from datetime import datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TimetableSlotCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    subject_id: UUID
    teacher_id: UUID
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: time
    end_time: time


class TimetableSlotUpdate(BaseModel):
    teacher_id: Optional[UUID] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None


class TimetableSlotResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    subject_id: UUID
    teacher_id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    created_at: datetime

    class Config:
        from_attributes = True
