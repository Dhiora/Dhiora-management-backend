from datetime import datetime
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

    class Config:
        from_attributes = True
