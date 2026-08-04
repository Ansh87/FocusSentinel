from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


def ensure_own_student_or_parent(db: Session, user: models.User, student_id: str) -> None:
    """Read-scoping for the new student self-service view: a student-role
    user may only ever query their own linked Student record. Parent-role
    users are left exactly as permissive as they already were everywhere
    else in this codebase (no family-membership check here) — this only
    closes the new gap a student login would otherwise open, not a general
    authorization overhaul."""
    if user.role != "student":
        return
    own_student = db.query(models.Student).filter_by(user_id=user.id).first()
    if not own_student or own_student.id != student_id:
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
