"""
Migration: Add upload/processing fields to ai_lecture_sessions.

Adds: upload_completed, audio_file_path, processing_stage,
      last_chunk_received_at, upload_progress_percent.

Run once:
  python -m app.db.migrations.005_ai_lecture_session_upload_fields
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


ALTER_AI_LECTURE_SESSIONS_UPLOAD = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'school' AND table_name = 'ai_lecture_sessions'
                   AND column_name = 'upload_completed') THEN
        ALTER TABLE school.ai_lecture_sessions ADD COLUMN upload_completed BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'school' AND table_name = 'ai_lecture_sessions'
                   AND column_name = 'audio_file_path') THEN
        ALTER TABLE school.ai_lecture_sessions ADD COLUMN audio_file_path VARCHAR(1024);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'school' AND table_name = 'ai_lecture_sessions'
                   AND column_name = 'processing_stage') THEN
        ALTER TABLE school.ai_lecture_sessions ADD COLUMN processing_stage VARCHAR(50);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'school' AND table_name = 'ai_lecture_sessions'
                   AND column_name = 'last_chunk_received_at') THEN
        ALTER TABLE school.ai_lecture_sessions ADD COLUMN last_chunk_received_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'school' AND table_name = 'ai_lecture_sessions'
                   AND column_name = 'upload_progress_percent') THEN
        ALTER TABLE school.ai_lecture_sessions ADD COLUMN upload_progress_percent INTEGER NOT NULL DEFAULT 0;
    END IF;
END $$;
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(ALTER_AI_LECTURE_SESSIONS_UPLOAD))
    print("Migration 005_ai_lecture_session_upload_fields done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
