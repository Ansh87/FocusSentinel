from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

if settings.database_url.startswith("sqlite"):
    # pysqlite's default driver-level transaction handling doesn't play well
    # with SQLAlchemy SAVEPOINTs (db.begin_nested(), used by the usage-events
    # ingestion endpoint to isolate per-event duplicate-key failures within a
    # batch). This is SQLAlchemy's documented workaround — see "Serializable
    # isolation / Savepoints" in the SQLite dialect docs. Postgres needs none
    # of this; SAVEPOINT support there is native.
    @event.listens_for(engine, "connect")
    def _sqlite_disable_pysqlite_txn(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None
        # WAL mode lets one writer and multiple readers work concurrently
        # instead of sqlite's default rollback-journal mode, where any
        # connection with an open read transaction can make a different
        # connection's commit fail with "database is locked" — which is
        # exactly what happens here: the API serves each request on its own
        # session/connection while a test can hold a separate read-only
        # session open across several requests. busy_timeout adds a retry
        # window as a second line of defense under real contention.
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")

    @event.listens_for(engine, "begin")
    def _sqlite_emit_begin(conn):
        conn.exec_driver_sql("BEGIN")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
