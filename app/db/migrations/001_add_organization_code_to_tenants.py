"""
Migration: Add organization_code to core.tenants.

- tenant_id (UUID) remains the internal primary key and only FK target.
- organization_code is a UNIQUE, NOT NULL public identifier (e.g. SCH-A3K9);
  never used as a foreign key. For login, imports, support, subdomain routing.

Run once (or use schema_check which runs this logic automatically):
  python -m app.db.migrations.001_add_organization_code_to_tenants

Equivalent to the ALTER + backfill in app.db.schema_check.
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.tenant_service import generate_organization_code_candidate
from app.db.session import engine


ALTER_ADD_COLUMN = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'core' AND table_name = 'tenants' AND column_name = 'organization_code'
    ) THEN
        ALTER TABLE core.tenants ADD COLUMN organization_code VARCHAR(20);
    END IF;
END $$;
"""

SET_NOT_NULL = """
DO $$
BEGIN
    ALTER TABLE core.tenants ALTER COLUMN organization_code SET NOT NULL;
EXCEPTION WHEN others THEN NULL;
END $$;
"""

ADD_UNIQUE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE n.nspname = 'core' AND t.relname = 'tenants' AND c.conname = 'uq_tenants_organization_code'
    ) THEN
        ALTER TABLE core.tenants ADD CONSTRAINT uq_tenants_organization_code UNIQUE (organization_code);
    END IF;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(ALTER_ADD_COLUMN))

    async with db_engine.connect() as backfill_conn:
        result = await backfill_conn.execute(
            text("SELECT id, organization_type FROM core.tenants WHERE organization_code IS NULL")
        )
        rows = result.mappings().all()
        for row in rows:
            tenant_id, org_type = row["id"], row["organization_type"]
            for _ in range(20):
                code = generate_organization_code_candidate(org_type or "Other")
                check = await backfill_conn.execute(
                    text("SELECT 1 FROM core.tenants WHERE organization_code = :c"),
                    {"c": code},
                )
                if check.scalar() is None:
                    await backfill_conn.execute(
                        text("UPDATE core.tenants SET organization_code = :c WHERE id = :id"),
                        {"c": code, "id": tenant_id},
                    )
                    await backfill_conn.commit()
                    break

    async with db_engine.begin() as conn:
        await conn.execute(text(SET_NOT_NULL))
        await conn.execute(text(ADD_UNIQUE))

    print("Migration 001_add_organization_code_to_tenants done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
