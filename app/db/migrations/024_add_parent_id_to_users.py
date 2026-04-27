"""
Migration 024: add nullable auth.users.parent_id for parent-role linkage.

Run:
  python -m app.db.migrations.024_add_parent_id_to_users
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


SQL_BLOCKS = [
    """
    ALTER TABLE auth.users
    ADD COLUMN IF NOT EXISTS parent_id UUID NULL;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'fk_users_parent_id'
        ) THEN
            ALTER TABLE auth.users
            ADD CONSTRAINT fk_users_parent_id
            FOREIGN KEY (parent_id) REFERENCES school.parents(id) ON DELETE SET NULL;
        END IF;
    END $$;
    """,
    "CREATE INDEX IF NOT EXISTS idx_users_parent_id ON auth.users(parent_id);",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        for sql in SQL_BLOCKS:
            await conn.execute(text(sql.strip()))
    print("Migration 024: auth.users.parent_id added.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
