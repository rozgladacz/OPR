from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .db import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_current_user(optional: bool = False):
    def dependency(
        request: Request, db: Session = Depends(get_db)
    ) -> Optional[models.User]:
        user_id = request.session.get("user_id")
        if not user_id:
            if optional:
                return None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        user = db.get(models.User, user_id)
        if user is None:
            request.session.pop("user_id", None)
            if optional:
                return None
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return user

    return dependency
