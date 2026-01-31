from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ----- Staff profile -----
class StaffProfileBase(BaseModel):
    employee_code: Optional[str] = None
    department_id: Optional[UUID] = None
    designation: Optional[str] = None
    join_date: Optional[date] = None


class StaffProfileCreate(StaffProfileBase):
    pass


class StaffProfileUpdate(BaseModel):
    department_id: Optional[UUID] = None
    designation: Optional[str] = None
    join_date: Optional[date] = None


class StaffProfileResponse(StaffProfileBase):
    id: UUID
    user_id: UUID

    class Config:
        from_attributes = True


# ----- Student profile -----
class StudentProfileBase(BaseModel):
    roll_number: Optional[str] = None
    class_id: Optional[UUID] = None
    section_id: Optional[UUID] = None


class StudentProfileCreate(StudentProfileBase):
    pass


class StudentProfileUpdate(BaseModel):
    roll_number: Optional[str] = None
    class_id: Optional[UUID] = None
    section_id: Optional[UUID] = None


class StudentProfileResponse(StudentProfileBase):
    id: UUID
    user_id: UUID

    class Config:
        from_attributes = True


# ----- Employee -----
class EmployeeCreate(BaseModel):
    """Do NOT send user_type, tenant_id, or employee_code (generated in backend). department_id is required."""

    full_name: str = Field(..., min_length=1)
    email: EmailStr
    mobile: Optional[str] = None
    password: str = Field(..., min_length=8)
    role_id: UUID
    department_id: UUID  # Required; must be active department for tenant
    designation: Optional[str] = None
    join_date: Optional[date] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1)
    email: Optional[EmailStr] = None
    mobile: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)
    role_id: Optional[UUID] = None
    status: Optional[str] = None
    department_id: Optional[UUID] = None  # Must be active department for tenant if provided
    designation: Optional[str] = None
    join_date: Optional[date] = None
    # employee_code is NOT editable after creation


class EmployeeResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    full_name: str
    email: str
    mobile: Optional[str] = None
    role: str
    role_id: Optional[UUID] = None
    status: str
    user_type: Optional[str] = None
    created_at: datetime
    staff_profile: Optional[StaffProfileResponse] = None

    class Config:
        from_attributes = True


# ----- Student -----
class StudentCreate(BaseModel):
    """Optional role_id: assign a tenant role (e.g. STUDENT1, STUDENT2). If omitted, role named 'STUDENT' is used."""

    full_name: str = Field(..., min_length=1)
    email: EmailStr
    mobile: Optional[str] = None
    password: str = Field(..., min_length=8)
    roll_number: Optional[str] = None
    class_id: UUID  # Required; must be active class for tenant
    section_id: UUID  # Required; must be active section for tenant
    role_id: Optional[UUID] = Field(None, description="Tenant role to assign (e.g. STUDENT1, STUDENT2). If omitted, default 'STUDENT' role is used.")


class StudentPromote(BaseModel):
    """Promote student to new academic year. Creates new academic record; old record status → PROMOTED."""

    academic_year_id: UUID = Field(..., description="New academic year to promote to")
    class_id: UUID = Field(..., description="New class for the promoted year")
    section_id: UUID = Field(..., description="New section for the promoted year")
    roll_number: Optional[str] = None


class DefaultClassPromotion(BaseModel):
    """Maps from_class → to_class for default promotion."""

    from_class_id: UUID = Field(..., description="Current class of students")
    to_class_id: UUID = Field(..., description="Target class after promotion")


class StudentPromotionOverride(BaseModel):
    """Per-student override: RETAIN (same class) or PROMOTE (new class/section)."""

    student_id: UUID = Field(..., description="Student to override")
    action: str = Field(..., description="RETAIN or PROMOTE")
    to_class_id: Optional[UUID] = Field(None, description="Target class (required if action=PROMOTE)")
    to_section_id: Optional[UUID] = Field(None, description="Target section (required if action=PROMOTE with section)")


class StudentBulkPromote(BaseModel):
    """Bulk promote students from source to target academic year."""

    source_academic_year_id: UUID = Field(..., description="Academic year to promote from")
    target_academic_year_id: UUID = Field(..., description="Academic year to promote to (must be ACTIVE)")
    default_class_promotion: List[DefaultClassPromotion] = Field(
        default_factory=list,
        description="Class mapping: from_class → to_class",
    )
    default_section_behavior: str = Field(
        "AUTO",
        description="AUTO=assign first section; SAME=keep same section name; MANUAL=fail unless in overrides",
    )
    student_overrides: List[StudentPromotionOverride] = Field(
        default_factory=list,
        description="Per-student: RETAIN=same class/section; PROMOTE=use to_class_id, to_section_id",
    )


