"""
Migration 007: Add session_stage to school.ai_doubt_chats (for ULTRA tier).

Run once:
  python -m app.db.migrations.007_ai_doubt_chat_session_stage
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


ALTER_AI_DOUBT_CHATS_SESSION_STAGE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'school' AND table_name = 'ai_doubt_chats'
        AND column_name = 'session_stage'
    ) THEN
        ALTER TABLE school.ai_doubt_chats ADD COLUMN session_stage VARCHAR(50);
    END IF;
END $$;
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(ALTER_AI_DOUBT_CHATS_SESSION_STAGE))
    print("Migration 007_ai_doubt_chat_session_stage done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
