"""
Check school.subjects table: row count, sample rows, and uniqueness constraints.
Use this to verify whether subject codes exist when you get "Subject code already exists" errors.

Usage:
  python -m app.scripts.check_subjects_table
  python -m app.scripts.check_subjects_table --code TESTING
  python -m app.scripts.check_subjects_table --code "BIO"
"""

import argparse
import asyncio
from typing import Optional

from sqlalchemy import text

from app.db.session import AsyncSessionLocal


async def run_checks(code_filter: Optional[str] = None) -> None:
    async with AsyncSessionLocal() as session:
        # 1) Raw count on school.subjects
        result = await session.execute(
            text("SELECT COUNT(*) FROM school.subjects")
        )
        total = result.scalar()
        print(f"school.subjects total row count: {total}")

        # 2) List unique constraints on school.subjects
        constraints_result = await session.execute(
            text("""
                SELECT c.conname AS constraint_name,
                       pg_get_constraintdef(c.oid) AS definition
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE n.nspname = 'school' AND t.relname = 'subjects'
                  AND c.contype = 'u'
                ORDER BY c.conname;
            """)
        )
        rows = constraints_result.fetchall()
        print("\nUnique constraints on school.subjects:")
        if not rows:
            print("  (none)")
        for name, definition in rows:
            print(f"  {name}: {definition}")

        # 3) Optional: rows with given code, or sample rows (raw SQL to avoid ORM registry loading)
        if code_filter:
            code_upper = code_filter.strip().upper()
            result = await session.execute(
                text("SELECT id, tenant_id, department_id, name, code FROM school.subjects WHERE code = :code"),
                {"code": code_upper},
            )
            subjects = result.fetchall()
            print(f"\nRows with code = '{code_upper}': {len(subjects)}")
            for row in subjects:
                print(f"  id={row[0]} tenant_id={row[1]} department_id={row[2]} name={row[3]!r} code={row[4]!r}")
        else:
            result = await session.execute(
                text("SELECT id, tenant_id, department_id, name, code FROM school.subjects LIMIT 5")
            )
            sample = result.fetchall()
            print("\nFirst 5 rows (sample):")
            if not sample:
                print("  (no rows)")
            for row in sample:
                print(f"  id={row[0]} department_id={row[2]} name={row[3]!r} code={row[4]!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check school.subjects table and optional code")
    parser.add_argument("--code", type=str, default=None, help="Filter by subject code (e.g. TESTING, BIO)")
    args = parser.parse_args()
    asyncio.run(run_checks(code_filter=args.code))


if __name__ == "__main__":
    main()
