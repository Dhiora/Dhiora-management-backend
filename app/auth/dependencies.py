from typing import Dict, Optional
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

    user_id_str = payload.get("user_id") or payload.get("sub")
    tenant_id_str = payload.get("tenant_id")
    role_name = payload.get("role")
    if not user_id_str or not tenant_id_str or not role_name:
        raise credentials_exception

    try:
        user_id = UUID(user_id_str)
        tenant_id = UUID(tenant_id_str)
    except ValueError:
        raise credentials_exception

    academic_year_id: Optional[UUID] = None
    academic_year_status: Optional[str] = None
    ay_id_str = payload.get("academic_year_id")
    if ay_id_str:
        try:
            academic_year_id = UUID(ay_id_str)
        except ValueError:
            pass
    academic_year_status = payload.get("academic_year_status")

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
        academic_year_id=academic_year_id,
        academic_year_status=academic_year_status,
    )


CLOSED_ACADEMIC_YEAR_MESSAGE = "This academic year is closed and cannot be modified."


async def require_writable_academic_year(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Dependency: block CREATE/UPDATE/DELETE when academic year is CLOSED or missing.
    Use on write endpoints (POST, PUT, PATCH, DELETE) that are scoped to the current academic year.
    Admins without an active year can still call endpoints that create/set the academic year.
    """
    if current_user.academic_year_status == "CLOSED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=CLOSED_ACADEMIC_YEAR_MESSAGE,
        )
    # Optional: block writes when no academic year (non-admin). Admins may have no year until they create one.
    if current_user.academic_year_id is None and current_user.role not in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active academic year. Please contact administrator.",
        )
    return current_user

