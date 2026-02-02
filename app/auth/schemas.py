from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.enums import OrganizationType


class RegisterRequest(BaseModel):
    organization_name: str = Field(..., min_length=3)
    organization_type: OrganizationType
    country: str
    timezone: str
    org_short_code: Optional[str] = Field(None, max_length=10)  # Optional; e.g. "KTS", "SSHS". For identification only.

    selected_modules: List[UUID] = Field(..., min_length=1, description="List of module IDs (UUID) from core.modules")

    admin_full_name: str
    admin_email: EmailStr
    admin_mobile: Optional[str] = None
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)

    accept_terms: bool
    accept_privacy: bool

    @model_validator(mode="after")
    def validate_passwords_and_consents(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        if not self.accept_terms or not self.accept_privacy:
            raise ValueError("Terms and privacy policy must be accepted")
        return self


class RegisterResponse(BaseModel):
    success: bool
    message: str
    tenant_id: UUID
    organization_code: str  # Public identifier; tenant_id remains the internal FK
    org_short_code: Optional[str] = None  # Optional short code for identification (e.g. employee numbers)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserInfo(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: str


class TenantInfo(BaseModel):
    id: UUID
    organization_code: str  # Public identifier; id (tenant_id) remains the internal key
    organization_name: str
    organization_type: str


class AcademicYearContext(BaseModel):
    """Active academic year embedded in the session/token."""

    id: Optional[UUID] = None
    status: Optional[str] = None  # ACTIVE | CLOSED


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo
    tenant: TenantInfo
    modules: List[str]
    academic_year: Optional[AcademicYearContext] = None  # ACTIVE year at login; None if admin and none set
    issued_at: datetime


class RoleCreate(BaseModel):
    name: str
    permissions: Dict[str, Dict[str, bool]]


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[Dict[str, Dict[str, bool]]] = None


class RoleListResponse(BaseModel):
    """Role summary for list: permissions as list of module names (e.g. Admissions, student, homework)."""

    id: UUID
    name: str
    permissions: List[str] = Field(default_factory=list, description="List of module/permission names the role has access to")
    is_default: bool = False


class RoleResponse(BaseModel):
    """Full role with granular permissions (create/read/update/delete per module). Used for get-by-id and create/update."""

    id: UUID
    name: str
    permissions: Dict[str, Dict[str, bool]]
    is_default: bool = False  # True if role is platform default (visible to all tenants)


class CurrentUser(BaseModel):
    """Lightweight representation of the authenticated user for RBAC checks.
    academic_year_id and academic_year_status come from the ACTIVE academic year at login.
    """

    id: UUID
    tenant_id: UUID
    role: str
    permissions: Dict[str, Dict[str, bool]]
    academic_year_id: Optional[UUID] = None  # ACTIVE academic year (is_current=true) at login
    academic_year_status: Optional[str] = None  # ACTIVE | CLOSED; CLOSED => read-only

