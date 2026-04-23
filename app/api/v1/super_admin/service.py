"""Service layer for Platform Super Admin API."""

from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models import (
    AITokenUsage,
    AIWhisperUsage,
    Tenant,
    TenantModule,
    TenantSubscription,
    SubscriptionPlan,
)

from .schemas import (
    DailyTokenUsage,
    DailyWhisperUsage,
    PlatformDashboardResponse,
    SchoolDetailResponse,
    SchoolListItem,
    SchoolListResponse,
    StudentTokenUsage,
    SubscriptionSummary,
    TeacherWhisperUsage,
    TokenUsageResponse,
    UpdateSubscriptionRequest,
    WhisperUsageResponse,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _count_users_by_type(db: AsyncSession, tenant_id: UUID, user_type: str) -> int:
    result = await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.user_type == user_type,
            User.status == "ACTIVE",
        )
    )
    return result.scalar() or 0


async def _count_students(db: AsyncSession, tenant_id: UUID) -> int:
    return await _count_users_by_type(db, tenant_id, "student")


async def _count_employees(db: AsyncSession, tenant_id: UUID) -> int:
    return await _count_users_by_type(db, tenant_id, "employee")


async def _total_tokens(db: AsyncSession, tenant_id: UUID, since: Optional[date] = None) -> int:
    stmt = select(func.coalesce(func.sum(AITokenUsage.total_tokens), 0)).where(
        AITokenUsage.tenant_id == tenant_id
    )
    if since:
        stmt = stmt.where(AITokenUsage.usage_date >= since)
    result = await db.execute(stmt)
    return result.scalar() or 0


async def _build_subscription_summary(sub: TenantSubscription) -> SubscriptionSummary:
    plan_name = None
    plan_price = None
    if sub.plan:
        plan_name = sub.plan.name
        plan_price = sub.plan.price
    return SubscriptionSummary(
        id=sub.id,
        category=sub.category,
        status=sub.status,
        plan_name=plan_name,
        plan_price=plan_price,
        activated_at=sub.activated_at,
        expires_at=sub.expires_at,
        created_at=sub.created_at,
    )


# ── List all schools ──────────────────────────────────────────────────────────

async def list_schools(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> SchoolListResponse:
    offset = (page - 1) * page_size

    stmt = select(Tenant).order_by(Tenant.created_at.desc())
    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter.upper())

    count_stmt = select(func.count(Tenant.id))
    if status_filter:
        count_stmt = count_stmt.where(Tenant.status == status_filter.upper())

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    tenants = result.scalars().all()

    schools: List[SchoolListItem] = []
    for tenant in tenants:
        students = await _count_students(db, tenant.id)
        employees = await _count_employees(db, tenant.id)
        tokens = await _total_tokens(db, tenant.id)

        # Get latest active subscriptions
        subs_result = await db.execute(
            select(TenantSubscription)
            .where(
                TenantSubscription.tenant_id == tenant.id,
                TenantSubscription.status == "ACTIVE",
            )
            .order_by(TenantSubscription.activated_at.desc())
        )
        active_subs = subs_result.scalars().all()

        erp_sub = next((s for s in active_subs if s.category == "ERP"), None)
        ai_sub = next((s for s in active_subs if s.category == "AI"), None)

        # Eagerly load plan for each sub
        erp_summary = None
        if erp_sub:
            if erp_sub.subscription_plan_id:
                erp_sub.plan = await db.get(SubscriptionPlan, erp_sub.subscription_plan_id)
            erp_summary = await _build_subscription_summary(erp_sub)

        ai_summary = None
        if ai_sub:
            if ai_sub.subscription_plan_id:
                ai_sub.plan = await db.get(SubscriptionPlan, ai_sub.subscription_plan_id)
            ai_summary = await _build_subscription_summary(ai_sub)

        schools.append(
            SchoolListItem(
                tenant_id=tenant.id,
                organization_code=tenant.organization_code,
                organization_name=tenant.organization_name,
                organization_type=tenant.organization_type,
                country=tenant.country,
                status=tenant.status,
                created_at=tenant.created_at,
                total_students=students,
                total_employees=employees,
                active_erp_subscription=erp_summary,
                active_ai_subscription=ai_summary,
                total_tokens_consumed=tokens,
            )
        )

    return SchoolListResponse(total=total, schools=schools)


