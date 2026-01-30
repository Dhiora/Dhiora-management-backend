from datetime import datetime, timedelta, timezone
import secrets
from typing import Dict, Optional, Tuple

import bcrypt
from jose import jwt

from app.core.config import settings


def hash_password(plain_password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # In case the stored hash is invalid/corrupted
        return False


def create_access_token(
    *, subject: Dict, expires_minutes: Optional[int] = None
) -> str:
    if expires_minutes is None:
        expires_minutes = settings.access_token_expire_minutes

    to_encode = subject.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def create_refresh_token(*, expires_days: Optional[int] = None) -> Tuple[str, datetime]:
    if expires_days is None:
        expires_days = settings.refresh_token_expire_days
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)
    token = secrets.token_urlsafe(48)
    return token, expire

