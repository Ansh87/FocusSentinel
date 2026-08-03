"""Offline-first behavior: a device that queued usage events while offline
submits them in one batch after reconnecting. Events must land on the
calendar day they actually occurred (not "today"), and re-submitting the same
batch after a retry must not double count or re-fire warnings.
"""
from app import models
from conftest import create_family_student, register_and_login
from test_usage_flow import make_rule, register_device


def submit(client, device_token, identifier, seconds, key, started_at):
    return client.post(
        "/usage-events/batch",
        json={
            "device_id": "unused",
            "events": [
                {
                    "identifier": identifier,
                    "started_at": started_at,
                    "ended_at": started_at,
                    "active_duration_seconds": seconds,
                    "classification_source": "catalog",
                    "idempotency_key": key,
                }
            ],
        },
        headers={"Authorization": f"Bearer {device_token}"},
    )


def test_offline_queued_events_attributed_to_original_day(client, db_session):
    parent_token = register_and_login(client, email="offline_parent@example.com")
    family_id, student_id = create_family_student(client, parent_token)
    device_token = register_device(client, parent_token, student_id)
    make_rule(client, parent_token, student_id)

    # Device was offline all day yesterday, then reconnects and syncs both
    # yesterday's and today's queued events in the same batch call.
    r1 = submit(client, device_token, "tiktok.com", 40, "yesterday-1", "2026-08-01T10:00:00-05:00")
    r2 = submit(client, device_token, "tiktok.com", 40, "today-1", "2026-08-02T10:00:00-05:00")
    assert r1.status_code == 200 and r2.status_code == 200

    totals = db_session.query(models.DailyUsageTotal).filter_by(student_id=student_id).all()
    dates = sorted(t.usage_date for t in totals)
    assert dates == ["2026-08-01", "2026-08-02"]
    assert all(t.total_seconds == 40 for t in totals)


def test_resyncing_same_batch_after_retry_does_not_duplicate(client, db_session):
    parent_token = register_and_login(client, email="retry_parent@example.com")
    family_id, student_id = create_family_student(client, parent_token)
    device_token = register_device(client, parent_token, student_id)
    make_rule(client, parent_token, student_id)

    first = submit(client, device_token, "tiktok.com", 50, "retry-key-1", "2026-08-02T09:00:00-05:00")
    assert first.json()["accepted"] == 1

    # Simulate a network retry resending the exact same event (same
    # idempotency key) — must be rejected as a duplicate, not double counted.
    second = submit(client, device_token, "tiktok.com", 50, "retry-key-1", "2026-08-02T09:00:00-05:00")
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1

    total = db_session.query(models.DailyUsageTotal).filter_by(student_id=student_id, usage_date="2026-08-02").first()
    assert total.total_seconds == 50
