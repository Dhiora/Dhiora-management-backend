from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SchoolProfileResponse(BaseModel):
    """Full school profile combining Tenant core fields and extended SchoolProfile fields."""

    # From Tenant
    tenant_id: UUID
    organization_code: str
    organization_name: str
    organization_type: str
    country: str
    timezone: str
    status: str
    org_short_code: Optional[str] = None

    # From SchoolProfile
    logo_url: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    principal_name: Optional[str] = None
    established_year: Optional[str] = None
    affiliation_board: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SchoolProfileUpdate(BaseModel):
    """
    Fields a school ADMIN or role-permitted user can update.
    Sensitive fields (status, organization_type, country) are excluded.
    """

    organization_name: Optional[str] = Field(None, min_length=3)
    timezone: Optional[str] = None
    org_short_code: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    principal_name: Optional[str] = None
    established_year: Optional[str] = Field(None, max_length=10)
    affiliation_board: Optional[str] = None


class SchoolProfilePlatformUpdate(SchoolProfileUpdate):
    """
    Extended update schema for PLATFORM_ADMIN / SUPER_ADMIN.
    Includes all fields from SchoolProfileUpdate plus privileged tenant fields.
    """

    organization_type: Optional[str] = None
    country: Optional[str] = None
    status: Optional[str] = None
