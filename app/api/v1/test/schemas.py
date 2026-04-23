from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.enums import OrganizationType


class TestFullAccessRegisterRequest(BaseModel):
    """Register an organization with every enabled module for the org type and free tenant subscriptions (test only)."""

    organization_name: str = Field(..., min_length=3)
    organization_type: OrganizationType
    country: str
    timezone: str
    org_short_code: Optional[str] = Field(None, max_length=10)

    admin_full_name: str
    admin_email: EmailStr
    admin_mobile: Optional[str] = None
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def validate_passwords(self) -> "TestFullAccessRegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class ResetDatabaseResponse(BaseModel):
    success: bool
    message: str
    tables_truncated: int
