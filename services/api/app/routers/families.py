from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent

router = APIRouter(prefix="/families", tags=["families"])


@router.post("", response_model=schemas.FamilyOut, status_code=201)
def create_family(payload: schemas.FamilyCreate, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    family = models.Family(name=payload.name, timezone=payload.timezone)
    db.add(family)
    db.flush()
    db.add(models.FamilyMember(family_id=family.id, user_id=user.id, role="parent"))
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
    family = db.get(models.Family, family_id)
    if not family:
        from fastapi import HTTPException
        raise HTTPException(404, "Family not found")
    return family
