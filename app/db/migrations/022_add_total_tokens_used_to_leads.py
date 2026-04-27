"""
Migration 022: Add total_tokens_used to core.leads for existing deployments.

Run once:
  python -m app.db.migrations.022_add_total_tokens_used_to_leads
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


ALTER_SQL = """
ALTER TABLE core.leads
ADD COLUMN IF NOT EXISTS total_tokens_used INTEGER NOT NULL DEFAULT 0;
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_leads_total_tokens_used
ON core.leads(total_tokens_used);
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(ALTER_SQL))
        await conn.execute(text(INDEX_SQL))
    print("Migration 022: total_tokens_used column ensured on core.leads.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
