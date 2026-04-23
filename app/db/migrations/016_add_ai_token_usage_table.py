"""
Migration 016: Create school.ai_token_usage table for per-request AI token tracking.

Run once:
  python -m app.db.migrations.016_add_ai_token_usage_table
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_AI_TOKEN_USAGE = """
CREATE TABLE IF NOT EXISTS school.ai_token_usage (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    student_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    chat_id        UUID REFERENCES school.ai_doubt_chats(id) ON DELETE SET NULL,
    usage_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    total_tokens   INTEGER NOT NULL DEFAULT 0,
    model_used     VARCHAR(100),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(CREATE_AI_TOKEN_USAGE))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_token_usage_tenant_id "
            "ON school.ai_token_usage(tenant_id);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_token_usage_student_id "
            "ON school.ai_token_usage(student_id);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_token_usage_usage_date "
            "ON school.ai_token_usage(usage_date);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ai_token_usage_tenant_date "
            "ON school.ai_token_usage(tenant_id, usage_date);"
        ))
    print("Migration 016: school.ai_token_usage table created successfully.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
