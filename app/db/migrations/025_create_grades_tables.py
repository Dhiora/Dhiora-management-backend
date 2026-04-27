"""
Migration 025: Create grade_scales and exam_marks tables.

Run:
  python -m app.db.migrations.025_create_grades_tables
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine

SQL_BLOCKS = [
    """
    CREATE TABLE IF NOT EXISTS school.grade_scales (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        label           VARCHAR(10) NOT NULL,
        min_percentage  NUMERIC(5,2) NOT NULL,
        max_percentage  NUMERIC(5,2) NOT NULL,
        gpa_points      NUMERIC(4,2),
        remarks         TEXT,
        display_order   INTEGER NOT NULL DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_grade_scales_tenant ON school.grade_scales(tenant_id);",
    """
    CREATE TABLE IF NOT EXISTS school.exam_marks (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        exam_id         UUID NOT NULL REFERENCES school.exams(id) ON DELETE CASCADE,
        student_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        subject_id      UUID NOT NULL REFERENCES school.subjects(id) ON DELETE RESTRICT,
        class_id        UUID NOT NULL REFERENCES core.classes(id) ON DELETE CASCADE,
        section_id      UUID REFERENCES core.sections(id) ON DELETE SET NULL,
        marks_obtained  NUMERIC(6,2),
        max_marks       NUMERIC(6,2) NOT NULL DEFAULT 100,
        is_absent       BOOLEAN NOT NULL DEFAULT FALSE,
        remarks         TEXT,
        entered_by      UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_exam_mark UNIQUE (exam_id, student_id, subject_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_exam_marks_exam ON school.exam_marks(exam_id);",
    "CREATE INDEX IF NOT EXISTS idx_exam_marks_student ON school.exam_marks(student_id);",
    "CREATE INDEX IF NOT EXISTS idx_exam_marks_tenant_ay ON school.exam_marks(tenant_id, academic_year_id);",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        for sql in SQL_BLOCKS:
            await conn.execute(text(sql.strip()))
    print("Migration 025: grade_scales and exam_marks tables created.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
