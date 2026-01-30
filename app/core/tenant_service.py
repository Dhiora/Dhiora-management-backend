"""
Tenant service: organization_code generation and lookup.

- organization_code is a human-readable public identifier (e.g. SCH-A3K9).
- tenant_id (UUID) remains the only primary key and FK target; organization_code
  is never used as a foreign key.
"""
import secrets
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import Tenant
from fastapi import HTTPException, status


# Pattern by tenant type: School → SCH-XXXX, Software → CMP-XXXX, etc.
# Uppercase, short, non-guessable suffix (alphanumeric).
ORG_TYPE_PREFIX_MAP = {
    "School": "SCH",
    "College": "COL",
    "Software Company": "CMP",
    "Sales Organization": "SAL",
    "Hospital": "HOS",
    "Shopping Mall": "SHP",
    "Platform": "PLT",
    "Other": "ORG",
}
DEFAULT_PREFIX = "ORG"


def _prefix_for_organization_type(organization_type: str) -> str:
    """Return 3-letter uppercase prefix for organization_code (e.g. SCH, CMP)."""
    return ORG_TYPE_PREFIX_MAP.get(organization_type, DEFAULT_PREFIX)


def generate_organization_code_candidate(organization_type: str) -> str:
    """
    Generate a single candidate organization code (no DB check).
    Uppercase, short, non-guessable: PREFIX-XXXX (4 alphanumeric chars).
    """
    prefix = _prefix_for_organization_type(organization_type)
    # Non-guessable suffix: 4 uppercase alphanumeric
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # exclude ambiguous 0/O, 1/I
    suffix = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"{prefix}-{suffix}"


async def generate_organization_code(
    db: AsyncSession,
    organization_type: str,
    max_attempts: int = 20,
) -> str:
    """
    Generate a unique organization_code for the given organization type.
    Ensures uniqueness before returning (retries with new suffix on collision).
    """
    for _ in range(max_attempts):
        code = generate_organization_code_candidate(organization_type)
        result = await db.execute(
            select(Tenant.id).where(Tenant.organization_code == code)
        )
        if result.scalar_one_or_none() is None:
            return code
    raise ServiceError(
        "Could not generate unique organization code",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def get_tenant_by_organization_code(
    db: AsyncSession,
    code: str,
) -> Optional[Tenant]:
    """
    Fetch tenant by organization_code (public identifier).
    Returns the tenant or None if not found. Use for login, imports, support, subdomain routing.
    Caller should raise 404 if None is returned.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.organization_code == code.strip().upper())
    )
    return result.scalar_one_or_none()


async def get_tenant_id_by_organization_code(
    db: AsyncSession,
    code: str,
) -> Optional[UUID]:
    """
    Fetch tenant_id by organization_code. Returns UUID or None.
    Use when only tenant_id is needed (e.g. login flow).
    """
    tenant = await get_tenant_by_organization_code(db, code)
    return tenant.id if tenant else None


async def get_tenant_by_organization_code_or_404(
    db: AsyncSession,
    code: str,
) -> Tenant:
    """
    Fetch tenant by organization_code; raise 404 if not found.
    Use for login flow, imports, support, subdomain routing.
    """
    tenant = await get_tenant_by_organization_code(db, code)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return tenant
