from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent
from ..phone import normalize_phone

router = APIRouter(prefix="/notification-recipients", tags=["notification-recipients"])


def _require_family_membership(db: Session, user: models.User, family_id: str) -> None:
    membership = db.query(models.FamilyMember).filter_by(family_id=family_id, user_id=user.id).first()
    if not membership:
        raise HTTPException(403, "Not a member of this family")


def _normalized_mobile(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return normalize_phone(raw)
    except ValueError:
        raise HTTPException(400, "That doesn't look like a valid phone number.")


@router.post("", response_model=schemas.NotificationRecipientOut, status_code=201)
def create_recipient(payload: schemas.NotificationRecipientCreate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    _require_family_membership(db, user, payload.family_id)
    recipient = models.NotificationRecipient(
        family_id=payload.family_id,
        name=payload.name,
        relationship=payload.relationship,
        email=payload.email,
        mobile_number=_normalized_mobile(payload.mobile_number),
        preferred_channels=payload.preferred_channels,
        severity_preference=payload.severity_preference,
        verified=False,  # verification flow (email/SMS confirmation code) is a follow-up, not faked here
    )
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


@router.get("/family/{family_id}", response_model=list[schemas.NotificationRecipientOut])
def list_recipients(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    _require_family_membership(db, user, family_id)
    return db.query(models.NotificationRecipient).filter_by(family_id=family_id).all()


def _get_owned_recipient(db: Session, user: models.User, recipient_id: str) -> models.NotificationRecipient:
    recipient = db.get(models.NotificationRecipient, recipient_id)
    if not recipient:
        raise HTTPException(404, "Recipient not found")
    _require_family_membership(db, user, recipient.family_id)
    return recipient


@router.patch("/{recipient_id}", response_model=schemas.NotificationRecipientOut)
def update_recipient(recipient_id: str, payload: schemas.NotificationRecipientUpdate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    recipient = _get_owned_recipient(db, user, recipient_id)
    fields = payload.model_dump(exclude_unset=True)
    if "mobile_number" in fields:
        fields["mobile_number"] = _normalized_mobile(fields["mobile_number"])
    for field, value in fields.items():
        setattr(recipient, field, value)
    db.commit()
    db.refresh(recipient)
    return recipient


@router.delete("/{recipient_id}")
def delete_recipient(recipient_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    recipient = _get_owned_recipient(db, user, recipient_id)
    # NotificationEvent.recipient_id has no ON DELETE clause at the DB level
    # (see cascade.py's module docstring for why this pattern keeps showing
    # up in this codebase) -- past notification history stays, just no
    # longer attributed to a specific recipient row.
    db.query(models.NotificationEvent).filter_by(recipient_id=recipient_id).update(
        {models.NotificationEvent.recipient_id: None}, synchronize_session=False
    )
    db.delete(recipient)
    db.commit()
    return {"status": "recipient_deleted"}