# ── Get school detail ─────────────────────────────────────────────────────────

async def get_school_detail(db: AsyncSession, tenant_id: UUID) -> SchoolDetailResponse:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise ServiceError("School not found", status.HTTP_404_NOT_FOUND)

    students = await _count_students(db, tenant_id)
    employees = await _count_employees(db, tenant_id)
    tokens_all = await _total_tokens(db, tenant_id)

    today = date.today()
    month_start = today.replace(day=1)
    tokens_month = await _total_tokens(db, tenant_id, since=month_start)

    subs_result = await db.execute(
        select(TenantSubscription)
        .where(TenantSubscription.tenant_id == tenant_id)
        .order_by(TenantSubscription.created_at.desc())
    )
    all_subs = subs_result.scalars().all()

    sub_summaries = []
    for sub in all_subs:
        if sub.subscription_plan_id:
            sub.plan = await db.get(SubscriptionPlan, sub.subscription_plan_id)
        else:
            sub.plan = None
        sub_summaries.append(await _build_subscription_summary(sub))

    modules_result = await db.execute(
        select(TenantModule.module_key).where(
            TenantModule.tenant_id == tenant_id,
            TenantModule.is_enabled == True,
        )
    )
    enabled_modules = [row[0] for row in modules_result.fetchall()]

    return SchoolDetailResponse(
        tenant_id=tenant.id,
        organization_code=tenant.organization_code,
        organization_name=tenant.organization_name,
        organization_type=tenant.organization_type,
        country=tenant.country,
        timezone=tenant.timezone,
        status=tenant.status,
        created_at=tenant.created_at,
        total_students=students,
        total_employees=employees,
        subscriptions=sub_summaries,
        total_tokens_consumed=tokens_all,
        tokens_this_month=tokens_month,
        enabled_modules=enabled_modules,
    )


# ── Update subscription ───────────────────────────────────────────────────────

async def update_subscription(
    db: AsyncSession,
    tenant_id: UUID,
    sub_id: UUID,
    payload: UpdateSubscriptionRequest,
) -> SubscriptionSummary:
    sub = await db.get(TenantSubscription, sub_id)
    if not sub or sub.tenant_id != tenant_id:
        raise ServiceError("Subscription not found", status.HTTP_404_NOT_FOUND)

    if payload.status is not None:
        allowed = {"ACTIVE", "CANCELLED", "EXPIRED", "PENDING"}
        if payload.status.upper() not in allowed:
            raise ServiceError(
                f"Invalid status. Must be one of: {', '.join(allowed)}",
                status.HTTP_400_BAD_REQUEST,
            )
        new_status = payload.status.upper()
        # If activating, set activated_at if not already set
        if new_status == "ACTIVE" and sub.activated_at is None:
            sub.activated_at = datetime.now(timezone.utc)
        sub.status = new_status

    if payload.expires_at is not None:
        sub.expires_at = payload.expires_at

    if payload.subscription_plan_id is not None:
        plan = await db.get(SubscriptionPlan, payload.subscription_plan_id)
        if not plan:
            raise ServiceError("Subscription plan not found", status.HTTP_404_NOT_FOUND)
        sub.subscription_plan_id = payload.subscription_plan_id

    await db.commit()
    await db.refresh(sub)

    if sub.subscription_plan_id:
        sub.plan = await db.get(SubscriptionPlan, sub.subscription_plan_id)
    else:
        sub.plan = None

    return await _build_subscription_summary(sub)


# ── Token usage ───────────────────────────────────────────────────────────────

