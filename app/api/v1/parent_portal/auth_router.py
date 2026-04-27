"""Parent auth endpoints under /api/v1/auth/parent."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    ParentLoginRequest,
    ParentLoginResponse,
    ParentRefreshRequest,
    ParentRefreshResponse,
)

router = APIRouter(prefix="/api/v1/auth/parent", tags=["parent-auth"])
_LOGIN_RATE_WINDOW = timedelta(minutes=15)
_LOGIN_RATE_LIMIT = 10
_LOGIN_ATTEMPTS: Dict[str, List[datetime]] = {}


def _enforce_login_rate_limit(client_ip: str) -> None:
    now = datetime.now(timezone.utc)
    attempts = _LOGIN_ATTEMPTS.get(client_ip, [])
    recent = [ts for ts in attempts if now - ts <= _LOGIN_RATE_WINDOW]
    if len(recent) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    recent.append(now)
    _LOGIN_ATTEMPTS[client_ip] = recent


@router.post("/login", response_model=ParentLoginResponse)
async def parent_login(
    payload: ParentLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ParentLoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    _enforce_login_rate_limit(client_ip)
    try:
        return await service.parent_login(db, payload.email, payload.password)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/refresh", response_model=ParentRefreshResponse)
async def parent_refresh(
    payload: ParentRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> ParentRefreshResponse:
    try:
        return await service.parent_refresh_token(db, payload.refresh_token)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/forgot-password")
async def parent_forgot_password(
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    email = payload.get("email")
    if not email:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="email is required",
        )
    try:
        return await service.parent_forgot_password(db, email)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/reset-password")
async def parent_reset_password(
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = payload.get("token")
    new_password = payload.get("new_password")
    if not token or not new_password:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="token and new_password are required",
        )
    try:
        return await service.parent_reset_password(db, token, new_password)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
