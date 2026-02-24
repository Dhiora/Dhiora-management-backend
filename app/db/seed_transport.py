"""Seed default transport vehicle types (BUS, VAN, MINIBUS, AUTO, CAB). System defaults have tenant_id=NULL."""

import asyncio
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

DEFAULT_VEHICLE_TYPES = [
    ("BUS", "School bus"),
    ("VAN", "Van"),
    ("MINIBUS", "Minibus"),
    ("AUTO", "Auto rickshaw"),
    ("CAB", "Cab"),
]


async def seed_transport_vehicle_types(db: AsyncSession) -> int:
    """Insert system default vehicle types if not present. Returns count inserted."""
    inserted = 0
    for code, desc in DEFAULT_VEHICLE_TYPES:
        exists = await db.execute(
            text("SELECT 1 FROM school.transport_vehicle_types WHERE tenant_id IS NULL AND name = :name"),
            {"name": code},
        )
        if exists.scalar() is not None:
            continue
        await db.execute(
            text("""
                INSERT INTO school.transport_vehicle_types
                (id, tenant_id, academic_year_id, name, description, is_system_default, is_active, created_at, updated_at)
                VALUES (:id, NULL, NULL, :name, :desc, TRUE, TRUE, NOW(), NOW())
            """),
            {"id": uuid4(), "name": code, "desc": desc},
        )
        inserted += 1
    return inserted


async def main() -> None:
    async with AsyncSessionLocal() as db:
        n = await seed_transport_vehicle_types(db)
        await db.commit()
        print(f"Transport seed: {n} default vehicle type(s) inserted (total system defaults: {len(DEFAULT_VEHICLE_TYPES)}).")


if __name__ == "__main__":
    asyncio.run(main())
