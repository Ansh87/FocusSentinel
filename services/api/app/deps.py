from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import decode_token, hash_device_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing credentials")
    payload = decode_token(creds.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(models.User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def require_parent(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role not in ("parent", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Parent/guardian access required")
    return user


def require_student(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Student access required")
    return user


def user_can_manage_student(db: Session, user: models.User, student_id: str) -> bool:
    """True if `user` may edit rules / decide extension requests for
    `student_id`: any parent (unchanged, family-membership isn't checked
    here — matches the rest of this codebase's existing permissiveness for
    parents), or a student holding an active SiblingManagerGrant for another
    student in their own family. A sibling manager can't manage themselves
    through this grant — that's just their own student view."""
    if user.role in ("parent", "admin"):
        return True
    if user.role != "student":
        return False
    own_student = db.query(models.Student).filter_by(user_id=user.id).first()
    if not own_student or own_student.id == student_id:
        return False
    target = db.get(models.Student, student_id)
    if not target or target.family_id != own_student.family_id:
        return False
    return active_sibling_grant(db, own_student.family_id, own_student.id) is not None


def active_sibling_grant(db: Session, family_id: str, manager_student_id: str) -> models.SiblingManagerGrant | None:
    """Wrapped in a try/except because `sibling_manager_grants` is a table
    added purely via `Base.metadata.create_all` (see models.py) rather than
    the tracked SQL migration — on a deployment where that hasn't run yet
    (or a stale connection holds a schema snapshot from before it existed),
    Postgres aborts the whole transaction on a "relation does not exist"
    error, and every other query on this same request's session would fail
    right along with it. Treat that as "no active grant" rather than letting
    an auxiliary permission lookup take down reads that have nothing to do
    with sibling management."""
    try:
        return (
            db.query(models.SiblingManagerGrant)
            .filter(
                models.SiblingManagerGrant.family_id == family_id,
                models.SiblingManagerGrant.manager_student_id == manager_student_id,
            )
            .filter(
                or_(
                    models.SiblingManagerGrant.expires_at.is_(None),
                    models.SiblingManagerGrant.expires_at > datetime.utcnow(),
                )
            )
            .first()
        )
    except (OperationalError, ProgrammingError):
        db.rollback()
        return None


def ensure_can_manage_student(db: Session, user: models.User, student_id: str) -> None:
    if not user_can_manage_student(db, user, student_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to manage this student")


def ensure_own_student_or_parent(db: Session, user: models.User, student_id: str) -> None:
    """Read-scoping for the student self-service view: a student-role user
    may query their own linked Student record, or any student they hold a
    SiblingManagerGrant over (they need to be able to see a sibling's rules
    and requests in order to manage them). Parent-role users are left
    exactly as permissive as they already were everywhere else in this
    codebase (no family-membership check here)."""
    if user.role != "student":
        return
    own_student = db.query(models.Student).filter_by(user_id=user.id).first()
    if own_student and own_student.id == student_id:
        return
    if user_can_manage_student(db, user, student_id):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only view your own data")


def get_current_device(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.Device:
    """Devices (browser extension, agents) authenticate with a narrowly scoped
    bearer token issued at registration, distinct from user JWTs. This keeps a
    compromised device token from granting dashboard/account access."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing device token")
    token_hash = hash_device_token(creds.credentials)
    device = db.query(models.Device).filter_by(device_token_hash=token_hash).first()
    if device is None or device.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked device token")
    return device
