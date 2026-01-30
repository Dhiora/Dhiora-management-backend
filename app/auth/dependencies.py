from typing import Dict
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role, User
from app.auth.schemas import CurrentUser
from app.core.config import settings
from app.db.session import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login-oauth")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Resolve the authenticated user and their permissions from the access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise credentials_exception

    user_id_str = payload.get("user_id")
    tenant_id_str = payload.get("tenant_id")
    role_name = payload.get("role")
    if not user_id_str or not tenant_id_str or not role_name:
        raise credentials_exception

    try:
        user_id = UUID(user_id_str)
        tenant_id = UUID(tenant_id_str)
    except ValueError:
        raise credentials_exception

    # Load user
    stmt = select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user or user.status != "ACTIVE":
        raise credentials_exception

    # Load role permissions (tenant-scoped)
    role_stmt = select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name)
    role_result = await db.execute(role_stmt)
    role = role_result.scalar_one_or_none()

    permissions: Dict[str, Dict[str, bool]] = {}
    if role and role.permissions:
        # Ensure proper type
        permissions = role.permissions  # type: ignore[assignment]

    return CurrentUser(
        id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        permissions=permissions or {},
    )

