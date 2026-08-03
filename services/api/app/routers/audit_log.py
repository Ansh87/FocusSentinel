from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_parent

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


@router.get("", response_model=list[schemas.AuditLogOut])
def get_audit_log(family_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_parent)):
    return (
        db.query(models.AuditLog)
        .filter_by(family_id=family_id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
