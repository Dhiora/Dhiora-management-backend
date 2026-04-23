"""
Migration 018: Create school.ai_whisper_usage table for Whisper audio minutes tracking.

Run once:
  python -m app.db.migrations.018_add_ai_whisper_usage_table
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_AI_WHISPER_USAGE = """
CREATE TABLE IF NOT EXISTS school.ai_whisper_usage (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    teacher_id            UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    lecture_session_id    UUID REFERENCES school.ai_lecture_sessions(id) ON DELETE SET NULL,
    usage_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    audio_duration_seconds FLOAT NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(CREATE_AI_WHISPER_USAGE))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_whisper_usage_tenant_id "
            "ON school.ai_whisper_usage(tenant_id);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_whisper_usage_teacher_id "
            "ON school.ai_whisper_usage(teacher_id);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_whisper_usage_date "
            "ON school.ai_whisper_usage(usage_date);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_whisper_usage_tenant_date "
            "ON school.ai_whisper_usage(tenant_id, usage_date);"
        ))
    print("Migration 018: school.ai_whisper_usage table created successfully.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
