from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from . import models, schemas, security, config
from .database import get_db
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=schemas.UserOut)
def signup(
    payload: schemas.SignupRequest,
    response: Response,
    role: str = "consumer",
    db: Session = Depends(get_db),
):
    if role not in ("consumer", "dealer"):
        raise HTTPException(400, "role must be 'consumer' or 'dealer'.")

    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(409, "An account with that email already exists.")

    user = models.User(
        email=payload.email,
        password_hash=security.hash_password(payload.password),
        role=role,
    )
    if role == "dealer":
        user.dealer_name = payload.dealer_name or payload.email.split("@")[0]
        user.is_vicimus_client = False
        user.trial_ends_at = models.User.new_trial_window()

    db.add(user)
    db.commit()
    db.refresh(user)

    _set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=schemas.UserOut)
def login(payload: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    _set_session_cookie(response, user.id)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=Optional[schemas.UserOut])
def me(user: Optional[models.User] = Depends(get_current_user)):
    return user


def _set_session_cookie(response: Response, user_id: str) -> None:
    token = security.create_session_token(user_id)
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=security.SESSION_MAX_AGE_SECONDS,
        secure=config.ENVIRONMENT == "production",
    )
