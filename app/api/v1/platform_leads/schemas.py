from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.models.lead import FREE_TOKEN_LIMIT


class LeadSummary(BaseModel):
    id: UUID
    session_id: str
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: str
    source: str
    lead_captured: bool
    total_tokens_used: int = 0
    token_limit: int = FREE_TOKEN_LIMIT
    limit_reached: bool = False
    converted_at: Optional[datetime] = None
    converted_to_tenant_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeadDetail(LeadSummary):
    conversation: List[Dict[str, Any]] = []
    notes: Optional[str] = None


class LeadListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_tokens_consumed: int = Field(
        0, description="Sum of tokens across all leads in this result set"
    )
    leads_at_limit: int = Field(
        0, description="Number of leads that hit the free token limit"
    )
    items: List[LeadSummary]


class LeadUpdateRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = Field(
        None, description="new | contacted | converted | lost"
    )


class LeadConvertRequest(BaseModel):
    tenant_id: Optional[UUID] = Field(
        None, description="Optionally link this lead to an existing school tenant"
    )
    notes: Optional[str] = Field(None, max_length=2000)


class LeadTokenStatsResponse(BaseModel):
    total_leads: int
    total_tokens_consumed: int
    leads_at_limit: int
    leads_with_contact: int = Field(
        0, description="Leads where name + phone + email are all captured"
    )
    avg_tokens_per_session: float = 0.0
