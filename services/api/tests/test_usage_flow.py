"""End-to-end vertical slice test: register a device, set a short limit on
short-form video, push usage past warning one -> warning two -> restriction,
then request and approve an extension that lifts the restriction.

This exercises the same code path the browser extension uses in production
(POST /usage-events/batch), just with a Python HTTP client instead of a
Chrome service worker.
"""
from app import models
from conftest import create_family_student, register_and_login


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _device_auth(token):
    return {"Authorization": f"Bearer {token}"}


def register_device(client, parent_token, student_id):
    resp = client.post(
        "/devices/register",
        json={"student_id": student_id, "device_type": "browser_extension", "name": "Chrome"},
        headers=_auth(parent_token),
    )
    assert resp.status_code == 201
    return resp.json()["device_token"]


def make_rule(client, parent_token, student_id):
    resp = client.post(
        "/rules",
        json={
            "student_id": student_id,
            "name": "Short-form video limit",
            "scope_type": "category",
            "scope_category_key": "short_form_video",
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            "daily_limit_minutes": 1,
            "warning_one_at_minutes": 1,
            "warning_two_after_additional_minutes": 1,
            "block_after_warning_two_seconds": 30,
        },
        headers=_auth(parent_token),
    )
    assert resp.status_code == 201
    return resp.json()


def submit_usage(client, device_token, identifier, seconds, key_suffix):
    resp = client.post(
        "/usage-events/batch",
        json={
            "device_id": "unused-server-derives-from-token",
            "events": [
                {
                    "identifier": identifier,
                    "started_at": "2026-08-02T16:00:00Z",
                    "ended_at": "2026-08-02T16:01:00Z",
                    "active_duration_seconds": seconds,
                    "classification_source": "catalog",
                    "idempotency_key": f"evt-{key_suffix}",
                }
            ],
        },
        headers=_device_auth(device_token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_full_warning_to_restriction_to_extension_flow(client, db_session):
    parent_token = register_and_login(client)
    family_id, student_id = create_family_student(client, parent_token)
    device_token = register_device(client, parent_token, student_id)
    make_rule(client, parent_token, student_id)

    client.post(
        "/notification-recipients",
        json={"family_id": family_id, "name": "Parent", "relationship": "mother", "email": "parent@example.com", "preferred_channels": ["email"]},
        headers=_auth(parent_token),
    )

    # 70 seconds (~1.17 min) crosses the 1-minute warning-one threshold.
    result = submit_usage(client, device_token, "tiktok.com", 70, "1")
    assert result["evaluations"][0]["level"] == "warning_one"
    # db_session is a separate SQLAlchemy session from the one each API
    # request uses internally. SQLite (even in WAL mode) gives each
    # transaction a consistent snapshot from when it *began* — so without
    # committing here, this session's very first query above would pin a
    # snapshot that never sees any of the writes the next submit_usage() call
    # makes, and every assertion after it would see stale (often empty)
    # results. Committing (a no-op if nothing is pending) closes that
    # transaction so the next query opens a fresh one against current data.
    db_session.commit()
    warning_events = db_session.query(models.WarningEvent).all()
    assert len(warning_events) == 1
    assert warning_events[0].level == 1

    notifications = db_session.query(models.NotificationEvent).filter_by(event_type="limit_crossed").all()
    assert len(notifications) == 1
    assert notifications[0].status == "queued"
    db_session.commit()

    # +60s -> cumulative ~2.17 min, crosses warning_one(1) + grace(1) = 2 min threshold.
    result = submit_usage(client, device_token, "tiktok.com", 60, "2")
    assert result["evaluations"][0]["level"] == "warning_two"
    db_session.commit()
    assert db_session.query(models.WarningEvent).filter_by(level=2).count() == 1
    db_session.commit()

    # +40s -> cumulative ~2.83 min; (2.83 - 2.17) * 60 = ~40s >= 30s grace -> restricted.
    result = submit_usage(client, device_token, "tiktok.com", 40, "3")
    assert result["evaluations"][0]["level"] == "restricted"
    db_session.commit()

    restriction = db_session.query(models.RestrictionEvent).filter_by(student_id=student_id, active=True).first()
    assert restriction is not None

    restriction_notifications = db_session.query(models.NotificationEvent).filter_by(event_type="restricted").all()
    assert len(restriction_notifications) == 1
    db_session.commit()

    # Duplicate submission of the same idempotency key must not double-count or re-warn.
    dup = submit_usage(client, device_token, "tiktok.com", 40, "3")
    assert dup["duplicates"] == 1
    assert dup["accepted"] == 0
    db_session.commit()

    # Student requests more time; parent approves 5 minutes.
    resp = client.post(
        "/extension-requests",
        json={
            "student_id": student_id,
            "restriction_event_id": restriction.id,
            "rule_id": restriction.rule_id,
            "requested_minutes": 5,
            "reason_code": "friends",
            "explanation": "Finishing a match with friends",
        },
        headers=_auth(parent_token),
    )
    assert resp.status_code == 201
    request_id = resp.json()["id"]
    db_session.commit()

    extension_requested = db_session.query(models.NotificationEvent).filter_by(event_type="extension_requested").all()
    assert len(extension_requested) == 1
    db_session.commit()

    resp = client.post(f"/extension-requests/{request_id}/approve", json={"minutes": 5}, headers=_auth(parent_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    db_session.commit()

    db_session.refresh(restriction)
    assert restriction.active is False
    assert restriction.lifted_reason == "extension_approved"

    audit_actions = [a.action for a in db_session.query(models.AuditLog).all()]
    assert "extension_request.approved" in audit_actions


def test_progress_notice_is_not_a_formal_warning(client, db_session):
    parent_token = register_and_login(client, email="parent2@example.com")
    family_id, student_id = create_family_student(client, parent_token)
    device_token = register_device(client, parent_token, student_id)
    make_rule(client, parent_token, student_id)

    # 50 seconds (~0.83 min) is 83% of the 1-minute limit -> progress notice, no warning row.
    result = submit_usage(client, device_token, "tiktok.com", 50, "p1")
    assert result["evaluations"][0]["level"] == "progress_notice"
    assert db_session.query(models.WarningEvent).count() == 0


def test_false_positive_threshold_ignores_sub_3_second_samples(client, db_session):
    parent_token = register_and_login(client, email="parent3@example.com")
    family_id, student_id = create_family_student(client, parent_token)
    device_token = register_device(client, parent_token, student_id)
    make_rule(client, parent_token, student_id)

    result = submit_usage(client, device_token, "tiktok.com", 2, "fp1")
    assert result["accepted"] == 0
    assert db_session.query(models.UsageEvent).count() == 0


def test_untracked_domain_is_not_classified_or_limited(client):
    parent_token = register_and_login(client, email="parent4@example.com")
    family_id, student_id = create_family_student(client, parent_token)
    device_token = register_device(client, parent_token, student_id)
    make_rule(client, parent_token, student_id)

    result = submit_usage(client, device_token, "example.com", 100, "u1")
    assert result["evaluations"][0]["level"] == "none"
