from typing import Optional

from fastapi import Depends, Cookie, HTTPException
from sqlalchemy.orm import Session

from . import security, models, config
from .database import get_db


def get_current_user(
    df_session: Optional[str] = Cookie(default=None, alias=config.SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not df_session:
        return None
    user_id = security.read_session_token(df_session)
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_user(user: Optional[models.User] = Depends(get_current_user)) -> models.User:
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


def require_role(role: str):
    def _dep(user: models.User = Depends(require_user)) -> models.User:
        if user.role != role:
            raise HTTPException(status_code=403, detail=f"This action requires a {role} account.")
        return user
    return _dep
