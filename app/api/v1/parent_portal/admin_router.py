"""Admin endpoints for parent account management."""

import csv
import io
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    AdminResetParentPasswordRequest,
    BulkImportResponse,
    BulkImportRow,
    CreateParentRequest,
    CreateParentResponse,
    ParentDetail,
    ParentListItem,
    UpdateParentRequest,
)

router = APIRouter(prefix="/api/v1/admin/parents", tags=["parent-admin"])


def _require_admin(current_user: CurrentUser) -> None:
    if current_user.role not in {"SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN"}:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


@router.post("", response_model=CreateParentResponse, status_code=http_status.HTTP_201_CREATED)
async def create_parent(
    payload: CreateParentRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateParentResponse:
    _require_admin(current_user)
    try:
        return await service.admin_create_parent(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("", response_model=List[ParentListItem])
async def list_parents(
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ParentListItem]:
    _require_admin(current_user)
    return await service.admin_list_parents(db, current_user.tenant_id, search, page, limit)


@router.post("/bulk-import", response_model=BulkImportResponse)
async def bulk_import_parents(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkImportResponse:
    _require_admin(current_user)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    content = await file.read()
    decoded = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(decoded))

    rows: List[BulkImportRow] = []
    for row in reader:
        try:
            rows.append(
                BulkImportRow(
                    full_name=row.get("full_name", ""),
                    email=row.get("email", ""),
                    phone=row.get("phone") or None,
                    student_admission_number=row.get("student_admission_number", ""),
                    relation=row.get("relation", ""),
                    is_primary=str(row.get("is_primary", "")).lower() in {"1", "true", "yes"},
                )
            )
        except Exception:
            continue

    result = await service.admin_bulk_import(db, current_user.tenant_id, rows)
    return BulkImportResponse(**result)


@router.get("/{parent_id}", response_model=ParentDetail)
async def get_parent(
    parent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParentDetail:
    _require_admin(current_user)
    try:
        return await service.admin_get_parent(db, current_user.tenant_id, parent_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/{parent_id}", response_model=ParentDetail)
async def update_parent(
    parent_id: UUID,
    payload: UpdateParentRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParentDetail:
    _require_admin(current_user)
    try:
        return await service.admin_update_parent(db, current_user.tenant_id, parent_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{parent_id}/resend-invite", response_model=CreateParentResponse)
async def resend_invite(
    parent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateParentResponse:
    _require_admin(current_user)
    try:
        return await service.admin_resend_invite(db, current_user.tenant_id, parent_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{parent_id}/reset-password")
async def reset_parent_password(
    parent_id: UUID,
    payload: AdminResetParentPasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(current_user)
    try:
        return await service.admin_reset_parent_password(
            db,
            current_user.tenant_id,
            parent_id,
            payload.password,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{parent_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def deactivate_parent(
    parent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_admin(current_user)
    try:
        await service.admin_deactivate_parent(db, current_user.tenant_id, parent_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
