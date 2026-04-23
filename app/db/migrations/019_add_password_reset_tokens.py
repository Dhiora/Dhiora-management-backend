"""
Migration 019: Create auth.password_reset_tokens table.

Run once:
  python -m app.db.migrations.019_add_password_reset_tokens
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_PASSWORD_RESET_TOKENS = """
CREATE TABLE IF NOT EXISTS auth.password_reset_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token       VARCHAR(128) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(CREATE_PASSWORD_RESET_TOKENS))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_prt_user_id "
            "ON auth.password_reset_tokens(user_id);"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_prt_token "
            "ON auth.password_reset_tokens(token);"
        ))
    print("Migration 019: auth.password_reset_tokens table created successfully.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
