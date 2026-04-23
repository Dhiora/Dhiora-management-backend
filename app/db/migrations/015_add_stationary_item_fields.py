"""Migration 015: Add new fields to stationary.items and rename quantity_available -> stock_quantity."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine

_STATEMENTS = [
    "ALTER TABLE stationary.items RENAME COLUMN quantity_available TO stock_quantity",
    "ALTER TABLE stationary.items ADD COLUMN IF NOT EXISTS brand VARCHAR(150)",
    "ALTER TABLE stationary.items ADD COLUMN IF NOT EXISTS original_price NUMERIC(10, 2)",
    "ALTER TABLE stationary.items ADD COLUMN IF NOT EXISTS class_level VARCHAR(50)",
    "ALTER TABLE stationary.items ADD COLUMN IF NOT EXISTS academic_year VARCHAR(20)",
    "ALTER TABLE stationary.items ADD COLUMN IF NOT EXISTS condition VARCHAR(20)",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        for stmt in _STATEMENTS:
            await conn.execute(text(stmt))
    print("Migration 015_add_stationary_item_fields done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
