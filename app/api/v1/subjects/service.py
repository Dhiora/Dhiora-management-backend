from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import SchoolSubject
from app.api.v1.departments import service as department_service

from .schemas import SubjectCreate, SubjectDropdownItem, SubjectResponse, SubjectUpdate


def _to_response(s: SchoolSubject) -> SubjectResponse:
    return SubjectResponse(
        id=s.id,
        tenant_id=s.tenant_id,
        department_id=s.department_id,
        name=s.name,
        code=s.code,
        display_order=s.display_order,
        is_active=s.is_active,
        created_at=s.created_at,
    )


def _conflict_message(existing: SchoolSubject, code: str) -> str:
    return (
        f"Subject code '{code}' already exists in school.subjects "
        f"(existing: name='{existing.name}', id={existing.id}, department_id={existing.department_id})"
    )


async def _existing_in_school_subjects(
    db: AsyncSession,
    tenant_id: UUID,
    department_id: UUID,
    code: str,
    exclude_subject_id: Optional[UUID] = None,
) -> Optional[SchoolSubject]:
    """Check only school.subjects (this API's table). Uniqueness is (tenant_id, department_id, code)."""
    stmt = select(SchoolSubject).where(
        SchoolSubject.tenant_id == tenant_id,
        SchoolSubject.department_id == department_id,
        SchoolSubject.code == code,
    )
    if exclude_subject_id is not None:
        stmt = stmt.where(SchoolSubject.id != exclude_subject_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _find_any_by_tenant_and_code(
    db: AsyncSession, tenant_id: UUID, code: str
) -> Optional[SchoolSubject]:
    """Find any row in school.subjects with this tenant and code (used when DB still has old tenant+code constraint)."""
    result = await db.execute(
        select(SchoolSubject).where(
            SchoolSubject.tenant_id == tenant_id,
            SchoolSubject.code == code,
        )
    )
    return result.scalar_one_or_none()


async def create_subject(
    db: AsyncSession,
    tenant_id: UUID,
    payload: SubjectCreate,
) -> SubjectResponse:
    dept = await department_service.get_department_by_id_for_tenant(db, tenant_id, payload.department_id, active_only=True)
    if not dept:
        raise ServiceError("Invalid department", status.HTTP_400_BAD_REQUEST)
    code = payload.code.strip().upper()
    name = payload.name.strip()
    # Check only school.subjects, same (tenant, department, code)
    existing = await _existing_in_school_subjects(db, tenant_id, payload.department_id, code)
    if existing:
        raise ServiceError(_conflict_message(existing, code), status.HTTP_409_CONFLICT)
    try:
        obj = SchoolSubject(
            tenant_id=tenant_id,
            department_id=payload.department_id,
            name=name,
            code=code,
            display_order=payload.display_order,
            is_active=True,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError as e:
        await db.rollback()
        err_msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        # FK violation: department_id not in departments table (e.g. wrong schema or stale data)
        if "foreign key" in err_msg.lower() or "department_id" in err_msg or "departments" in err_msg.lower():
            raise ServiceError(
                "Department not found or invalid. If the department exists in your departments list, run schema migration: python -m app.db.schema_check",
                status.HTTP_400_BAD_REQUEST,
            )
        # Unique constraint: find conflicting row for a clear message
        conflict = await _find_any_by_tenant_and_code(db, tenant_id, code)
        if conflict:
            msg = _conflict_message(conflict, code)
            if conflict.department_id != payload.department_id:
                msg += ". Code is unique per department; run schema migration if you need the same code in multiple departments."
            raise ServiceError(msg, status.HTTP_409_CONFLICT)
        raise ServiceError(
            "Subject code already exists in school.subjects (run schema migration for per-department uniqueness).",
            status.HTTP_409_CONFLICT,
        )


async def list_subjects(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[SubjectResponse]:
    stmt = select(SchoolSubject).where(SchoolSubject.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(SchoolSubject.is_active.is_(True))
    stmt = stmt.order_by(SchoolSubject.display_order.nullslast(), SchoolSubject.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_to_response(s) for s in rows]


async def get_subject(
    db: AsyncSession,
    tenant_id: UUID,
    subject_id: UUID,
) -> Optional[SubjectResponse]:
    result = await db.execute(
        select(SchoolSubject).where(
            SchoolSubject.id == subject_id,
            SchoolSubject.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    return _to_response(obj) if obj else None


async def get_subject_by_id_for_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    subject_id: UUID,
    active_only: bool = True,
) -> Optional[SchoolSubject]:
    stmt = select(SchoolSubject).where(
        SchoolSubject.id == subject_id,
        SchoolSubject.tenant_id == tenant_id,
    )
    if active_only:
        stmt = stmt.where(SchoolSubject.is_active.is_(True))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_subject(
    db: AsyncSession,
    tenant_id: UUID,
    subject_id: UUID,
    payload: SubjectUpdate,
) -> Optional[SubjectResponse]:
    result = await db.execute(
        select(SchoolSubject).where(
            SchoolSubject.id == subject_id,
            SchoolSubject.tenant_id == tenant_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    if payload.department_id is not None:
        dept = await department_service.get_department_by_id_for_tenant(db, tenant_id, payload.department_id, active_only=True)
        if not dept:
            raise ServiceError("Invalid department", status.HTTP_400_BAD_REQUEST)
        obj.department_id = payload.department_id
    if payload.name is not None:
        obj.name = payload.name.strip()
    if payload.code is not None:
        obj.code = payload.code.strip().upper()
    if payload.display_order is not None:
        obj.display_order = payload.display_order
    if payload.is_active is not None:
        obj.is_active = payload.is_active
    new_code = obj.code
    existing = await _existing_in_school_subjects(
        db, tenant_id, obj.department_id, new_code, exclude_subject_id=subject_id
    )
    if existing:
        raise ServiceError(_conflict_message(existing, new_code), status.HTTP_409_CONFLICT)
    try:
        await db.commit()
        await db.refresh(obj)
        return _to_response(obj)
    except IntegrityError as e:
        await db.rollback()
        err_msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        if "foreign key" in err_msg.lower() or "department_id" in err_msg or "departments" in err_msg.lower():
            raise ServiceError(
                "Department not found or invalid. If the department exists in your departments list, run schema migration: python -m app.db.schema_check",
                status.HTTP_400_BAD_REQUEST,
            )
        conflict = await _find_any_by_tenant_and_code(db, tenant_id, new_code)
        if conflict and conflict.id != subject_id:
            msg = _conflict_message(conflict, new_code)
            if conflict.department_id != obj.department_id:
                msg += ". Code is unique per department; run schema migration if you need the same code in multiple departments."
            raise ServiceError(msg, status.HTTP_409_CONFLICT)
        raise ServiceError(
            "Subject code already exists in school.subjects (run schema migration for per-department uniqueness).",
            status.HTTP_409_CONFLICT,
        )


async def get_subject_dropdown(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[SubjectDropdownItem]:
    subjects = await list_subjects(db, tenant_id, active_only=True)
    return [SubjectDropdownItem(label=s.name, value=s.id) for s in subjects]
