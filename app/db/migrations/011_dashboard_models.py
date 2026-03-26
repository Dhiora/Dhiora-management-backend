"""Migration 011 – Create dashboard support tables.

New tables:
  school.lesson_plan_progress  – curriculum completion % per grade group / academic year
  school.dashboard_alerts      – tenant-scoped alerts shown on the admin dashboard

Indexes:
  idx_lesson_progress_tenant_ay  ON school.lesson_plan_progress (tenant_id, academic_year_id)
  idx_dashboard_alerts_tenant    ON school.dashboard_alerts      (tenant_id)
  idx_dashboard_alerts_active    ON school.dashboard_alerts      (tenant_id, is_active, expires_at)
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine

logger = logging.getLogger(__name__)


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        # ── lesson_plan_progress ────────────────────────────────────────────
        await conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS school.lesson_plan_progress (
                id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id         UUID        NOT NULL REFERENCES core.tenants(id)       ON DELETE CASCADE,
                academic_year_id  UUID        NOT NULL REFERENCES core.academic_years(id) ON DELETE CASCADE,
                grade_group       VARCHAR(100) NOT NULL,
                progress_percent  INTEGER      NOT NULL DEFAULT 0
                                  CHECK (progress_percent BETWEEN 0 AND 100),
                is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
                created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_lesson_progress_tenant_ay_group
                    UNIQUE (tenant_id, academic_year_id, grade_group)
            );
            """)
        )

        await conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_lesson_progress_tenant_ay
                ON school.lesson_plan_progress (tenant_id, academic_year_id);
            """)
        )

        logger.info("Migration 011: created school.lesson_plan_progress")

        # ── dashboard_alerts ────────────────────────────────────────────────
        await conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS school.dashboard_alerts (
                id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id   UUID        NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
                alert_type  VARCHAR(20)  NOT NULL DEFAULT 'warning'
                            CHECK (alert_type IN ('info', 'warning', 'critical')),
                message     TEXT         NOT NULL,
                action_url  TEXT,
                is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
                expires_at  TIMESTAMPTZ,
                created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            );
            """)
        )

        await conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_dashboard_alerts_tenant
                ON school.dashboard_alerts (tenant_id);
            """)
        )

        await conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_dashboard_alerts_active
                ON school.dashboard_alerts (tenant_id, is_active, expires_at);
            """)
        )

        logger.info("Migration 011: created school.dashboard_alerts")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migration(engine))
