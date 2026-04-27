"""
Migration 023: Parent Portal tables.

Tables created (all in school schema):
  - school.parents
  - school.parent_student_links
  - school.parent_notifications
  - school.notification_preferences
  - school.message_threads
  - school.messages

Run once:
  python -m app.db.migrations.023_create_parent_portal_tables
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


SQL_BLOCKS = [
    # Parents
    """
    CREATE TABLE IF NOT EXISTS school.parents (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id   UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        full_name   VARCHAR(255) NOT NULL,
        phone       VARCHAR(50),
        email       VARCHAR(255) NOT NULL,
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (tenant_id, email)
    );
    """,

    "CREATE INDEX IF NOT EXISTS idx_parents_tenant ON school.parents(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_parents_user_id ON school.parents(user_id);",

    # Parent-student links
    """
    CREATE TABLE IF NOT EXISTS school.parent_student_links (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        parent_id   UUID NOT NULL REFERENCES school.parents(id) ON DELETE CASCADE,
        student_id  UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        relation    VARCHAR(20) NOT NULL CHECK (relation IN ('father','mother','guardian')),
        is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (parent_id, student_id)
    );
    """,

    "CREATE INDEX IF NOT EXISTS idx_psl_parent ON school.parent_student_links(parent_id);",
    "CREATE INDEX IF NOT EXISTS idx_psl_student ON school.parent_student_links(student_id);",

    # Notification preferences
    """
    CREATE TABLE IF NOT EXISTS school.notification_preferences (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        parent_id       UUID NOT NULL UNIQUE REFERENCES school.parents(id) ON DELETE CASCADE,
        sms_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
        email_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
        push_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
        types_muted     JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,

    # Parent notifications
    """
    CREATE TABLE IF NOT EXISTS school.parent_notifications (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id   UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        parent_id   UUID NOT NULL REFERENCES school.parents(id) ON DELETE CASCADE,
        student_id  UUID REFERENCES auth.users(id) ON DELETE CASCADE,
        type        VARCHAR(50) NOT NULL CHECK (type IN (
                        'attendance_absent','fee_due','homework_due',
                        'exam_schedule','circular','general'
                    )),
        title       VARCHAR(255) NOT NULL,
        body        TEXT NOT NULL,
        is_read     BOOLEAN NOT NULL DEFAULT FALSE,
        sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,

    "CREATE INDEX IF NOT EXISTS idx_pn_parent ON school.parent_notifications(parent_id);",
    "CREATE INDEX IF NOT EXISTS idx_pn_tenant ON school.parent_notifications(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_pn_sent_at ON school.parent_notifications(sent_at DESC);",

    # Message threads
    """
    CREATE TABLE IF NOT EXISTS school.message_threads (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        parent_id       UUID NOT NULL REFERENCES school.parents(id) ON DELETE CASCADE,
        teacher_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        student_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        subject         VARCHAR(255) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,

    "CREATE INDEX IF NOT EXISTS idx_mt_parent ON school.message_threads(parent_id);",
    "CREATE INDEX IF NOT EXISTS idx_mt_teacher ON school.message_threads(teacher_id);",
    "CREATE INDEX IF NOT EXISTS idx_mt_tenant ON school.message_threads(tenant_id);",

    # Messages
    """
    CREATE TABLE IF NOT EXISTS school.messages (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        thread_id   UUID NOT NULL REFERENCES school.message_threads(id) ON DELETE CASCADE,
        sender_role VARCHAR(20) NOT NULL CHECK (sender_role IN ('parent','teacher')),
        sender_id   UUID NOT NULL,
        body        TEXT NOT NULL,
        sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_read     BOOLEAN NOT NULL DEFAULT FALSE
    );
    """,

    "CREATE INDEX IF NOT EXISTS idx_msg_thread ON school.messages(thread_id);",
    "CREATE INDEX IF NOT EXISTS idx_msg_sent_at ON school.messages(sent_at);",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        for sql in SQL_BLOCKS:
            await conn.execute(text(sql.strip()))
    print("Migration 023: Parent Portal tables created successfully.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
