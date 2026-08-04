from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, setup_status
from ..database import get_db
from ..deps import require_parent

router = APIRouter(prefix="/families", tags=["families"])

# How long "Remind Me Later" hides the full-screen setup banner before it
# reappears -- long enough not to nag every single visit, short enough that
# a family who genuinely never comes back to finish setup still sees it
# again periodically rather than it going silent forever.
REMINDER_SNOOZE_DAYS = 3


def _require_membership(db: Session, user: models.User, family_id: str) -> models.Family:
    family = db.get(models.Family, family_id)
    if not family:
        raise HTTPException(404, "Family not found")
    membership = db.query(models.FamilyMember).filter_by(family_id=family_id, user_id=user.id).first()
    if not membership:
        raise HTTPException(403, "Not a member of this family")
    return family


@router.post("", response_model=schemas.FamilyOut, status_code=201)
def create_family(payload: schemas.FamilyCreate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    family = models.Family(name=payload.name, timezone=payload.timezone)
    db.add(family)
    db.flush()
    db.add(models.FamilyMember(family_id=family.id, user_id=user.id, role="parent"))
    db.add(models.FamilyOnboardingState(family_id=family.id))
    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="family.created",
            target_type="family",
            target_id=family.id,
        )
    )
    db.commit()
    db.refresh(family)
    return family


@router.get("/mine", response_model=list[schemas.FamilyOut])
def my_families(db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    memberships = db.query(models.FamilyMember).filter_by(user_id=user.id).all()
    family_ids = [m.family_id for m in memberships]
    if not family_ids:
        return []
    return db.query(models.Family).filter(models.Family.id.in_(family_ids)).all()


@router.get("/{family_id}", response_model=schemas.FamilyOut)
def get_family(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    return _require_membership(db, user, family_id)


@router.patch("/{family_id}", response_model=schemas.FamilyOut)
def update_family(family_id: str, payload: schemas.FamilyUpdate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    family = _require_membership(db, user, family_id)
    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        if value is not None:
            setattr(family, field, value)
    db.add(
        models.AuditLog(
            family_id=family.id,
            actor_user_id=user.id,
            actor_type="parent",
            action="family.updated",
            target_type="family",
            target_id=family.id,
            event_metadata=fields,
        )
    )
    db.commit()
    db.refresh(family)
    return family


@router.get("/{family_id}/setup-status", response_model=schemas.SetupStatusOut)
def get_setup_status(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    _require_membership(db, user, family_id)
    setup_status.get_or_create_onboarding_state(db, family_id)
    db.commit()
    return setup_status.compute_setup_status(db, family_id)


@router.post("/{family_id}/setup-status/dismiss-reminder", response_model=schemas.SetupStatusOut)
def dismiss_setup_reminder(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    _require_membership(db, user, family_id)
    state = setup_status.get_or_create_onboarding_state(db, family_id)
    state.reminder_dismissed_until = datetime.utcnow() + timedelta(days=REMINDER_SNOOZE_DAYS)
    db.commit()
    return setup_status.compute_setup_status(db, family_id)


@router.post("/{family_id}/setup-status/skip-device", response_model=schemas.SetupStatusOut)
def skip_device_setup(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    _require_membership(db, user, family_id)
    state = setup_status.get_or_create_onboarding_state(db, family_id)
    state.device_connect_skipped = True
    db.commit()
    return setup_status.compute_setup_status(db, family_id)
