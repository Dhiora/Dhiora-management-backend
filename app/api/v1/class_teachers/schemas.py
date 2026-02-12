from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ClassTeacherAssignmentCreate(BaseModel):
    academic_year_id: UUID = Field(..., description="Academic year (must be ACTIVE)")
    class_id: UUID = Field(..., description="Class")
    section_id: UUID = Field(..., description="Section (must belong to class)")
    teacher_id: UUID = Field(..., description="Teacher/staff user (auth.users)")


class ClassTeacherAssignmentUpdate(BaseModel):
    teacher_id: UUID = Field(..., description="New teacher for this class-section")


class ClassTeacherAssignmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    teacher_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
