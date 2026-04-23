"""
Migration 017: Create admin@dhiora.com as PLATFORM_ADMIN under the Dhiora Platform tenant.

Run once:
  python -m app.db.migrations.017_create_platform_admin
"""

import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.models import Role, User
from app.auth.security import hash_password
from app.core.models import Tenant
from app.db.session import engine, AsyncSessionLocal


PLATFORM_ADMIN_EMAIL = "admin@dhiora.com"
PLATFORM_ADMIN_PASSWORD = "Dhiora@1610"
PLATFORM_ADMIN_FULL_NAME = "Dhiora Super Admin"
PLATFORM_TENANT_NAME = "Dhiora Platform"
PLATFORM_ORG_CODE = "DHIORA-PLATFORM"


async def run_migration() -> None:
    async with AsyncSessionLocal() as db:
        # 1. Ensure platform tenant exists
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.organization_code == PLATFORM_ORG_CODE)
        )
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            tenant = Tenant(
                organization_code=PLATFORM_ORG_CODE,
                org_short_code="DHIORA",
                organization_name=PLATFORM_TENANT_NAME,
                organization_type="Platform",
                country="India",
                timezone="Asia/Kolkata",
                status="ACTIVE",
            )
            db.add(tenant)
            await db.flush()
            print(f"Created Dhiora Platform tenant (id={tenant.id}).")
        else:
            print(f"Dhiora Platform tenant already exists (id={tenant.id}).")

        # 2. Check if admin@dhiora.com already exists
        user_result = await db.execute(
            select(User).where(User.email == PLATFORM_ADMIN_EMAIL)
        )
        existing_user = user_result.scalar_one_or_none()

        if existing_user:
            # Update password and ensure PLATFORM_ADMIN role
            existing_user.password_hash = hash_password(PLATFORM_ADMIN_PASSWORD)
            existing_user.role = "PLATFORM_ADMIN"
            existing_user.status = "ACTIVE"
            print(f"Updated existing user {PLATFORM_ADMIN_EMAIL} to PLATFORM_ADMIN.")
        else:
            new_user = User(
                tenant_id=tenant.id,
                full_name=PLATFORM_ADMIN_FULL_NAME,
                email=PLATFORM_ADMIN_EMAIL,
                mobile=None,
                password_hash=hash_password(PLATFORM_ADMIN_PASSWORD),
                role="PLATFORM_ADMIN",
                status="ACTIVE",
                source="SYSTEM",
            )
            db.add(new_user)
            print(f"Created PLATFORM_ADMIN user: {PLATFORM_ADMIN_EMAIL}")

        # 3. Ensure PLATFORM_ADMIN role row exists for this tenant
        role_result = await db.execute(
            select(Role).where(
                Role.tenant_id == tenant.id,
                Role.name == "PLATFORM_ADMIN",
            )
        )
        if role_result.scalar_one_or_none() is None:
            db.add(
                Role(
                    tenant_id=tenant.id,
                    name="PLATFORM_ADMIN",
                    permissions={},
                )
            )
            print("Created PLATFORM_ADMIN role row.")

        await db.commit()
        print("Migration 017 complete: admin@dhiora.com is ready.")


if __name__ == "__main__":
    asyncio.run(run_migration())
