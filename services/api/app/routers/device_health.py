from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import ensure_own_student_or_parent, get_current_user

router = APIRouter(prefix="/device-health", tags=["device-health"])

# Neutral, non-accusatory language per spec section 16 — never phrased as
# "bypassed" or "disabled by the student." Four states a parent can act on:
# connected (all good), delayed (probably fine, just hasn't checked in
# recently), offline (hasn't reported in a long time), permission_issue (it's
# reporting, but something it needs was turned off).
OFFLINE_THRESHOLD_MINUTES = 60
DELAYED_THRESHOLD_MINUTES = 10


@router.get("", response_model=list[schemas.DeviceHealthOut])
def device_health(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    ensure_own_student_or_parent(db, user, student_id)
    devices = db.query(models.Device).filter_by(student_id=student_id).all()
    out = []
    now = datetime.utcnow()
    for d in devices:
        perms = db.query(models.DevicePermission).filter_by(device_id=d.id).all()
        has_denied_permission = any(p.granted is False for p in perms)
        minutes_since_seen = (now - d.last_seen_at).total_seconds() / 60 if d.last_seen_at else None

        if d.status == "revoked":
            status = "revoked"
        elif minutes_since_seen is None or minutes_since_seen >= OFFLINE_THRESHOLD_MINUTES:
            status = "offline"
        elif has_denied_permission:
            status = "permission_issue"
        elif minutes_since_seen >= DELAYED_THRESHOLD_MINUTES:
            status = "delayed"
        else:
            status = "connected"

        out.append(
            schemas.DeviceHealthOut(
                device_id=d.id,
                device_name=d.name,
                status=status,
                platform_identifier=d.platform_identifier,
                last_seen_at=d.last_seen_at,
                permissions={p.permission_key: p.granted for p in perms},
            )
        )
    return out
