"""Service layer for School Profile API."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models.school_profile import SchoolProfile
from app.core.models.tenant import Tenant

from .schemas import SchoolProfilePlatformUpdate, SchoolProfileResponse, SchoolProfileUpdate


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_create_profile(db: AsyncSession, tenant_id: UUID) -> SchoolProfile:
    result = await db.execute(
        select(SchoolProfile).where(SchoolProfile.tenant_id == tenant_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = SchoolProfile(tenant_id=tenant_id)
        db.add(profile)
        await db.flush()
    return profile


def _build_response(tenant: Tenant, profile: SchoolProfile) -> SchoolProfileResponse:
    return SchoolProfileResponse(
        tenant_id=tenant.id,
        organization_code=tenant.organization_code,
        organization_name=tenant.organization_name,
        organization_type=tenant.organization_type,
        country=tenant.country,
        timezone=tenant.timezone,
        status=tenant.status,
        org_short_code=getattr(tenant, "org_short_code", None),
        logo_url=profile.logo_url,
        address_line1=profile.address_line1,
        address_line2=profile.address_line2,
        city=profile.city,
        state=profile.state,
        pincode=profile.pincode,
        phone=profile.phone,
        website=profile.website,
        principal_name=profile.principal_name,
        established_year=profile.established_year,
        affiliation_board=profile.affiliation_board,
        created_at=tenant.created_at,
        updated_at=profile.updated_at,
    )


async def _has_active_employees(db: AsyncSession, tenant_id: UUID) -> bool:
    result = await db.execute(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.user_type == "employee",
            User.status == "ACTIVE",
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


# ── Read ──────────────────────────────────────────────────────────────────────

async def get_school_profile(db: AsyncSession, tenant_id: UUID) -> SchoolProfileResponse:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise ServiceError("School not found", status.HTTP_404_NOT_FOUND)
    profile = await _get_or_create_profile(db, tenant_id)
    await db.commit()
    return _build_response(tenant, profile)


# ── Update (school admin / role-permitted) ────────────────────────────────────

async def update_school_profile(
    db: AsyncSession,
    tenant_id: UUID,
    payload: SchoolProfileUpdate,
) -> SchoolProfileResponse:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise ServiceError("School not found", status.HTTP_404_NOT_FOUND)

    if payload.organization_name is not None:
        tenant.organization_name = payload.organization_name

    if payload.timezone is not None:
        tenant.timezone = payload.timezone

    if payload.org_short_code is not None:
        if tenant.org_short_code and tenant.org_short_code != payload.org_short_code:
            if await _has_active_employees(db, tenant_id):
                raise ServiceError(
                    "org_short_code cannot be changed after employees exist",
                    status.HTTP_409_CONFLICT,
                )
        tenant.org_short_code = payload.org_short_code.upper() if payload.org_short_code else None

    profile = await _get_or_create_profile(db, tenant_id)
    _apply_profile_fields(profile, payload)

    await db.commit()
    await db.refresh(tenant)
    await db.refresh(profile)
    return _build_response(tenant, profile)


# ── Update (platform admin) ───────────────────────────────────────────────────

async def update_school_profile_platform(
    db: AsyncSession,
    tenant_id: UUID,
    payload: SchoolProfilePlatformUpdate,
) -> SchoolProfileResponse:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise ServiceError("School not found", status.HTTP_404_NOT_FOUND)

    # Regular fields
    if payload.organization_name is not None:
        tenant.organization_name = payload.organization_name
    if payload.timezone is not None:
        tenant.timezone = payload.timezone
    if payload.org_short_code is not None:
        tenant.org_short_code = payload.org_short_code.upper() if payload.org_short_code else None

    # Privileged fields (platform admin only)
    if payload.organization_type is not None:
        tenant.organization_type = payload.organization_type
    if payload.country is not None:
        tenant.country = payload.country
    if payload.status is not None:
        allowed_statuses = {"ACTIVE", "INACTIVE", "SUSPENDED"}
        if payload.status.upper() not in allowed_statuses:
            raise ServiceError(
                f"Invalid status. Allowed: {', '.join(allowed_statuses)}",
                status.HTTP_400_BAD_REQUEST,
            )
        tenant.status = payload.status.upper()

    profile = await _get_or_create_profile(db, tenant_id)
    _apply_profile_fields(profile, payload)

    await db.commit()
    await db.refresh(tenant)
    await db.refresh(profile)
    return _build_response(tenant, profile)


# ── Shared field applicator ───────────────────────────────────────────────────

def _apply_profile_fields(profile: SchoolProfile, payload: SchoolProfileUpdate) -> None:
    field_map = (
        "logo_url",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "pincode",
        "phone",
        "website",
        "principal_name",
        "established_year",
        "affiliation_board",
    )
    for field in field_map:
        value = getattr(payload, field, None)
        if value is not None:
            setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)
