"""
Migration: Create AI Classroom tables.

Creates:
- school.ai_lecture_sessions
- school.ai_lecture_chunks (with pgvector)
- school.ai_doubt_chats
- school.ai_doubt_messages

Run once:
  python -m app.db.migrations.003_create_ai_classroom_tables
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_AI_LECTURE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS school.ai_lecture_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
    class_id UUID NOT NULL REFERENCES core.classes(id) ON DELETE RESTRICT,
    section_id UUID REFERENCES core.sections(id) ON DELETE RESTRICT,
    subject_id UUID NOT NULL REFERENCES school.subjects(id) ON DELETE RESTRICT,
    teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    transcript TEXT NOT NULL DEFAULT '',
    structured_notes JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'IDLE',
    recording_started_at TIMESTAMPTZ,
    recording_paused_at TIMESTAMPTZ,
    total_recording_seconds INTEGER NOT NULL DEFAULT 0,
    is_active_recording BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_AI_LECTURE_SESSIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_sessions_tenant_id ON school.ai_lecture_sessions(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_sessions_teacher_id ON school.ai_lecture_sessions(teacher_id);",
]

CREATE_AI_LECTURE_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS school.ai_lecture_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    lecture_id UUID NOT NULL REFERENCES school.ai_lecture_sessions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_AI_LECTURE_CHUNKS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_chunks_tenant_id ON school.ai_lecture_chunks(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_chunks_lecture_id ON school.ai_lecture_chunks(lecture_id);",
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_chunks_embedding ON school.ai_lecture_chunks USING ivfflat (embedding vector_l2_ops);",
]

CREATE_AI_DOUBT_CHATS_TABLE = """
CREATE TABLE IF NOT EXISTS school.ai_doubt_chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    lecture_id UUID NOT NULL REFERENCES school.ai_lecture_sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_AI_DOUBT_CHATS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ai_doubt_chats_tenant_id ON school.ai_doubt_chats(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_ai_doubt_chats_student_id ON school.ai_doubt_chats(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_ai_doubt_chats_lecture_id ON school.ai_doubt_chats(lecture_id);",
]

CREATE_AI_DOUBT_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS school.ai_doubt_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES school.ai_doubt_chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_AI_DOUBT_MESSAGES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ai_doubt_messages_chat_id ON school.ai_doubt_messages(chat_id);",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        # Ensure pgvector extension is enabled
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        
        # Create ai_lecture_sessions table
        await conn.execute(text(CREATE_AI_LECTURE_SESSIONS_TABLE))
        for index_sql in CREATE_AI_LECTURE_SESSIONS_INDEXES:
            await conn.execute(text(index_sql))
        
        # Create ai_lecture_chunks table
        await conn.execute(text(CREATE_AI_LECTURE_CHUNKS_TABLE))
        for index_sql in CREATE_AI_LECTURE_CHUNKS_INDEXES:
            await conn.execute(text(index_sql))
        
        # Create ai_doubt_chats table
        await conn.execute(text(CREATE_AI_DOUBT_CHATS_TABLE))
        for index_sql in CREATE_AI_DOUBT_CHATS_INDEXES:
            await conn.execute(text(index_sql))
        
        # Create ai_doubt_messages table
        await conn.execute(text(CREATE_AI_DOUBT_MESSAGES_TABLE))
        for index_sql in CREATE_AI_DOUBT_MESSAGES_INDEXES:
            await conn.execute(text(index_sql))

    print("Migration 003_create_ai_classroom_tables done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))

