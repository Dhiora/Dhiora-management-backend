"""Repository layer for Holiday Calendar."""

from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import HolidayCalendar


async def get_holiday_by_id(
    db: AsyncSession,
    tenant_id: UUID,
    holiday_id: UUID,
) -> Optional[HolidayCalendar]:
    stmt: Select = select(HolidayCalendar).where(
        HolidayCalendar.id == holiday_id,
        HolidayCalendar.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_holiday_by_date(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    holiday_date: date,
    exclude_id: Optional[UUID] = None,
) -> Optional[HolidayCalendar]:
    conditions = [
        HolidayCalendar.tenant_id == tenant_id,
        HolidayCalendar.academic_year_id == academic_year_id,
        HolidayCalendar.holiday_date == holiday_date,
    ]
    if exclude_id is not None:
        conditions.append(HolidayCalendar.id != exclude_id)
    stmt: Select = select(HolidayCalendar).where(and_(*conditions))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_holidays(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    month: Optional[int] = None,
) -> List[HolidayCalendar]:
    conditions = [
        HolidayCalendar.tenant_id == tenant_id,
        HolidayCalendar.academic_year_id == academic_year_id,
    ]
    if month is not None:
        conditions.append(HolidayCalendar.month == month)
    stmt: Select = (
        select(HolidayCalendar)
        .where(and_(*conditions))
        .order_by(HolidayCalendar.holiday_date)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def add_holiday(
    db: AsyncSession,
    holiday: HolidayCalendar,
) -> HolidayCalendar:
    db.add(holiday)
    await db.commit()
    await db.refresh(holiday)
    return holiday


async def update_holiday(
    db: AsyncSession,
    holiday: HolidayCalendar,
) -> HolidayCalendar:
    await db.commit()
    await db.refresh(holiday)
    return holiday


async def delete_holiday(
    db: AsyncSession,
    holiday: HolidayCalendar,
) -> None:
    await db.delete(holiday)
    await db.commit()

