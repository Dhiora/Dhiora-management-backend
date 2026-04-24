"""
Migration 021: Create core.leads table for website visitor lead capture.

Run once:
  python -m app.db.migrations.021_create_leads_table
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS core.leads (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              VARCHAR(64) NOT NULL UNIQUE,
    name                    VARCHAR(100),
    phone                   VARCHAR(30),
    email                   VARCHAR(200),
    status                  VARCHAR(20) NOT NULL DEFAULT 'new',
    total_tokens_used       INTEGER NOT NULL DEFAULT 0,
    conversation            JSONB NOT NULL DEFAULT '[]',
    notes                   TEXT,
    converted_at            TIMESTAMPTZ,
    converted_to_tenant_id  UUID REFERENCES core.tenants(id) ON DELETE SET NULL,
    source                  VARCHAR(50) NOT NULL DEFAULT 'website',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_leads_session_id ON core.leads(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_leads_status ON core.leads(status);",
    "CREATE INDEX IF NOT EXISTS idx_leads_created_at ON core.leads(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_leads_phone ON core.leads(phone) WHERE phone IS NOT NULL;",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(CREATE_SQL))
        for idx_sql in CREATE_INDEXES:
            await conn.execute(text(idx_sql))
    print("Migration 021: core.leads table created successfully.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
