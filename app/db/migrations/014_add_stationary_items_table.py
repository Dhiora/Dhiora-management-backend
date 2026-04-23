"""Migration 014: Add stationary.items table for school management catalog."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine

_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS stationary.items (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id           UUID            NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        name                VARCHAR(255)    NOT NULL,
        description         TEXT,
        category            VARCHAR(100)    NOT NULL,
        unit                VARCHAR(50)     NOT NULL DEFAULT 'per piece',
        price               NUMERIC(10, 2)  NOT NULL CHECK (price >= 0),
        quantity_available  INTEGER         NOT NULL DEFAULT 0 CHECK (quantity_available >= 0),
        images              JSONB           NOT NULL DEFAULT '[]',
        is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
        created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    )""",

    """CREATE INDEX IF NOT EXISTS idx_stationary_items_tenant
        ON stationary.items (tenant_id)""",

    """CREATE INDEX IF NOT EXISTS idx_stationary_items_category
        ON stationary.items (tenant_id, category)
        WHERE is_active = TRUE""",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        for stmt in _STATEMENTS:
            await conn.execute(text(stmt))
    print("Migration 014_add_stationary_items_table done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
