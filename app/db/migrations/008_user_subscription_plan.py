"""
Migration 008: Add subscription_plan to auth.users for AI doubt tiers (BASIC | PRO | ULTRA).

Run once:
  python -m app.db.migrations.008_user_subscription_plan
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


ALTER_USERS_SUBSCRIPTION_PLAN = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'auth'
          AND table_name = 'users'
          AND column_name = 'subscription_plan'
    ) THEN
        ALTER TABLE auth.users ADD COLUMN subscription_plan VARCHAR(50);
    END IF;
END $$;
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(ALTER_USERS_SUBSCRIPTION_PLAN))
    print("Migration 008_user_subscription_plan done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
