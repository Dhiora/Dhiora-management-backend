from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TeacherSubjectAssignmentCreate(BaseModel):
    academic_year_id: UUID
    teacher_id: UUID
    class_id: UUID
    section_id: UUID
    subject_id: UUID = Field(..., description="school.subjects")


class TeacherSubjectAssignmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    teacher_id: UUID
    class_id: UUID
    section_id: UUID
    subject_id: UUID
    created_at: datetime
    teacher_name: Optional[str] = None
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    subject_name: Optional[str] = None

    class Config:
        from_attributes = True
