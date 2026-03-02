"""
Migration: Add audio_buffer_size_bytes column to ai_lecture_sessions.

Run once:
  python -m app.db.migrations.004_add_audio_buffer_size_to_lecture_sessions
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


ADD_AUDIO_BUFFER_SIZE_COLUMN = """
ALTER TABLE school.ai_lecture_sessions
ADD COLUMN IF NOT EXISTS audio_buffer_size_bytes INTEGER NOT NULL DEFAULT 0;
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(ADD_AUDIO_BUFFER_SIZE_COLUMN))
    print("Migration 004_add_audio_buffer_size_to_lecture_sessions done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))

