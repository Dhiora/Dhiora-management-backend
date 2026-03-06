"""Exam management schemas."""

from datetime import date, datetime, time
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----- Exam Types -----
class ExamTypeCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None


class ExamTypeResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Exams -----
class ExamCreate(BaseModel):
    exam_type_id: UUID
    name: str = Field(..., max_length=255)
    class_id: UUID
    section_id: UUID
    start_date: date
    end_date: date
    status: str = Field("draft", description="draft | scheduled | completed")


class ExamResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    exam_type_id: UUID
    name: str
    class_id: UUID
    section_id: UUID
    start_date: date
    end_date: date
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Exam Schedule -----
class ExamScheduleCreate(BaseModel):
    subject_id: UUID
    class_id: UUID
    section_id: UUID
    exam_date: date
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    room_number: Optional[str] = Field(None, max_length=50)
    invigilator_teacher_id: Optional[UUID] = None


class ExamScheduleResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    exam_id: UUID
    subject_id: UUID
    class_id: UUID
    section_id: UUID
    exam_date: date
    start_time: str
    end_time: str
    room_number: Optional[str] = None
    invigilator_teacher_id: Optional[UUID] = None
    created_at: datetime
    subject_name: Optional[str] = None
    invigilator_name: Optional[str] = None

    class Config:
        from_attributes = True


class InvigilatorUpdate(BaseModel):
    invigilator_teacher_id: Optional[UUID] = None
