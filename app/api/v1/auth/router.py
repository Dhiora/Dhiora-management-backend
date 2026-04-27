from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.auth.schemas import (
    AcademicYearContext,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TenantInfo,
    CurrentUser,
)
from app.auth.services import ServiceError, login_user, register_tenant_and_admin, request_password_reset, reset_password
from app.core.models import AcademicYear, Tenant, TenantModule
from app.db.session import get_db
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    try:
        return await register_tenant_and_admin(db, payload)
    except ServiceError as e:
        # Map service errors to HTTP responses
        if e.status_code == http_status.HTTP_409_CONFLICT:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == http_status.HTTP_400_BAD_REQUEST:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == http_status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise HTTPException(status_code=e.status_code, detail="Internal server error")
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=http_status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    try:
        return await login_user(db, payload)
    except ServiceError as e:
        if e.status_code in {
            http_status.HTTP_401_UNAUTHORIZED,
            http_status.HTTP_403_FORBIDDEN,
            http_status.HTTP_409_CONFLICT,
        }:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == http_status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise HTTPException(status_code=e.status_code, detail="Internal server error")
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=http_status.HTTP_200_OK,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    try:
        return await request_password_reset(db, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=http_status.HTTP_200_OK,
)
async def reset_password_endpoint(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    try:
        return await reset_password(db, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/login-oauth")
async def login_oauth(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    payload = LoginRequest(
        email=form_data.username.strip(),
        password=form_data.password,
    )
    try:
        result = await login_user(db, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {
        "access_token": result.access_token,
        "token_type": "bearer",
    }


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user identity, role, modules, and permissions (always fresh from DB)",
)
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """
    Pass the Bearer token to get the user's current role, enabled modules, and
    permissions fresh from the database — not from the (possibly stale) JWT claims.
    Useful after a role change without forcing a re-login.
    """
    # Fetch full user row
    user_result = await db.execute(
        select(User).where(User.id == current_user.id, User.tenant_id == current_user.tenant_id)
    )
    user: User = user_result.scalar_one_or_none()
    if not user or user.status != "ACTIVE":
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Fetch tenant
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant: Tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Tenant not found")

    # Fetch enabled modules
    modules_result = await db.execute(
        select(TenantModule.module_key)
        .where(TenantModule.tenant_id == tenant.id, TenantModule.is_enabled.is_(True))
    )
    modules = [row[0] for row in modules_result.all()]

    # Fetch permissions from current role_id (fresh from DB)
    permissions: dict = {}
    if user.role_id:
        role_result = await db.execute(
            select(Role).where(Role.id == user.role_id, Role.tenant_id == tenant.id)
        )
        role = role_result.scalar_one_or_none()
        if role and role.permissions:
            permissions = role.permissions

    # Fetch current academic year
    ay_result = await db.execute(
        select(AcademicYear)
        .where(AcademicYear.tenant_id == tenant.id, AcademicYear.is_current.is_(True))
    )
    active_ay = ay_result.scalar_one_or_none()
    academic_year_ctx = None
    if active_ay:
        academic_year_ctx = AcademicYearContext(id=active_ay.id, status=active_ay.status)

    return MeResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        user_type=getattr(user, "user_type", None),
        status=user.status,
        tenant=TenantInfo(
            id=tenant.id,
            organization_code=tenant.organization_code,
            organization_name=tenant.organization_name,
            organization_type=tenant.organization_type,
        ),
        modules=modules,
        permissions=permissions,
        academic_year=academic_year_ctx,
    )
