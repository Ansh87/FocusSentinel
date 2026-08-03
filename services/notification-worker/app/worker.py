"""Notification worker: polls the shared `notification_events` table for
queued rows and dispatches them through the configured adapter.

Why polling instead of only Celery/Redis? Postgres is already the durable
queue (the row exists and is deduplicated before this process ever sees it),
so a simple poll loop is enough for Phase 1 and works identically whether or
not Redis is up. `run_forever()` is what the Docker Compose `worker` service
runs; `process_once()` is what tests and one-off invocations use.
"""
from __future__ import annotations

import time
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .adapters import NotificationMessage, get_email_adapter, get_sms_adapter
from .config import settings
from .templates import render


def process_once(engine) -> int:
    sent = 0
    with Session(engine) as db:
        rows = db.execute(
            text(
                """
                SELECT ne.id, ne.event_type, ne.channel, ne.payload,
                       nr.name, nr.email, nr.mobile_number
                FROM notification_events ne
                JOIN notification_recipients nr ON nr.id = ne.recipient_id
                WHERE ne.status = 'queued'
                ORDER BY ne.created_at ASC
                LIMIT 50
                """
            )
        ).mappings().all()

        for row in rows:
            import json

            payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
            payload.setdefault("student_name", payload.get("student_name", "Your student"))
            subject, body = render(row["event_type"], payload)

            try:
                if row["channel"] == "email":
                    if not row["email"]:
                        raise RuntimeError("Recipient has no email on file")
                    get_email_adapter().send(NotificationMessage(subject=subject, body=body, to_email=row["email"]))
                elif row["channel"] == "sms":
                    if not row["mobile_number"]:
                        raise RuntimeError("Recipient has no mobile number on file")
                    get_sms_adapter().send(NotificationMessage(subject=subject, body=body, to_phone=row["mobile_number"]))
                else:
                    # push / in_app delivery is a future-phase integration
                    # (FCM/APNs) — see docs/KNOWN_LIMITATIONS.md.
                    raise RuntimeError(f"Channel '{row['channel']}' has no configured adapter yet")

                db.execute(
                    text("UPDATE notification_events SET status = 'sent', sent_at = :now WHERE id = :id"),
                    {"now": datetime.utcnow(), "id": row["id"]},
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001 - worker must not crash on one bad row
                db.execute(
                    text("UPDATE notification_events SET status = 'failed' WHERE id = :id"),
                    {"id": row["id"]},
                )
                print(f"[notification-worker] failed to send {row['id']}: {exc}")

        db.commit()
    return sent


def run_forever():
    engine = create_engine(settings.database_url, future=True)
    print(f"[notification-worker] polling every {settings.poll_interval_seconds}s using provider "
          f"email={settings.email_provider} sms={settings.sms_provider}")
    while True:
        try:
            n = process_once(engine)
            if n:
                print(f"[notification-worker] sent {n} notification(s)")
        except Exception as exc:  # noqa: BLE001
            print(f"[notification-worker] poll loop error: {exc}")
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    run_forever()
