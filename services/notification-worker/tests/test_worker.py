import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

from app.worker import process_once


def make_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE notification_recipients (
                    id TEXT PRIMARY KEY, name TEXT, email TEXT, mobile_number TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE notification_events (
                    id TEXT PRIMARY KEY, recipient_id TEXT, event_type TEXT,
                    channel TEXT, payload TEXT, status TEXT, created_at TEXT, sent_at TEXT
                )
                """
            )
        )
    return engine


def insert_recipient(engine, email="parent@example.com"):
    rid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO notification_recipients (id, name, email, mobile_number) VALUES (:id, :n, :e, :m)"),
            {"id": rid, "n": "Parent", "e": email, "m": None},
        )
    return rid


def insert_event(engine, recipient_id, event_type="restricted", channel="email", status="queued"):
    eid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO notification_events (id, recipient_id, event_type, channel, payload, status, created_at) "
                "VALUES (:id, :rid, :et, :ch, :payload, :status, datetime('now'))"
            ),
            {
                "id": eid,
                "rid": recipient_id,
                "et": event_type,
                "ch": channel,
                "payload": json.dumps({"student_name": "Alex", "rule_name": "Short-form video"}),
                "status": status,
            },
        )
    return eid


def test_processes_queued_email_and_marks_sent(capsys):
    engine = make_engine()
    rid = insert_recipient(engine)
    eid = insert_event(engine, rid)

    sent = process_once(engine)
    assert sent == 1

    with engine.begin() as conn:
        row = conn.execute(text("SELECT status FROM notification_events WHERE id = :id"), {"id": eid}).mappings().first()
    assert row["status"] == "sent"

    captured = capsys.readouterr()
    assert "Alex" in captured.out


def test_only_queued_rows_are_processed():
    engine = make_engine()
    rid = insert_recipient(engine)
    insert_event(engine, rid, status="sent")
    insert_event(engine, rid, status="suppressed_dedup")

    sent = process_once(engine)
    assert sent == 0


def test_missing_email_marks_failed_not_crash():
    engine = make_engine()
    rid = insert_recipient(engine, email=None)
    eid = insert_event(engine, rid)

    sent = process_once(engine)
    assert sent == 0
    with engine.begin() as conn:
        row = conn.execute(text("SELECT status FROM notification_events WHERE id = :id"), {"id": eid}).mappings().first()
    assert row["status"] == "failed"
