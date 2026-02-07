from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ClassSubjectCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    subject_id: UUID = Field(..., description="school.subjects")


class ClassSubjectResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    class_id: UUID
    subject_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class ClassSubjectBulkCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    subject_ids: List[UUID] = Field(..., min_length=1)
