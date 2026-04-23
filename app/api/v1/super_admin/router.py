"""Platform Super Admin API — visible only to PLATFORM_ADMIN users."""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.school_profile import service as school_profile_service
from app.api.v1.school_profile.schemas import SchoolProfilePlatformUpdate, SchoolProfileResponse
from app.auth.rbac import require_platform_admin
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    PlatformDashboardResponse,
    SchoolDetailResponse,
    SchoolListResponse,
    SubscriptionSummary,
    TokenUsageResponse,
    UpdateSubscriptionRequest,
    WhisperUsageResponse,
)

router = APIRouter(
    prefix="/api/v1/platform",
    tags=["super-admin / platform"],
    dependencies=[Depends(require_platform_admin)],
)


@router.get("/dashboard", response_model=PlatformDashboardResponse)
async def platform_dashboard(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    Platform-wide summary: total schools, subscriptions by status, AI token consumption.
    """
    try:
        return await service.get_platform_dashboard(db)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/schools", response_model=SchoolListResponse)
async def list_schools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE | INACTIVE"),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    List all registered schools with their subscription and token usage summary.
    """
    try:
        return await service.list_schools(db, page=page, page_size=page_size, status_filter=status)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/schools/{tenant_id}", response_model=SchoolDetailResponse)
async def get_school(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    Full detail for a single school: subscriptions, enabled modules, token usage.
    """
    try:
        return await service.get_school_detail(db, tenant_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch(
    "/schools/{tenant_id}/subscriptions/{sub_id}",
    response_model=SubscriptionSummary,
)
async def update_school_subscription(
    tenant_id: UUID,
    sub_id: UUID,
    payload: UpdateSubscriptionRequest,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    Edit a school's subscription: change status (ACTIVE/CANCELLED/EXPIRED),
    update expiry date, or switch subscription plan.
    """
    try:
        return await service.update_subscription(db, tenant_id, sub_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/schools/{tenant_id}/token-usage", response_model=TokenUsageResponse)
async def school_token_usage(
    tenant_id: UUID,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    AI token consumption for a school.
    Returns total, daily breakdown, and top students by token usage.
    Defaults to all-time if no date range is given.
    """
    try:
        return await service.get_token_usage(db, tenant_id, from_date=from_date, to_date=to_date)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/schools/{tenant_id}/whisper-usage", response_model=WhisperUsageResponse)
async def school_whisper_usage(
    tenant_id: UUID,
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    Whisper audio transcription usage for a school.
    Returns total minutes, daily breakdown, and per-teacher breakdown.
    Whisper is billed at $0.006/minute — use this to track cost per school.
    Defaults to all-time if no date range is given.
    """
    try:
        return await service.get_whisper_usage(db, tenant_id, from_date=from_date, to_date=to_date)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch("/schools/{tenant_id}/profile", response_model=SchoolProfileResponse)
async def update_school_profile(
    tenant_id: UUID,
    payload: SchoolProfilePlatformUpdate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    Update any school's profile — full access including status, country, and organization_type.
    Only PLATFORM_ADMIN / SUPER_ADMIN can call this endpoint.
    """
    try:
        return await school_profile_service.update_school_profile_platform(db, tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/schools/{tenant_id}/profile", response_model=SchoolProfileResponse)
async def get_school_profile_platform(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_platform_admin),
):
    """
    Get the full profile of any school.
    Only PLATFORM_ADMIN / SUPER_ADMIN can call this endpoint.
    """
    try:
        return await school_profile_service.get_school_profile(db, tenant_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
