"""Platform admin service for lead management."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models.lead import FREE_TOKEN_LIMIT, Lead

from .schemas import (
    LeadConvertRequest,
    LeadDetail,
    LeadListResponse,
    LeadSummary,
    LeadTokenStatsResponse,
    LeadUpdateRequest,
)

_VALID_STATUSES = {"new", "contacted", "converted", "lost"}


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _lead_captured(lead: Lead) -> bool:
    return bool(lead.name and lead.phone and lead.email)


def _limit_reached(lead: Lead) -> bool:
    return (lead.total_tokens_used or 0) >= FREE_TOKEN_LIMIT


def _to_summary(lead: Lead) -> LeadSummary:
    return LeadSummary(
        id=_to_uuid(lead.id),
        session_id=lead.session_id,
        name=lead.name,
        phone=lead.phone,
        email=lead.email,
        status=lead.status,
        source=lead.source,
        lead_captured=_lead_captured(lead),
        total_tokens_used=lead.total_tokens_used or 0,
        token_limit=FREE_TOKEN_LIMIT,
        limit_reached=_limit_reached(lead),
        converted_at=lead.converted_at,
        converted_to_tenant_id=_to_uuid(lead.converted_to_tenant_id),
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def _to_detail(lead: Lead) -> LeadDetail:
    return LeadDetail(
        id=_to_uuid(lead.id),
        session_id=lead.session_id,
        name=lead.name,
        phone=lead.phone,
        email=lead.email,
        status=lead.status,
        source=lead.source,
        lead_captured=_lead_captured(lead),
        total_tokens_used=lead.total_tokens_used or 0,
        token_limit=FREE_TOKEN_LIMIT,
        limit_reached=_limit_reached(lead),
        converted_at=lead.converted_at,
        converted_to_tenant_id=_to_uuid(lead.converted_to_tenant_id),
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        conversation=lead.conversation or [],
        notes=lead.notes,
    )


async def list_leads(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> LeadListResponse:
    stmt = select(Lead)
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    stmt = stmt.order_by(desc(Lead.created_at))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Aggregate stats across the filtered set (not just the current page)
    base_stmt = select(Lead)
    if status_filter:
        base_stmt = base_stmt.where(Lead.status == status_filter)

    filtered_leads = base_stmt.subquery()
    stats_stmt = select(
        func.coalesce(func.sum(filtered_leads.c.total_tokens_used), 0),
        func.count(filtered_leads.c.id).filter(
            filtered_leads.c.total_tokens_used >= FREE_TOKEN_LIMIT
        ),
    )
    stats_result = await db.execute(stats_stmt)
    total_tokens, leads_at_limit = stats_result.one()

    # Page
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return LeadListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_tokens_consumed=int(total_tokens or 0),
        leads_at_limit=int(leads_at_limit or 0),
        items=[_to_summary(r) for r in rows],
    )


async def get_lead(db: AsyncSession, lead_id: UUID) -> Optional[LeadDetail]:
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    return _to_detail(lead) if lead else None


async def update_lead(
    db: AsyncSession, lead_id: UUID, payload: LeadUpdateRequest
) -> Optional[LeadDetail]:
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        return None

    if payload.status is not None:
        if payload.status not in _VALID_STATUSES:
            raise ServiceError(
                f"Invalid status. Must be one of: {', '.join(_VALID_STATUSES)}",
                status.HTTP_400_BAD_REQUEST,
            )
        lead.status = payload.status

    if payload.notes is not None:
        lead.notes = payload.notes.strip() or None

    await db.commit()
    await db.refresh(lead)
    return _to_detail(lead)


async def convert_lead(
    db: AsyncSession, lead_id: UUID, payload: LeadConvertRequest
) -> Optional[LeadDetail]:
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        return None

    lead.status = "converted"
    lead.converted_at = datetime.now(timezone.utc)

    if payload.tenant_id:
        lead.converted_to_tenant_id = payload.tenant_id

    if payload.notes:
        lead.notes = payload.notes.strip() or None

    await db.commit()
    await db.refresh(lead)
    return _to_detail(lead)


async def get_token_stats(db: AsyncSession) -> LeadTokenStatsResponse:
    result = await db.execute(
        select(
            func.count(Lead.id),
            func.coalesce(func.sum(Lead.total_tokens_used), 0),
            func.count(Lead.id).filter(Lead.total_tokens_used >= FREE_TOKEN_LIMIT),
            func.count(Lead.id).filter(
                and_(Lead.name.isnot(None), Lead.phone.isnot(None), Lead.email.isnot(None))
            ),
        )
    )
    total, total_tokens, at_limit, with_contact = result.one()

    avg = round(float(total_tokens) / float(total), 1) if total else 0.0

    return LeadTokenStatsResponse(
        total_leads=int(total),
        total_tokens_consumed=int(total_tokens),
        leads_at_limit=int(at_limit),
        leads_with_contact=int(with_contact),
        avg_tokens_per_session=avg,
    )
