"""
Migration: Create Online Assessment tables.

Creates (all in 'school' schema):
  - school.online_assessments
  - school.assessment_questions
  - school.assessment_attempts
  - school.assessment_attempt_answers

Run once:
  python -m app.db.migrations.010_create_online_assessment_tables
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_ONLINE_ASSESSMENTS = """
CREATE TABLE IF NOT EXISTS school.online_assessments (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID        NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    created_by          UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    academic_year_id    UUID        NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
    class_id            UUID        NOT NULL REFERENCES core.classes(id) ON DELETE RESTRICT,
    section_id          UUID        REFERENCES core.sections(id) ON DELETE RESTRICT,
    subject_id          UUID        REFERENCES school.subjects(id) ON DELETE RESTRICT,
    title               VARCHAR(255) NOT NULL,
    description         TEXT,
    duration_minutes    INTEGER     NOT NULL DEFAULT 30,
    attempts_allowed    INTEGER     NOT NULL DEFAULT 1,
    status              VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                            CONSTRAINT chk_online_assessment_status
                            CHECK (status IN ('DRAFT','ACTIVE','UPCOMING','COMPLETED')),
    due_date            DATE,
    total_questions     INTEGER     NOT NULL DEFAULT 0,
    total_marks         INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_ONLINE_ASSESSMENTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_online_assessments_tenant_id ON school.online_assessments(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_online_assessments_academic_year ON school.online_assessments(academic_year_id);",
    "CREATE INDEX IF NOT EXISTS idx_online_assessments_class_section ON school.online_assessments(class_id, section_id);",
    "CREATE INDEX IF NOT EXISTS idx_online_assessments_status ON school.online_assessments(status);",
]

CREATE_ASSESSMENT_QUESTIONS = """
CREATE TABLE IF NOT EXISTS school.assessment_questions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id   UUID        NOT NULL REFERENCES school.online_assessments(id) ON DELETE CASCADE,
    question_text   TEXT        NOT NULL,
    question_type   VARCHAR(30) NOT NULL DEFAULT 'MCQ'
                        CONSTRAINT chk_assessment_question_type
                        CHECK (question_type IN ('MCQ','FILL_IN_BLANK','MULTI_SELECT','SHORT_ANSWER','LONG_ANSWER')),
    options         JSONB,
    correct_answer  JSONB,
    marks           INTEGER     NOT NULL DEFAULT 1,
    difficulty      VARCHAR(10)
                        CONSTRAINT chk_assessment_question_difficulty
                        CHECK (difficulty IN ('easy','medium','hard')),
    order_index     INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_ASSESSMENT_QUESTIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_assessment_questions_assessment_id ON school.assessment_questions(assessment_id);",
]

CREATE_ASSESSMENT_ATTEMPTS = """
CREATE TABLE IF NOT EXISTS school.assessment_attempts (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id       UUID        NOT NULL REFERENCES school.online_assessments(id) ON DELETE CASCADE,
    student_id          UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    attempt_number      INTEGER     NOT NULL DEFAULT 1,
    status              VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS'
                            CONSTRAINT chk_assessment_attempt_status
                            CHECK (status IN ('IN_PROGRESS','SUBMITTED','ABORTED','TIMED_OUT')),
    score               INTEGER,
    total_marks         INTEGER,
    correct_count       INTEGER,
    wrong_count         INTEGER,
    skipped_count       INTEGER,
    time_taken_seconds  INTEGER,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_assessment_attempt_number UNIQUE (assessment_id, student_id, attempt_number)
);
"""

CREATE_ASSESSMENT_ATTEMPTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_assessment_attempts_assessment_id ON school.assessment_attempts(assessment_id);",
    "CREATE INDEX IF NOT EXISTS idx_assessment_attempts_student_id ON school.assessment_attempts(student_id);",
]

CREATE_ASSESSMENT_ATTEMPT_ANSWERS = """
CREATE TABLE IF NOT EXISTS school.assessment_attempt_answers (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id      UUID        NOT NULL REFERENCES school.assessment_attempts(id) ON DELETE CASCADE,
    question_id     UUID        NOT NULL REFERENCES school.assessment_questions(id) ON DELETE CASCADE,
    selected_answer JSONB,
    is_correct      BOOLEAN,
    marks_awarded   INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_attempt_question_answer UNIQUE (attempt_id, question_id)
);
"""

CREATE_ASSESSMENT_ATTEMPT_ANSWERS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_assessment_attempt_answers_attempt_id ON school.assessment_attempt_answers(attempt_id);",
]


async def run_migration(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        print("Creating school.online_assessments …")
        await conn.execute(text(CREATE_ONLINE_ASSESSMENTS))
        for idx in CREATE_ONLINE_ASSESSMENTS_INDEXES:
            await conn.execute(text(idx))

        print("Creating school.assessment_questions …")
        await conn.execute(text(CREATE_ASSESSMENT_QUESTIONS))
        for idx in CREATE_ASSESSMENT_QUESTIONS_INDEXES:
            await conn.execute(text(idx))

        print("Creating school.assessment_attempts …")
        await conn.execute(text(CREATE_ASSESSMENT_ATTEMPTS))
        for idx in CREATE_ASSESSMENT_ATTEMPTS_INDEXES:
            await conn.execute(text(idx))

        print("Creating school.assessment_attempt_answers …")
        await conn.execute(text(CREATE_ASSESSMENT_ATTEMPT_ANSWERS))
        for idx in CREATE_ASSESSMENT_ATTEMPT_ANSWERS_INDEXES:
            await conn.execute(text(idx))

    print("Migration 010 complete.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
