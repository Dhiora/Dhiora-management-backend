"""
Seed script to create the Platform tenant and the first PLATFORM_ADMIN user.

Run once (e.g. after schema_check) with env set:
  PLATFORM_ADMIN_EMAIL=admin@yourplatform.com
  PLATFORM_ADMIN_PASSWORD=YourSecurePassword

Creates:
- core.tenants: one row with organization_name = "Platform" (if not exists)
- auth.users: one user with role PLATFORM_ADMIN for that tenant (if email/password set)
- auth.roles: one row name PLATFORM_ADMIN for that tenant (optional; PLATFORM_ADMIN bypasses checks)
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role, User
from app.auth.security import hash_password
from app.core.config import settings
from app.core.models import Tenant
from app.core.tenant_service import generate_organization_code
from app.db.session import AsyncSessionLocal

PLATFORM_TENANT_NAME = "Platform"
PLATFORM_ORG_TYPE = "Platform"

# Default platform admin (used when PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD not set)
DEFAULT_PLATFORM_ADMIN_EMAIL = "Dhioragroups@gmail.com"
DEFAULT_PLATFORM_ADMIN_PASSWORD = "Dhiora@1610"
DEFAULT_PLATFORM_ADMIN_FULL_NAME = "Platform Admin"


async def seed_platform_admin(db: AsyncSession) -> None:
    # 1. Ensure Platform tenant exists
    stmt = select(Tenant).where(Tenant.organization_name == PLATFORM_TENANT_NAME)
    result = await db.execute(stmt)
    platform_tenant = result.scalar_one_or_none()
    if not platform_tenant:
        org_code = await generate_organization_code(db, PLATFORM_ORG_TYPE)
        platform_tenant = Tenant(
            organization_code=org_code,
            organization_name=PLATFORM_TENANT_NAME,
            organization_type=PLATFORM_ORG_TYPE,
            country="",
            timezone="UTC",
            status="ACTIVE",
        )
        db.add(platform_tenant)
        await db.flush()
        print("Created Platform tenant.")
    else:
        print("Platform tenant already exists.")

    email = settings.platform_admin_email or DEFAULT_PLATFORM_ADMIN_EMAIL
    password = settings.platform_admin_password or DEFAULT_PLATFORM_ADMIN_PASSWORD
    full_name = DEFAULT_PLATFORM_ADMIN_FULL_NAME
    if not email or not password:
        await db.commit()
        print("No platform admin email/password; skipping platform admin user.")
        return

    # 2. Create or update PLATFORM_ADMIN user for this tenant
    user_stmt = select(User).where(
        User.tenant_id == platform_tenant.id,
        User.email == email,
    )
    user_result = await db.execute(user_stmt)
    platform_user = user_result.scalar_one_or_none()
    if not platform_user:
        platform_user = User(
            tenant_id=platform_tenant.id,
            full_name=full_name,
            email=email,
            mobile=None,
            password_hash=hash_password(password),
            role="PLATFORM_ADMIN",
            status="ACTIVE",
            source="SYSTEM",
        )
        db.add(platform_user)
        await db.flush()
        print("Created PLATFORM_ADMIN user:", email)
    else:
        platform_user.role = "PLATFORM_ADMIN"
        platform_user.password_hash = hash_password(password)
        platform_user.full_name = full_name
        print("Updated existing user to PLATFORM_ADMIN:", email)

    # 3. Ensure PLATFORM_ADMIN role row exists (for consistency; RBAC bypasses check for this role)
    role_stmt = select(Role).where(
        Role.tenant_id == platform_tenant.id,
        Role.name == "PLATFORM_ADMIN",
    )
    role_result = await db.execute(role_stmt)
    if role_result.scalar_one_or_none() is None:
        db.add(
            Role(
                tenant_id=platform_tenant.id,
                name="PLATFORM_ADMIN",
                permissions={"roles": {"create": True, "read": True, "update": True, "delete": True}},
            )
        )
        print("Created PLATFORM_ADMIN role row.")

    await db.commit()
    print("Platform admin seed done.")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        try:
            await seed_platform_admin(db)
        except Exception as e:
            await db.rollback()
            print("Error:", e)
            raise


if __name__ == "__main__":
    asyncio.run(main())
