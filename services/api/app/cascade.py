"""Shared cascade-delete helpers.

The production Postgres schema (database/migrations/0001_init.sql) already
has `ON DELETE CASCADE` wired from students/devices down through
usage/warning/restriction events. But a few tables were added later purely
through `Base.metadata.create_all` — `rule_websites` and
`sibling_manager_grants` — and `create_all` never attaches an `ON DELETE`
clause, so those rows would block a delete (or just get silently orphaned in
SQLite, which doesn't enforce FKs by default) unless removed explicitly.
Every place in the app that deletes a rule, a student, or a whole family
should go through these functions rather than deleting the row directly.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import models


def delete_rules(db: Session, rule_ids: list[str]) -> None:
    if not rule_ids:
        return
    db.query(models.RuleWebsite).filter(models.RuleWebsite.rule_id.in_(rule_ids)).delete(synchronize_session=False)
    db.query(models.WarningEvent).filter(models.WarningEvent.rule_id.in_(rule_ids)).delete(synchronize_session=False)
    db.query(models.RestrictionEvent).filter(models.RestrictionEvent.rule_id.in_(rule_ids)).delete(synchronize_session=False)
    db.query(models.ExtensionRequest).filter(models.ExtensionRequest.rule_id.in_(rule_ids)).update(
        {models.ExtensionRequest.rule_id: None}, synchronize_session=False
    )
    db.query(models.ScreenTimeRule).filter(models.ScreenTimeRule.id.in_(rule_ids)).delete(synchronize_session=False)


def _detach_user_logins(db: Session, user_ids: list[str]) -> None:
    """Clears FK references to a set of User rows that have no ON DELETE
    clause at the DB level (audit log authorship, extension-request
    decisions) before the User row itself is removed."""
    if not user_ids:
        return
    db.query(models.AuditLog).filter(models.AuditLog.actor_user_id.in_(user_ids)).update(
        {models.AuditLog.actor_user_id: None}, synchronize_session=False
    )
    db.query(models.ExtensionRequest).filter(models.ExtensionRequest.decided_by.in_(user_ids)).update(
        {models.ExtensionRequest.decided_by: None}, synchronize_session=False
    )
    db.query(models.User).filter(models.User.id.in_(user_ids)).delete(synchronize_session=False)


def delete_students(db: Session, student_ids: list[str], *, delete_logins: bool = True) -> None:
    """Deletes one or more Student rows and everything scoped under them
    (devices, rules, usage/warning/restriction history, extension requests,
    sibling-manager grants) and, unless delete_logins is False, each
    student's own login User row. Does not touch the parent Family row —
    callers still need to remove students before an empty family/account can
    be deleted."""
    if not student_ids:
        return
    device_ids = [d.id for d in db.query(models.Device).filter(models.Device.student_id.in_(student_ids)).all()]
    rule_ids = [r.id for r in db.query(models.ScreenTimeRule).filter(models.ScreenTimeRule.student_id.in_(student_ids)).all()]
    login_user_ids = [
        s.user_id for s in db.query(models.Student).filter(models.Student.id.in_(student_ids)).all() if s.user_id
    ]

    if device_ids:
        db.query(models.DeviceHealthEvent).filter(models.DeviceHealthEvent.device_id.in_(device_ids)).delete(synchronize_session=False)
        db.query(models.DevicePermission).filter(models.DevicePermission.device_id.in_(device_ids)).delete(synchronize_session=False)

    db.query(models.WarningEvent).filter(models.WarningEvent.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.query(models.RestrictionEvent).filter(models.RestrictionEvent.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.query(models.ExtensionRequest).filter(models.ExtensionRequest.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.query(models.UsageEvent).filter(models.UsageEvent.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.query(models.DailyUsageTotal).filter(models.DailyUsageTotal.student_id.in_(student_ids)).delete(synchronize_session=False)
    db.query(models.SiblingManagerGrant).filter(models.SiblingManagerGrant.manager_student_id.in_(student_ids)).delete(synchronize_session=False)

    delete_rules(db, rule_ids)

    if device_ids:
        db.query(models.Device).filter(models.Device.id.in_(device_ids)).delete(synchronize_session=False)

    db.query(models.Student).filter(models.Student.id.in_(student_ids)).delete(synchronize_session=False)

    if delete_logins and login_user_ids:
        _detach_user_logins(db, login_user_ids)


def delete_family(db: Session, family_id: str) -> None:
    """Deletes a family and everything under it, in FK-safe order. Commits
    internally (kept from the original demo-only version of this function) —
    callers doing this as part of a larger transaction with its own audit
    log should be fine committing again right after, since there's nothing
    left in this family for a second commit to race against."""
    student_ids = [s.id for s in db.query(models.Student).filter_by(family_id=family_id).all()]
    delete_students(db, student_ids)
    db.query(models.SiblingManagerGrant).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.FamilyOnboardingState).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.NotificationEvent).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.NotificationRecipient).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.AuditLog).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.FamilyMember).filter_by(family_id=family_id).delete(synchronize_session=False)
    db.query(models.Family).filter_by(id=family_id).delete(synchronize_session=False)
    db.commit()
