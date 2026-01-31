from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import AcademicYear

from .schemas import AcademicYearCreate, AcademicYearResponse, AcademicYearUpdate


def _to_response(ay: AcademicYear) -> AcademicYearResponse:
    return AcademicYearResponse(
        id=ay.id,
        tenant_id=ay.tenant_id,
        name=ay.name,
        start_date=ay.start_date,
        end_date=ay.end_date,
        is_current=ay.is_current,
        status=ay.status,
        admissions_allowed=getattr(ay, "admissions_allowed", True),
        created_at=ay.created_at,
        updated_at=ay.updated_at,
        closed_at=getattr(ay, "closed_at", None),
        closed_by=getattr(ay, "closed_by", None),
    )


def _validate_dates(start_date: date, end_date: date) -> None:
    if end_date <= start_date:
        raise ServiceError("end_date must be after start_date", status.HTTP_400_BAD_REQUEST)


async def create_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
    payload: AcademicYearCreate,
) -> AcademicYearResponse:
    """Create academic year. If is_current=true, unset current on all other years (transaction)."""
    _validate_dates(payload.start_date, payload.end_date)
    existing = await db.execute(
        select(AcademicYear).where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.name == payload.name.strip(),
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError(
            f"Academic year with name '{payload.name}' already exists for this tenant",
            status.HTTP_409_CONFLICT,
        )
    if payload.is_current:
        await db.execute(
            update(AcademicYear).where(AcademicYear.tenant_id == tenant_id).values(is_current=False)
        )
    ay = AcademicYear(
        tenant_id=tenant_id,
        name=payload.name.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_current=payload.is_current,
        status="ACTIVE",
        admissions_allowed=payload.admissions_allowed,
    )
    db.add(ay)
    try:
        await db.commit()
        await db.refresh(ay)
        return _to_response(ay)
    except IntegrityError:
        await db.rollback()
        raise ServiceError(
            "Another academic year is already marked as current or name conflict",
            status.HTTP_409_CONFLICT,
        )


async def list_academic_years(
    db: AsyncSession,
    tenant_id: UUID,
    status_filter: Optional[str] = None,
) -> List[AcademicYearResponse]:
    """List academic years for tenant, optionally filtered by status."""
    stmt = select(AcademicYear).where(AcademicYear.tenant_id == tenant_id)
    if status_filter:
        stmt = stmt.where(AcademicYear.status == status_filter)
    stmt = stmt.order_by(AcademicYear.start_date.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_to_response(ay) for ay in rows]


async def get_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
) -> Optional[AcademicYearResponse]:
    """Get one academic year by id (tenant-scoped)."""
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.tenant_id == tenant_id,
        )
    )
    ay = result.scalar_one_or_none()
    return _to_response(ay) if ay else None


async def get_current_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
) -> Optional[AcademicYearResponse]:
    """Get the current academic year (is_current=true) for tenant. Default for data operations."""
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.is_current.is_(True),
        )
    )
    ay = result.scalar_one_or_none()
    return _to_response(ay) if ay else None


async def update_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    payload: AcademicYearUpdate,
) -> AcademicYearResponse:
    """Update academic year. Only allowed when status is ACTIVE."""
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.tenant_id == tenant_id,
        )
    )
    ay = result.scalar_one_or_none()
    if not ay:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)
    if ay.status != "ACTIVE":
        raise ServiceError(
            "Cannot update a CLOSED academic year; it is read-only",
            status.HTTP_400_BAD_REQUEST,
        )
    if payload.name is not None:
        other = await db.execute(
            select(AcademicYear).where(
                AcademicYear.tenant_id == tenant_id,
                AcademicYear.name == payload.name.strip(),
                AcademicYear.id != academic_year_id,
            )
        )
        if other.scalar_one_or_none():
            raise ServiceError(
                f"Academic year with name '{payload.name}' already exists",
                status.HTTP_409_CONFLICT,
            )
        ay.name = payload.name.strip()
    if payload.start_date is not None:
        ay.start_date = payload.start_date
    if payload.end_date is not None:
        ay.end_date = payload.end_date
    if payload.start_date is not None or payload.end_date is not None:
        _validate_dates(ay.start_date, ay.end_date)
    if payload.admissions_allowed is not None:
        ay.admissions_allowed = payload.admissions_allowed
    await db.commit()
    await db.refresh(ay)
    return _to_response(ay)


async def set_academic_year_current(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
) -> AcademicYearResponse:
    """Set this academic year as current. All others for tenant become is_current=false (transaction)."""
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.tenant_id == tenant_id,
        )
    )
    ay = result.scalar_one_or_none()
    if not ay:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)
    if ay.status != "ACTIVE":
        raise ServiceError(
            "Cannot set a CLOSED academic year as current",
            status.HTTP_400_BAD_REQUEST,
        )
    await db.execute(
        update(AcademicYear).where(AcademicYear.tenant_id == tenant_id).values(is_current=False)
    )
    ay.is_current = True
    await db.commit()
    await db.refresh(ay)
    return _to_response(ay)


async def close_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
    closed_by: Optional[UUID] = None,
) -> AcademicYearResponse:
    """Close academic year (status=CLOSED). Becomes read-only; no data can be modified for this year."""
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.tenant_id == tenant_id,
        )
    )
    ay = result.scalar_one_or_none()
    if not ay:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)
    if ay.status == "CLOSED":
        raise ServiceError("Academic year is already CLOSED", status.HTTP_400_BAD_REQUEST)
    ay.status = "CLOSED"
    ay.is_current = False
    ay.closed_at = datetime.utcnow()
    ay.closed_by = closed_by
    await db.commit()
    await db.refresh(ay)
    return _to_response(ay)


async def reopen_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: UUID,
) -> AcademicYearResponse:
    """Reopen a CLOSED academic year (e.g. accidental close). Sets status=ACTIVE, clears closed_at/closed_by.
    If no other year is current, sets this one as current."""
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.id == academic_year_id,
            AcademicYear.tenant_id == tenant_id,
        )
    )
    ay = result.scalar_one_or_none()
    if not ay:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)
    if ay.status != "CLOSED":
        raise ServiceError("Academic year is not CLOSED; only closed years can be reopened", status.HTTP_400_BAD_REQUEST)

    ay.status = "ACTIVE"
    ay.closed_at = None
    ay.closed_by = None

    # If no other year is current, set this one as current
    other_current = await db.execute(
        select(AcademicYear).where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.id != academic_year_id,
            AcademicYear.is_current.is_(True),
        )
    )
    if not other_current.scalar_one_or_none():
        await db.execute(
            update(AcademicYear).where(AcademicYear.tenant_id == tenant_id).values(is_current=False)
        )
        ay.is_current = True

    await db.commit()
    await db.refresh(ay)
    return _to_response(ay)


async def get_admission_open_academic_year(
    db: AsyncSession,
    tenant_id: UUID,
) -> Optional[AcademicYear]:
    """
    Get the current academic year where admissions are allowed.
    Student creation requires: is_current=true, status=ACTIVE, admissions_allowed=true.
    Returns None if no such year exists (student creation must then FAIL).
    """
    result = await db.execute(
        select(AcademicYear).where(
            AcademicYear.tenant_id == tenant_id,
            AcademicYear.is_current.is_(True),
            AcademicYear.status == "ACTIVE",
            AcademicYear.admissions_allowed.is_(True),
        )
    )
    return result.scalar_one_or_none()
