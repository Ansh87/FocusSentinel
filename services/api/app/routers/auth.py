from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..notifications import enqueue_direct_email
from ..security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from . import demo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter_by(email=payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = models.User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        display_name=payload.display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        role=user.role,
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    demo.ensure_demo_account_family(db, user)
    return schemas.TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        role=user.role,
    )


@router.post("/change-password")
def change_password(payload: schemas.ChangePasswordRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "password_changed"}


@router.post("/request-password-reset")
def request_password_reset(payload: schemas.RequestPasswordResetRequest, db: Session = Depends(get_db)):
    """Always returns the same generic response whether or not the email is
    registered, so this endpoint can't be used to check which emails have an
    account (account enumeration). If the account exists, a reset email is
    queued through the same notification pipeline the rest of the app uses —
    see enqueue_direct_email for why that's a meaningfully different claim
    than "an email was sent": actual delivery depends on a real
    email_provider being configured for the notification-worker service."""
    user = db.query(models.User).filter_by(email=payload.email).first()
    if user:
        token = create_password_reset_token(user.id)
        reset_url = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
        enqueue_direct_email(
            db,
            to_email=user.email,
            event_type="password_reset",
            payload={"reset_url": reset_url, "expires_minutes": settings.password_reset_expire_minutes},
            dedup_key=f"password_reset:{user.id}",
        )
        db.commit()
    return {"status": "if_registered_reset_email_queued"}


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.token)
    if not data or data.get("type") != "password_reset":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")
    user = db.get(models.User, data["sub"])
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "password_reset"}
