"""Service layer for Holiday Calendar."""

from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import AcademicYear, HolidayCalendar

from .integration_placeholders import remove_holiday_references_from_payroll
from .repository import (
    add_holiday,
    delete_holiday,
    get_holiday_by_date,
    get_holiday_by_id,
    list_holidays,
    update_holiday,
)
from .schemas import HolidayCreate, HolidayResponse, HolidayUpdate


def _to_response(model: HolidayCalendar) -> HolidayResponse:
    return HolidayResponse.model_validate(model)


async def _get_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
) -> AcademicYear:
    ay = await db.get(AcademicYear, academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    return ay


async def create_holiday(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_id: UUID,
    payload: HolidayCreate,
) -> HolidayResponse:
    ay = await _get_academic_year(db, tenant_id, payload.academic_year_id)

    if not (ay.start_date <= payload.holiday_date <= ay.end_date):
        raise ServiceError(
            "Holiday date must be within the academic year range",
            status.HTTP_400_BAD_REQUEST,
        )

    existing = await get_holiday_by_date(
        db,
        tenant_id,
        payload.academic_year_id,
        payload.holiday_date,
    )
    if existing:
        raise ServiceError(
            "Holiday already exists for this date in the academic year",
            status.HTTP_400_BAD_REQUEST,
        )

    month = payload.holiday_date.month
    year = payload.holiday_date.year

    holiday = HolidayCalendar(
        tenant_id=tenant_id,
        academic_year_id=payload.academic_year_id,
        holiday_name=payload.holiday_name.strip(),
        holiday_date=payload.holiday_date,
        month=month,
        year=year,
        description=payload.description.strip() if payload.description else None,
        created_by=current_user_id,
        updated_by=current_user_id,
    )

    saved = await add_holiday(db, holiday)
    return _to_response(saved)


async def list_holidays_service(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    month: Optional[int] = None,
) -> List[HolidayResponse]:
    await _get_academic_year(db, tenant_id, academic_year_id)
    if month is not None and (month < 1 or month > 12):
        raise ServiceError("month must be between 1 and 12", status.HTTP_400_BAD_REQUEST)

    rows = await list_holidays(db, tenant_id, academic_year_id, month)
    return [_to_response(row) for row in rows]


async def get_calendar_view(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    month: int,
) -> Dict[str, str]:
    if month < 1 or month > 12:
        raise ServiceError("month must be between 1 and 12", status.HTTP_400_BAD_REQUEST)

    await _get_academic_year(db, tenant_id, academic_year_id)
    rows = await list_holidays(db, tenant_id, academic_year_id, month)
    return {row.holiday_date.isoformat(): row.holiday_name for row in rows}


async def update_holiday_service(
    db: AsyncSession,
    tenant_id: UUID,
    holiday_id: UUID,
    current_user_id: UUID,
    payload: HolidayUpdate,
) -> HolidayResponse:
    holiday = await get_holiday_by_id(db, tenant_id, holiday_id)
    if not holiday:
        raise ServiceError("Holiday not found", status.HTTP_404_NOT_FOUND)

    if payload.holiday_name is not None:
        holiday.holiday_name = payload.holiday_name.strip()

    if payload.description is not None:
        holiday.description = payload.description.strip() if payload.description else None

    if payload.holiday_date is not None:
        ay = await _get_academic_year(db, tenant_id, holiday.academic_year_id)
        if not (ay.start_date <= payload.holiday_date <= ay.end_date):
            raise ServiceError(
                "Holiday date must be within the academic year range",
                status.HTTP_400_BAD_REQUEST,
            )

        existing = await get_holiday_by_date(
            db,
            tenant_id,
            holiday.academic_year_id,
            payload.holiday_date,
            exclude_id=holiday.id,
        )
        if existing:
            raise ServiceError(
                "Another holiday already exists for this date in the academic year",
                status.HTTP_400_BAD_REQUEST,
            )

        holiday.holiday_date = payload.holiday_date
        holiday.month = payload.holiday_date.month
        holiday.year = payload.holiday_date.year

    holiday.updated_by = current_user_id

    updated = await update_holiday(db, holiday)
    return _to_response(updated)


async def delete_holiday_service(
    db: AsyncSession,
    tenant_id: UUID,
    holiday_id: UUID,
) -> None:
    holiday = await get_holiday_by_id(db, tenant_id, holiday_id)
    if not holiday:
        raise ServiceError("Holiday not found", status.HTTP_404_NOT_FOUND)

    today = date.today()
    if holiday.holiday_date < today:
        raise ServiceError(
            "Past holidays cannot be deleted",
            status.HTTP_400_BAD_REQUEST,
        )

    await remove_holiday_references_from_payroll(
        tenant_id=holiday.tenant_id,
        academic_year_id=holiday.academic_year_id,
        holiday_id=holiday.id,
    )

    await delete_holiday(db, holiday)

