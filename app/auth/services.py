from datetime import datetime, timezone
from typing import List, Optional

from fastapi import status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    TenantInfo,
    UserInfo,
)
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.auth.models import RefreshToken, User
from app.core.exceptions import ServiceError
from app.core.models import Tenant, TenantModule
from app.core.tenant_service import generate_organization_code


async def register_tenant_and_admin(
    db: AsyncSession, payload: RegisterRequest
) -> RegisterResponse:
    # 2. Check admin email uniqueness across all tenants
    existing_user_stmt = select(User).where(User.email == payload.admin_email)
    existing_user_result = await db.execute(existing_user_stmt)
    existing_user = existing_user_result.scalar_one_or_none()
    if existing_user:
        raise ServiceError("Email is already in use", status.HTTP_409_CONFLICT)

    try:
        # 3. Auto-generate organization_code (never accept from frontend; tenant_id remains PK)
        organization_code = await generate_organization_code(db, payload.organization_type.value)
        # 4. Create tenant with both tenant_id (UUID) and organization_code (public identifier)
        # org_short_code: optional, uppercase before save; for identification only (e.g. employee numbers)
        org_short_code = payload.org_short_code.strip().upper()[:10] if payload.org_short_code and payload.org_short_code.strip() else None
        tenant = Tenant(
            organization_code=organization_code,
            organization_name=payload.organization_name,
            organization_type=payload.organization_type.value,
            country=payload.country,
            timezone=payload.timezone,
            status="ACTIVE",
            org_short_code=org_short_code,
        )
        db.add(tenant)
        await db.flush()  # to populate tenant.id

        # 5. Enable selected modules
        modules: List[TenantModule] = []
        for module_key in payload.selected_modules:
            module = TenantModule(
                tenant_id=tenant.id,
                module_key=module_key,
                is_enabled=True,
            )
            db.add(module)
            modules.append(module)

        # 6. Hash password
        password_hash = hash_password(payload.password)

        # 7. Create Super Admin user
        admin_user = User(
            tenant_id=tenant.id,
            full_name=payload.admin_full_name,
            email=payload.admin_email,
            mobile=payload.admin_mobile,
            password_hash=password_hash,
            role="SUPER_ADMIN",
            status="ACTIVE",
            source="SYSTEM",
        )
        db.add(admin_user)

        # NOTE: 8. Trial subscription bootstrap could be added here when subscription model exists.

        await db.commit()
        await db.refresh(tenant)

    except IntegrityError as e:
        await db.rollback()
        # Surface conflicts clearly; rest as generic error
        raise ServiceError(
            "Conflict while creating tenant or user", status.HTTP_409_CONFLICT
        ) from e
    except ServiceError:
        # already mapped, just bubble up
        raise
    except Exception as e:
        await db.rollback()
        raise ServiceError(
            "Failed to create account", status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from e

    return RegisterResponse(
        success=True,
        message="Account created successfully",
        tenant_id=tenant.id,
        organization_code=tenant.organization_code,
        org_short_code=tenant.org_short_code,
    )


async def login_user(db: AsyncSession, payload: LoginRequest) -> LoginResponse:
    # 1. Find user by email (case-insensitive)
    user_stmt = select(User).where(func.lower(User.email) == func.lower(payload.email))
    user_result = await db.execute(user_stmt)
    user: Optional[User] = user_result.scalar_one_or_none()
    if not user:
        raise ServiceError("Invalid credentials", status.HTTP_401_UNAUTHORIZED)

    # 2. Verify password hash
    if not verify_password(payload.password, user.password_hash):
        raise ServiceError("Invalid credentials", status.HTTP_401_UNAUTHORIZED)

    # 3. Check user status
    if user.status != "ACTIVE":
        raise ServiceError("User is inactive", status.HTTP_403_FORBIDDEN)

    # 4. Fetch tenant status
    tenant_stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    tenant_result = await db.execute(tenant_stmt)
    tenant: Optional[Tenant] = tenant_result.scalar_one_or_none()
    if not tenant:
        raise ServiceError("Tenant not found", status.HTTP_403_FORBIDDEN)
    if tenant.status != "ACTIVE":
        raise ServiceError("Tenant is inactive", status.HTTP_403_FORBIDDEN)

    # 5. Fetch enabled modules for tenant
    modules_stmt = (
        select(TenantModule.module_key)
        .where(TenantModule.tenant_id == tenant.id)
        .where(TenantModule.is_enabled.is_(True))
    )
    modules_result = await db.execute(modules_stmt)
    modules: List[str] = [row[0] for row in modules_result.all()]

    issued_at = datetime.now(timezone.utc)

    # 6. Generate access token (JWT); include organization_code for convenience, tenant_id remains primary
    access_payload = {
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "organization_code": tenant.organization_code,
        "role": user.role,
        "modules": modules,
        "iat": int(issued_at.timestamp()),
    }
    access_token = create_access_token(subject=access_payload)

    # 7. Generate refresh token
    refresh_token_str, refresh_expires_at = create_refresh_token()

    # 8. Store refresh token
    refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=refresh_expires_at,
    )
    db.add(refresh_token)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise ServiceError(
            "Failed to persist authentication state",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from e

    # 9. Return auth payload
    user_info = UserInfo(
        id=user.id,
        name=user.full_name,
        email=user.email,
        role=user.role,
    )
    tenant_info = TenantInfo(
        id=tenant.id,
        organization_code=tenant.organization_code,
        organization_name=tenant.organization_name,
        organization_type=tenant.organization_type,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user=user_info,
        tenant=tenant_info,
        modules=modules,
        issued_at=issued_at,
    )

