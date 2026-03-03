"""
Migration 006: Create school.time_slots and refactor school.timetables to use slot_id.

Steps:
- Create school.time_slots table.
- Add slot_id column to school.timetables.
- Backfill slot_id by grouping distinct (tenant_id, start_time, end_time) per tenant.
- Drop start_time and end_time from school.timetables.
- Add useful indexes.

Run once:
  python -m app.db.migrations.006_time_slots_and_timetables_refactor
"""

import asyncio
import uuid
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_TIME_SLOTS_TABLE = """
CREATE TABLE IF NOT EXISTS school.time_slots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_type VARCHAR(20) NOT NULL,
    order_index INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_time_slots_time_range CHECK (end_time > start_time),
    CONSTRAINT uq_time_slots_tenant_order_index UNIQUE (tenant_id, order_index)
);
"""


ALTER_TIMETABLES_ADD_SLOT_ID = """
ALTER TABLE school.timetables
ADD COLUMN IF NOT EXISTS slot_id UUID REFERENCES school.time_slots(id);
"""

DROP_TIMETABLES_START_END_TIME = """
ALTER TABLE school.timetables
DROP COLUMN IF EXISTS start_time,
DROP COLUMN IF EXISTS end_time;
"""

CREATE_TIMETABLE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_timetables_tenant_slot ON school.timetables(tenant_id, slot_id);",
    "CREATE INDEX IF NOT EXISTS ix_timetables_tenant_day ON school.timetables(tenant_id, day_of_week);",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        # 1. Create time_slots table
        await conn.execute(text(CREATE_TIME_SLOTS_TABLE))
        # 2. Add slot_id column to timetables
        await conn.execute(text(ALTER_TIMETABLES_ADD_SLOT_ID))

    # 3. Backfill slot_id using distinct (tenant_id, start_time, end_time)
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT DISTINCT tenant_id, start_time, end_time
                FROM school.timetables
                WHERE start_time IS NOT NULL AND end_time IS NOT NULL
                ORDER BY tenant_id, start_time, end_time
                """
            )
        )
        rows = result.mappings().all()
        by_tenant = defaultdict(list)
        for row in rows:
            by_tenant[row["tenant_id"]].append(row)

        for tenant_id, combos in by_tenant.items():
            # Sort by start_time then end_time for stable order_index
            combos_sorted = sorted(combos, key=lambda r: (r["start_time"], r["end_time"]))
            for idx, row in enumerate(combos_sorted, start=1):
                slot_id = uuid.uuid4()
                name = f"Slot {idx}"
                await conn.execute(
                    text(
                        """
                        INSERT INTO school.time_slots
                            (id, tenant_id, name, start_time, end_time, slot_type, order_index, is_active)
                        VALUES
                            (:id, :tenant_id, :name, :start_time, :end_time, 'CLASS', :order_index, TRUE)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "id": slot_id,
                        "tenant_id": tenant_id,
                        "name": name,
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "order_index": idx,
                    },
                )
                await conn.execute(
                    text(
                        """
                        UPDATE school.timetables
                        SET slot_id = :slot_id
                        WHERE tenant_id = :tenant_id
                          AND start_time = :start_time
                          AND end_time = :end_time
                        """
                    ),
                    {
                        "slot_id": slot_id,
                        "tenant_id": tenant_id,
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                    },
                )
        await conn.commit()

    async with db_engine.begin() as conn2:
        # 4. Make slot_id NOT NULL (if all rows backfilled) and drop old time columns
        await conn2.execute(
            text(
                """
                ALTER TABLE school.timetables
                ALTER COLUMN slot_id SET NOT NULL;
                """
            )
        )
        await conn2.execute(text(DROP_TIMETABLES_START_END_TIME))
        # 5. Indexes for performance
        for sql in CREATE_TIMETABLE_INDEXES:
            await conn2.execute(text(sql))

    print("Migration 006_time_slots_and_timetables_refactor done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))

