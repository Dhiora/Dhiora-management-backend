"""
Migration 020: Create core.school_profiles table.

Run once:
  python -m app.db.migrations.020_add_school_profile_table
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS core.school_profiles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    logo_url         TEXT,
    address_line1    VARCHAR(255),
    address_line2    VARCHAR(255),
    city             VARCHAR(100),
    state            VARCHAR(100),
    pincode          VARCHAR(20),
    phone            VARCHAR(50),
    website          VARCHAR(255),
    principal_name   VARCHAR(255),
    established_year VARCHAR(10),
    affiliation_board VARCHAR(100),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_school_profile_tenant UNIQUE (tenant_id)
);
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(CREATE_SQL))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_school_profiles_tenant_id "
            "ON core.school_profiles(tenant_id);"
        ))
    print("Migration 020: core.school_profiles table created successfully.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
