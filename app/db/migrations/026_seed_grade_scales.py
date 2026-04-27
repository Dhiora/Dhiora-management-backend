"""
Migration 026: Seed default grade scales with real UUIDs.

Why:
- If a tenant has no rows in school.grade_scales, the API returns fallback
  in-memory defaults with id=00000000-0000-0000-0000-000000000000.
- This script inserts actual DB rows so frontend gets real UUID ids.

Run:
  python -m app.db.migrations.026_seed_grade_scales
"""

import asyncio
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.grades.models import GradeScale
from app.auth import models as auth_models  # noqa: F401 - register auth models
from app.core.models import Tenant
from app.db.session import AsyncSessionLocal


DEFAULT_SCALES = [
    {"label": "A+", "min_percentage": Decimal("90"), "max_percentage": Decimal("100"), "gpa_points": Decimal("4.0"), "display_order": 1},
    {"label": "A", "min_percentage": Decimal("80"), "max_percentage": Decimal("89.99"), "gpa_points": Decimal("3.7"), "display_order": 2},
    {"label": "B+", "min_percentage": Decimal("70"), "max_percentage": Decimal("79.99"), "gpa_points": Decimal("3.3"), "display_order": 3},
    {"label": "B", "min_percentage": Decimal("60"), "max_percentage": Decimal("69.99"), "gpa_points": Decimal("3.0"), "display_order": 4},
    {"label": "C", "min_percentage": Decimal("50"), "max_percentage": Decimal("59.99"), "gpa_points": Decimal("2.0"), "display_order": 5},
    {"label": "D", "min_percentage": Decimal("40"), "max_percentage": Decimal("49.99"), "gpa_points": Decimal("1.0"), "display_order": 6},
    {"label": "F", "min_percentage": Decimal("0"), "max_percentage": Decimal("39.99"), "gpa_points": Decimal("0.0"), "display_order": 7},
]


async def seed_grade_scales(db: AsyncSession) -> None:
    tenant_result = await db.execute(select(Tenant.id))
    tenant_ids = [row[0] for row in tenant_result.all()]

    seeded_tenants = 0
    skipped_tenants = 0

    for tenant_id in tenant_ids:
        count_result = await db.execute(
            select(func.count(GradeScale.id)).where(GradeScale.tenant_id == tenant_id)
        )
        existing_count = count_result.scalar() or 0
        if existing_count > 0:
            skipped_tenants += 1
            continue

        for scale in DEFAULT_SCALES:
            db.add(
                GradeScale(
                    tenant_id=tenant_id,
                    label=scale["label"],
                    min_percentage=scale["min_percentage"],
                    max_percentage=scale["max_percentage"],
                    gpa_points=scale["gpa_points"],
                    remarks=None,
                    display_order=scale["display_order"],
                )
            )
        seeded_tenants += 1

    await db.commit()
    print(f"Seeded grade scales for tenants: {seeded_tenants}")
    print(f"Skipped tenants (already had scales): {skipped_tenants}")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        try:
            await seed_grade_scales(db)
            print("Migration 026 completed successfully.")
        except Exception as exc:
            await db.rollback()
            print(f"Migration 026 failed: {exc}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
