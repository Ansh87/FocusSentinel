from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/device-health", tags=["device-health"])

OFFLINE_THRESHOLD_MINUTES = 60


@router.get("", response_model=list[schemas.DeviceHealthOut])
def device_health(student_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    devices = db.query(models.Device).filter_by(student_id=student_id).all()
    out = []
    cutoff = datetime.utcnow() - timedelta(minutes=OFFLINE_THRESHOLD_MINUTES)
    for d in devices:
        perms = db.query(models.DevicePermission).filter_by(device_id=d.id).all()
        status = d.status
        # Neutral, non-accusatory language per spec section 16 — never phrased
        # as "bypassed" or "disabled by the student."
        if d.status == "active" and (d.last_seen_at is None or d.last_seen_at < cutoff):
            status = "not_reporting"
        out.append(
            schemas.DeviceHealthOut(
                device_id=d.id,
                device_name=d.name,
                status=status,
                last_seen_at=d.last_seen_at,
                permissions={p.permission_key: p.granted for p in perms},
            )
        )
    return out
