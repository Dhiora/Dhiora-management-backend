"""
Backfill referral codes for teachers who already exist in the DB but have no row in teacher_referrals.

Run once (idempotent): only inserts for teachers without an existing referral.
Usage: python -m app.scripts.backfill_teacher_referrals
"""

import asyncio
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure all models are loaded so ORM relationships resolve (e.g. User -> Tenant)
from app.core.models import Tenant  # noqa: F401
from app.auth.models import User, TeacherReferral
from app.auth.referral_code import generate_teacher_referral_code
from app.db.session import AsyncSessionLocal


async def get_teachers_without_referral(session: AsyncSession) -> list:
    """Return list of (user_id, tenant_id, full_name) for teachers with no teacher_referrals row."""
    all_teachers = await session.execute(
        select(User.id, User.tenant_id, User.full_name).where(
            User.user_type == "employee",
            User.role == "Teacher",
        )
    )
    rows = all_teachers.all()
    existing_refs = await session.execute(select(TeacherReferral.teacher_id))
    have_ref = {r[0] for r in existing_refs.all()}
    return [(r[0], r[1], r[2]) for r in rows if r[0] not in have_ref]


async def backfill_teacher_referrals() -> None:
    """Generate and insert referral codes for existing teachers who don't have one."""
    async with AsyncSessionLocal() as session:
        teachers = await get_teachers_without_referral(session)
        if not teachers:
            print("No teachers without referral code found. Exiting.")
            return

        print(f"Found {len(teachers)} teacher(s) without referral code. Generating...")
        created = 0
        max_attempts = 5

        for user_id, tenant_id, full_name in teachers:
            user_id = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
            tenant_id = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
            name = full_name or ""

            for attempt in range(max_attempts):
                referral_code = generate_teacher_referral_code(name)
                ref = TeacherReferral(
                    teacher_id=user_id,
                    tenant_id=tenant_id,
                    referral_code=referral_code,
                )
                session.add(ref)
                try:
                    await session.commit()
                    created += 1
                    print(f"  {full_name} (id={user_id}) -> {referral_code}")
                    break
                except IntegrityError:
                    await session.rollback()
                    if attempt == max_attempts - 1:
                        print(f"  SKIP: Could not generate unique code for {full_name} (id={user_id}) after {max_attempts} attempts.", file=sys.stderr)
                    else:
                        continue

        print(f"Done. Created {created} referral code(s).")


def main() -> None:
    asyncio.run(backfill_teacher_referrals())


if __name__ == "__main__":
    main()
