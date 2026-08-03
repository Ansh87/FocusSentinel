from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent

router = APIRouter(prefix="/notification-recipients", tags=["notification-recipients"])


@router.post("", response_model=schemas.NotificationRecipientOut, status_code=201)
def create_recipient(payload: schemas.NotificationRecipientCreate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    recipient = models.NotificationRecipient(
        family_id=payload.family_id,
        name=payload.name,
        relationship=payload.relationship,
        email=payload.email,
        mobile_number=payload.mobile_number,
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
    return db.query(models.NotificationRecipient).filter_by(family_id=family_id).all()