async def get_token_usage(
    db: AsyncSession,
    tenant_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> TokenUsageResponse:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise ServiceError("School not found", status.HTTP_404_NOT_FOUND)

    base_filter = [AITokenUsage.tenant_id == tenant_id]
    if from_date:
        base_filter.append(AITokenUsage.usage_date >= from_date)
    if to_date:
        base_filter.append(AITokenUsage.usage_date <= to_date)

    # Totals
    totals_result = await db.execute(
        select(
            func.coalesce(func.sum(AITokenUsage.input_tokens), 0),
            func.coalesce(func.sum(AITokenUsage.output_tokens), 0),
            func.coalesce(func.sum(AITokenUsage.total_tokens), 0),
        ).where(*base_filter)
    )
    row = totals_result.one()
    total_input, total_output, total_all = row[0], row[1], row[2]

    # Daily breakdown
    daily_result = await db.execute(
        select(
            AITokenUsage.usage_date,
            func.sum(AITokenUsage.input_tokens).label("input"),
            func.sum(AITokenUsage.output_tokens).label("output"),
            func.sum(AITokenUsage.total_tokens).label("total"),
        )
        .where(*base_filter)
        .group_by(AITokenUsage.usage_date)
        .order_by(AITokenUsage.usage_date)
    )
    daily = [
        DailyTokenUsage(
            usage_date=r.usage_date,
            input_tokens=r.input,
            output_tokens=r.output,
            total_tokens=r.total,
        )
        for r in daily_result.fetchall()
    ]

    # Top students by token usage (up to 20)
    student_result = await db.execute(
        select(
            AITokenUsage.student_id,
            func.sum(AITokenUsage.input_tokens).label("input"),
            func.sum(AITokenUsage.output_tokens).label("output"),
            func.sum(AITokenUsage.total_tokens).label("total"),
        )
        .where(*base_filter, AITokenUsage.student_id != None)
        .group_by(AITokenUsage.student_id)
        .order_by(func.sum(AITokenUsage.total_tokens).desc())
        .limit(20)
    )
    student_rows = student_result.fetchall()

    top_students: List[StudentTokenUsage] = []
    for sr in student_rows:
        user = await db.get(User, sr.student_id)
        if not user:
            continue
        top_students.append(
            StudentTokenUsage(
                student_id=sr.student_id,
                student_name=user.full_name,
                student_email=user.email,
                subscription_plan=user.subscription_plan,
                total_tokens=sr.total,
                input_tokens=sr.input,
                output_tokens=sr.output,
            )
        )

    return TokenUsageResponse(
        tenant_id=tenant_id,
        organization_name=tenant.organization_name,
        total_tokens=total_all,
        input_tokens=total_input,
        output_tokens=total_output,
        daily_breakdown=daily,
        top_students=top_students,
    )


# ── Whisper usage ─────────────────────────────────────────────────────────────

async def get_whisper_usage(
    db: AsyncSession,
    tenant_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> WhisperUsageResponse:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise ServiceError("School not found", status.HTTP_404_NOT_FOUND)

    base_filter = [AIWhisperUsage.tenant_id == tenant_id]
    if from_date:
        base_filter.append(AIWhisperUsage.usage_date >= from_date)
    if to_date:
        base_filter.append(AIWhisperUsage.usage_date <= to_date)

    # Totals
    totals_result = await db.execute(
        select(
            func.coalesce(func.sum(AIWhisperUsage.audio_duration_seconds), 0.0),
        ).where(*base_filter)
    )
    total_seconds = float(totals_result.scalar() or 0.0)

    # Daily breakdown
    daily_result = await db.execute(
        select(
            AIWhisperUsage.usage_date,
            func.sum(AIWhisperUsage.audio_duration_seconds).label("seconds"),
        )
        .where(*base_filter)
        .group_by(AIWhisperUsage.usage_date)
        .order_by(AIWhisperUsage.usage_date)
    )
    daily = [
        DailyWhisperUsage(
            usage_date=r.usage_date,
            duration_seconds=round(r.seconds, 2),
            duration_minutes=round(r.seconds / 60, 2),
        )
        for r in daily_result.fetchall()
    ]

    # Per-teacher breakdown
    teacher_result = await db.execute(
        select(
            AIWhisperUsage.teacher_id,
            func.sum(AIWhisperUsage.audio_duration_seconds).label("seconds"),
            func.count(AIWhisperUsage.id).label("session_count"),
        )
        .where(*base_filter, AIWhisperUsage.teacher_id != None)
        .group_by(AIWhisperUsage.teacher_id)
        .order_by(func.sum(AIWhisperUsage.audio_duration_seconds).desc())
    )
    teacher_rows = teacher_result.fetchall()

    teachers: List[TeacherWhisperUsage] = []
    for tr in teacher_rows:
        user = await db.get(User, tr.teacher_id)
        if not user:
            continue
        teachers.append(
            TeacherWhisperUsage(
                teacher_id=tr.teacher_id,
                teacher_name=user.full_name,
                teacher_email=user.email,
                total_duration_seconds=round(tr.seconds, 2),
                total_duration_minutes=round(tr.seconds / 60, 2),
                session_count=tr.session_count,
            )
        )

    return WhisperUsageResponse(
        tenant_id=tenant_id,
        organization_name=tenant.organization_name,
        total_duration_seconds=round(total_seconds, 2),
        total_duration_minutes=round(total_seconds / 60, 2),
        daily_breakdown=daily,
        teachers=teachers,
    )


# ── Platform dashboard ────────────────────────────────────────────────────────

async def get_platform_dashboard(db: AsyncSession) -> PlatformDashboardResponse:
    # Schools
    total_schools_r = await db.execute(select(func.count(Tenant.id)))
    total_schools = total_schools_r.scalar() or 0

    active_schools_r = await db.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "ACTIVE")
    )
    active_schools = active_schools_r.scalar() or 0

    # Users
    total_students_r = await db.execute(
        select(func.count(User.id)).where(User.user_type == "student", User.status == "ACTIVE")
    )
    total_students = total_students_r.scalar() or 0

    total_employees_r = await db.execute(
        select(func.count(User.id)).where(User.user_type == "employee", User.status == "ACTIVE")
    )
    total_employees = total_employees_r.scalar() or 0

    # Subscriptions
    subs_active_r = await db.execute(
        select(func.count(TenantSubscription.id)).where(TenantSubscription.status == "ACTIVE")
    )
    subs_active = subs_active_r.scalar() or 0

    subs_expired_r = await db.execute(
        select(func.count(TenantSubscription.id)).where(TenantSubscription.status == "EXPIRED")
    )
    subs_expired = subs_expired_r.scalar() or 0

    subs_cancelled_r = await db.execute(
        select(func.count(TenantSubscription.id)).where(TenantSubscription.status == "CANCELLED")
    )
    subs_cancelled = subs_cancelled_r.scalar() or 0

    # Tokens
    total_tokens_r = await db.execute(
        select(func.coalesce(func.sum(AITokenUsage.total_tokens), 0))
    )
    total_tokens = total_tokens_r.scalar() or 0

    today = date.today()
    month_start = today.replace(day=1)
    tokens_month_r = await db.execute(
        select(func.coalesce(func.sum(AITokenUsage.total_tokens), 0)).where(
            AITokenUsage.usage_date >= month_start
        )
    )
    tokens_month = tokens_month_r.scalar() or 0

    # Whisper minutes
    whisper_total_r = await db.execute(
        select(func.coalesce(func.sum(AIWhisperUsage.audio_duration_seconds), 0.0))
    )
    whisper_total_s = float(whisper_total_r.scalar() or 0.0)

    whisper_month_r = await db.execute(
        select(func.coalesce(func.sum(AIWhisperUsage.audio_duration_seconds), 0.0)).where(
            AIWhisperUsage.usage_date >= month_start
        )
    )
    whisper_month_s = float(whisper_month_r.scalar() or 0.0)

    return PlatformDashboardResponse(
        total_schools=total_schools,
        active_schools=active_schools,
        inactive_schools=total_schools - active_schools,
        total_students=total_students,
        total_employees=total_employees,
        subscriptions_active=subs_active,
        subscriptions_expired=subs_expired,
        subscriptions_cancelled=subs_cancelled,
        total_tokens_all_time=total_tokens,
        tokens_this_month=tokens_month,
        total_whisper_minutes_all_time=round(whisper_total_s / 60, 2),
        whisper_minutes_this_month=round(whisper_month_s / 60, 2),
    )