class PromotionAction(BaseModel):
    """Single promotion action for preview/result."""

    student_id: UUID
    full_name: str
    action: str = Field(..., description="PROMOTED, RETAINED, or SKIPPED")
    from_class_id: Optional[UUID] = None
    from_section_id: Optional[UUID] = None
    to_class_id: Optional[UUID] = None
    to_section_id: Optional[UUID] = None
    reason: Optional[str] = None


class StudentBulkPromoteResult(BaseModel):
    """Result of bulk promotion."""

    promoted_count: int = Field(..., description="Number of students promoted/retained")
    promoted_ids: List[UUID] = Field(default_factory=list)
    skipped: List[dict] = Field(
        default_factory=list,
        description="Students skipped: {student_id, full_name, reason}",
    )
    actions: Optional[List[PromotionAction]] = Field(
        None,
        description="Per-student actions (included when preview=true)",
    )


class StudentUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1)
    email: Optional[EmailStr] = None
    mobile: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)
    status: Optional[str] = None
    roll_number: Optional[str] = None
    class_id: Optional[UUID] = None  # Must be active class for tenant if provided
    section_id: Optional[UUID] = None  # Must be active section for tenant if provided
    role_id: Optional[UUID] = Field(None, description="Change student's role to another tenant role.")


class StudentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    full_name: str
    email: str
    mobile: Optional[str] = None
    role: str
    role_id: Optional[UUID] = None
    status: str
    user_type: Optional[str] = None
    created_at: datetime
    student_profile: Optional[StudentProfileResponse] = None

    class Config:
        from_attributes = True


# ----- Student bulk upload -----
class StudentBulkItem(BaseModel):
    """Single student item for bulk create (JSON or parsed from Excel). Optional role_id assigns a tenant role."""

    full_name: str = Field(..., min_length=1)
    email: EmailStr
    mobile: Optional[str] = None
    password: str = Field(..., min_length=8)
    roll_number: Optional[str] = None
    class_id: UUID
    section_id: UUID
    role_id: Optional[UUID] = Field(None, description="Tenant role to assign. If omitted, default 'STUDENT' role is used.")


class StudentBulkCreate(BaseModel):
    """Request body for POST /api/v1/students/bulk (JSON)."""

    students: List[StudentBulkItem] = Field(..., min_length=1, max_length=500)


class StudentBulkFailureItem(BaseModel):
    """One failed row in bulk create (no password)."""

    index: int = Field(..., description="0-based index in the request students list")
    full_name: str = Field(..., description="Student full_name from request")
    email: str = Field(..., description="Student email from request")
    reason: str = Field(..., description="Why this row was not created")


class StudentBulkResponse(BaseModel):
    """Response for bulk create: list of created students, count, and optional failures with reasons."""

    students: List[StudentResponse]
    created: int
    failed: Optional[List[StudentBulkFailureItem]] = Field(
        None,
        description="Rows that could not be created (invalid class/section, duplicate email, etc.)",
    )


# ----- Paginated query responses -----
class EmployeePaginatedResponse(BaseModel):
    """Paginated response for employee query (POST /api/v1/employees/query)."""

    items: List[EmployeeResponse] = Field(..., description="List of employees")
    total: int = Field(..., ge=0, description="Total count matching the query")
    page: int = Field(..., ge=1, description="Current page")
    page_size: int = Field(..., ge=1, le=100, description="Page size")
    total_pages: int = Field(..., ge=0, description="Total pages")
    search_fields: Optional[List[str]] = Field(None, description="Fields searched by backend when search was used")


class StudentPaginatedResponse(BaseModel):
    """Paginated response for student query (POST /api/v1/students/query)."""

    items: List[StudentResponse] = Field(..., description="List of students")
    total: int = Field(..., ge=0, description="Total count matching the query")
    page: int = Field(..., ge=1, description="Current page")
    page_size: int = Field(..., ge=1, le=100, description="Page size")
    total_pages: int = Field(..., ge=0, description="Total pages")
    search_fields: Optional[List[str]] = Field(None, description="Fields searched by backend when search was used")
