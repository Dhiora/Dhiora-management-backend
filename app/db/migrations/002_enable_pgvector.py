"""
Migration: Enable pgvector extension.

Run once:
  python -m app.db.migrations.002_enable_pgvector
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


ENABLE_EXTENSION = """
CREATE EXTENSION IF NOT EXISTS vector;
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(ENABLE_EXTENSION))

    print("Migration 002_enable_pgvector done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))

