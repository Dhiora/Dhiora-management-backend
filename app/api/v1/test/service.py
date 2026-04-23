"""Test-only services: full DB truncate and full-access org registration."""

from datetime import datetime, timezone
from typing import List

from fastapi import status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import RegisterResponse
from app.auth.security import hash_password
from app.core.exceptions import ServiceError
from app.core.models import Tenant, TenantModule, TenantSubscription
from app.core.services import get_modules_by_organization_type
from app.core.tenant_service import generate_organization_code

from .schemas import ResetDatabaseResponse, TestFullAccessRegisterRequest

# Application schemas that own business tables (PostgreSQL).
_TRUNCATE_SCHEMAS = ("core", "auth", "school", "leave", "hrms", "asset")


async def truncate_all_application_tables(db: AsyncSession) -> ResetDatabaseResponse:
    """Remove all rows from application tables using TRUNCATE ... CASCADE."""
    result = await db.execute(
        text(
            """
            SELECT string_agg(
                format('%I.%I', schemaname, tablename),
                ', ' ORDER BY schemaname, tablename
            )
            FROM pg_tables
            WHERE schemaname = ANY(:schemas)
            """
        ),
        {"schemas": list(_TRUNCATE_SCHEMAS)},
    )
    tables_str = result.scalar_one_or_none()
    if not tables_str:
        await db.commit()
        return ResetDatabaseResponse(
            success=True,
            message="No tables found to truncate.",
            tables_truncated=0,
        )

    await db.execute(text(f"TRUNCATE {tables_str} RESTART IDENTITY CASCADE"))
    await db.commit()
    table_count = tables_str.count(",") + 1
    return ResetDatabaseResponse(
        success=True,
        message=(
            "All application table data was removed. "
            "Re-run module seeds (e.g. app.db.seed_modules) before registering tenants."
        ),
        tables_truncated=table_count,
    )


async def register_organization_full_access_free(
    db: AsyncSession, payload: TestFullAccessRegisterRequest
) -> RegisterResponse:
    """Create tenant, enable all modules for the org type, super admin, and ACTIVE ERP/AI subscriptions with no plan/fee."""
    existing_user_stmt = select(User).where(User.email == payload.admin_email)
    existing_user_result = await db.execute(existing_user_stmt)
    if existing_user_result.scalar_one_or_none():
        raise ServiceError("Email is already in use", status.HTTP_409_CONFLICT)

    try:
        mod_response = await get_modules_by_organization_type(db, payload.organization_type.value)
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(
            "Failed to load modules for organization type",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from e

    module_keys: List[str] = []
    for entry in mod_response.modules:
        if entry.is_enabled:
            module_keys.append(entry.module.module_key)
    module_keys = list(dict.fromkeys(module_keys))
    if not module_keys:
        raise ServiceError(
            "No enabled modules for this organization type. Seed core.modules and organization_type_modules first.",
            status.HTTP_400_BAD_REQUEST,
        )

    try:
        organization_code = await generate_organization_code(db, payload.organization_type.value)
        org_short_code = (
            payload.org_short_code.strip().upper()[:10]
            if payload.org_short_code and payload.org_short_code.strip()
            else None
        )
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
        await db.flush()

        for key in module_keys:
            db.add(
                TenantModule(
                    tenant_id=tenant.id,
                    module_key=key,
                    is_enabled=True,
                )
            )

        db.add(
            User(
                tenant_id=tenant.id,
                full_name=payload.admin_full_name,
                email=payload.admin_email,
                mobile=payload.admin_mobile,
                password_hash=hash_password(payload.password),
                role="SUPER_ADMIN",
                status="ACTIVE",
                source="SYSTEM",
            )
        )

        now = datetime.now(timezone.utc)
        for category in ("ERP", "AI"):
            db.add(
                TenantSubscription(
                    tenant_id=tenant.id,
                    subscription_plan_id=None,
                    category=category,
                    status="ACTIVE",
                    activated_at=now,
                )
            )

        await db.commit()
        await db.refresh(tenant)
    except IntegrityError as e:
        await db.rollback()
        raise ServiceError(
            "Conflict while creating tenant or user", status.HTTP_409_CONFLICT
        ) from e
    except ServiceError:
        raise
    except Exception as e:
        await db.rollback()
        raise ServiceError(
            "Failed to create account", status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from e

    return RegisterResponse(
        success=True,
        message="Account created with full module access and no subscription fee",
        tenant_id=tenant.id,
        organization_code=tenant.organization_code,
        org_short_code=tenant.org_short_code,
    )
