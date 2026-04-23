"""Schemas for Platform Super Admin API."""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


# ── Subscription ────────────────────────────────────────────────────────────

class SubscriptionSummary(BaseModel):
    id: UUID
    category: str          # ERP | AI
    status: str            # PENDING | ACTIVE | CANCELLED | EXPIRED
    plan_name: Optional[str] = None
    plan_price: Optional[str] = None
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateSubscriptionRequest(BaseModel):
    """Body for PATCH /platform/schools/{tenant_id}/subscriptions/{sub_id}"""
    status: Optional[str] = None          # ACTIVE | CANCELLED | EXPIRED
    expires_at: Optional[datetime] = None
    subscription_plan_id: Optional[UUID] = None


# ── School list ──────────────────────────────────────────────────────────────

class SchoolListItem(BaseModel):
    tenant_id: UUID
    organization_code: str
    organization_name: str
    organization_type: str
    country: str
    status: str
    created_at: datetime
    total_students: int
    total_employees: int
    active_erp_subscription: Optional[SubscriptionSummary] = None
    active_ai_subscription: Optional[SubscriptionSummary] = None
    total_tokens_consumed: int

    class Config:
        from_attributes = True


class SchoolListResponse(BaseModel):
    total: int
    schools: List[SchoolListItem]


# ── School detail ────────────────────────────────────────────────────────────

class SchoolDetailResponse(BaseModel):
    tenant_id: UUID
    organization_code: str
    organization_name: str
    organization_type: str
    country: str
    timezone: str
    status: str
    created_at: datetime
    total_students: int
    total_employees: int
    subscriptions: List[SubscriptionSummary]
    total_tokens_consumed: int
    tokens_this_month: int
    enabled_modules: List[str]

    class Config:
        from_attributes = True


# ── Token usage ──────────────────────────────────────────────────────────────

class DailyTokenUsage(BaseModel):
    usage_date: date
    input_tokens: int
    output_tokens: int
    total_tokens: int


class StudentTokenUsage(BaseModel):
    student_id: UUID
    student_name: str
    student_email: str
    subscription_plan: Optional[str]
    total_tokens: int
    input_tokens: int
    output_tokens: int


class TokenUsageResponse(BaseModel):
    tenant_id: UUID
    organization_name: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    daily_breakdown: List[DailyTokenUsage]
    top_students: List[StudentTokenUsage]


# ── Platform dashboard ───────────────────────────────────────────────────────

class PlatformDashboardResponse(BaseModel):
    total_schools: int
    active_schools: int
    inactive_schools: int
    total_students: int
    total_employees: int
    subscriptions_active: int
    subscriptions_expired: int
    subscriptions_cancelled: int
    total_tokens_all_time: int
    tokens_this_month: int
    total_whisper_minutes_all_time: float
    whisper_minutes_this_month: float


# ── Whisper usage ─────────────────────────────────────────────────────────────

class DailyWhisperUsage(BaseModel):
    usage_date: date
    duration_seconds: float
    duration_minutes: float


class TeacherWhisperUsage(BaseModel):
    teacher_id: UUID
    teacher_name: str
    teacher_email: str
    total_duration_seconds: float
    total_duration_minutes: float
    session_count: int


class WhisperUsageResponse(BaseModel):
    tenant_id: UUID
    organization_name: str
    total_duration_seconds: float
    total_duration_minutes: float
    daily_breakdown: List[DailyWhisperUsage]
    teachers: List[TeacherWhisperUsage]
