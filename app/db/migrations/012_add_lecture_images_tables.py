"""
Migration: Add board image annotation tables.

Creates:
- school.ai_lecture_images
- school.ai_image_regions

Run once:
  python -m app.db.migrations.012_add_lecture_images_tables
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_AI_LECTURE_IMAGES_TABLE = """
CREATE TABLE IF NOT EXISTS school.ai_lecture_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    lecture_id UUID NOT NULL REFERENCES school.ai_lecture_sessions(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES school.ai_lecture_chunks(id) ON DELETE SET NULL,
    image_url VARCHAR(1024) NOT NULL,
    sequence_order INTEGER NOT NULL DEFAULT 0,
    topic_label VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_AI_LECTURE_IMAGES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_images_tenant_id ON school.ai_lecture_images(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_images_lecture_id ON school.ai_lecture_images(lecture_id);",
    "CREATE INDEX IF NOT EXISTS idx_ai_lecture_images_chunk_id ON school.ai_lecture_images(chunk_id);",
]

CREATE_AI_IMAGE_REGIONS_TABLE = """
CREATE TABLE IF NOT EXISTS school.ai_image_regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_image_id UUID NOT NULL REFERENCES school.ai_lecture_images(id) ON DELETE CASCADE,
    label VARCHAR(255) NOT NULL,
    x FLOAT NOT NULL,
    y FLOAT NOT NULL,
    w FLOAT NOT NULL,
    h FLOAT NOT NULL,
    color_hex VARCHAR(10) DEFAULT '#EF9F27',
    description VARCHAR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_AI_IMAGE_REGIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ai_image_regions_lecture_image_id ON school.ai_image_regions(lecture_image_id);",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(CREATE_AI_LECTURE_IMAGES_TABLE))
        for idx_sql in CREATE_AI_LECTURE_IMAGES_INDEXES:
            await conn.execute(text(idx_sql))

        await conn.execute(text(CREATE_AI_IMAGE_REGIONS_TABLE))
        for idx_sql in CREATE_AI_IMAGE_REGIONS_INDEXES:
            await conn.execute(text(idx_sql))

    print("Migration 012_add_lecture_images_tables done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
