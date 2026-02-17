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
    class_name: Optional[str] = Field(None, description="Class name (core.classes); populated in list response")
    subject_name: Optional[str] = Field(None, description="Subject name (school.subjects); populated in list response")

    class Config:
        from_attributes = True


class ClassSubjectUpdate(BaseModel):
    """At least one of class_id or subject_id must be provided."""
    class_id: Optional[UUID] = Field(None, description="Reassign to another class (core.classes)")
    subject_id: Optional[UUID] = Field(None, description="Change to another subject (school.subjects)")


class ClassSubjectBulkCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    subject_ids: List[UUID] = Field(..., min_length=1)
