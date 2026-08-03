from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_device, require_parent
from ..security import generate_device_token

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=schemas.DeviceRegisterResponse, status_code=201)
def register_device(payload: schemas.DeviceRegisterRequest, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    student = db.get(models.Student, payload.student_id)
    if not student:
        raise HTTPException(404, "Student not found")

    plaintext, token_hash = generate_device_token()
    device = models.Device(
        student_id=payload.student_id,
        device_type=payload.device_type,
        name=payload.name,
        platform_identifier=payload.platform_identifier,
        device_token_hash=token_hash,
        status="active",
    )
    db.add(device)
    db.flush()
    db.add(
        models.AuditLog(
            family_id=student.family_id,
            actor_user_id=user.id,
            actor_type="parent",
            action="device.registered",
            target_type="device",
            target_id=device.id,
            event_metadata={"device_type": payload.device_type, "name": payload.name},
        )
    )
    db.commit()
    return schemas.DeviceRegisterResponse(device_id=device.id, device_token=plaintext)


@router.post("/heartbeat")
def heartbeat(payload: schemas.DeviceHeartbeat, db: Session = Depends(get_db), device: models.Device = Depends(get_current_device)):
    device.last_seen_at = datetime.utcnow()
    for key, granted in payload.permissions.items():
        perm = db.query(models.DevicePermission).filter_by(device_id=device.id, permission_key=key).first()
        was_granted = perm.granted if perm else None
        if perm is None:
            perm = models.DevicePermission(device_id=device.id, permission_key=key, granted=granted)
            db.add(perm)
        else:
            perm.granted = granted
        perm.last_checked_at = datetime.utcnow()

        if was_granted is True and granted is False:
            db.add(
                models.DeviceHealthEvent(
                    device_id=device.id,
                    event_type="permission_removed",
                    details={"permission_key": key},
                )
            )
    db.commit()
    return {"status": "ok", "last_seen_at": device.last_seen_at.isoformat()}


@router.post("/{device_id}/revoke")
def revoke_device(device_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    device.status = "revoked"
    db.add(
        models.AuditLog(
            actor_user_id=user.id,
            actor_type="parent",
            action="device.revoked",
            target_type="device",
            target_id=device.id,
        )
    )
    db.commit()
    return {"status": "revoked"}
