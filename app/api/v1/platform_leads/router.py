"""Platform admin leads API — visible only to PLATFORM_ADMIN / SUPER_ADMIN."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import require_platform_admin
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    LeadConvertRequest,
    LeadDetail,
    LeadListResponse,
    LeadTokenStatsResponse,
    LeadUpdateRequest,
)

router = APIRouter(
    prefix="/api/v1/platform/leads",
    tags=["super-admin / leads"],
    dependencies=[Depends(require_platform_admin)],
)


@router.get("", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(
        None, description="Filter by status: new | contacted | converted | lost"
    ),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
) -> LeadListResponse:
    """List all website leads with pagination and optional status filter."""
    return await service.list_leads(db, page=page, page_size=page_size, status_filter=status)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
) -> LeadDetail:
    """Get full lead detail including complete conversation history."""
    lead = await service.get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadDetail)
async def update_lead(
    lead_id: UUID,
    payload: LeadUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
) -> LeadDetail:
    """Update a lead's status or internal notes."""
    try:
        lead = await service.update_lead(db, lead_id, payload)
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return lead
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{lead_id}/convert", response_model=LeadDetail)
async def convert_lead(
    lead_id: UUID,
    payload: LeadConvertRequest,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
) -> LeadDetail:
    """
    Convert a lead to a client.

    Marks the lead as converted and optionally links it to an existing school tenant.
    """
    try:
        lead = await service.convert_lead(db, lead_id, payload)
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return lead
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/token-stats", response_model=LeadTokenStatsResponse)
async def get_token_stats(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
) -> LeadTokenStatsResponse:
    """Get aggregate free-token usage stats for super admin dashboard cards."""
    return await service.get_token_stats(db)
