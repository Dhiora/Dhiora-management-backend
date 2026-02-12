from datetime import datetime, time
from typing import Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator


def _parse_time_24(v: Union[str, time]) -> time:
    """Parse 24-hour time string (HH:MM or HH:MM:SS) to time."""
    if isinstance(v, time):
        return v
    if isinstance(v, str):
        v = v.strip()
        if len(v) == 5:  # HH:MM
            return datetime.strptime(v, "%H:%M").time()
        return datetime.strptime(v, "%H:%M:%S").time()
    raise ValueError("start_time/end_time must be 24-hour string (e.g. 09:00, 09:45) or time")


class TimetableSlotCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    subject_id: UUID
    teacher_id: UUID
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: Union[str, time] = Field(..., description="24-hour format, e.g. 09:00")
    end_time: Union[str, time] = Field(..., description="24-hour format, e.g. 09:45")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time(cls, v: Union[str, time]) -> time:
        return _parse_time_24(v)


class TimetableSlotUpdate(BaseModel):
    teacher_id: Optional[UUID] = None
    start_time: Optional[Union[str, time]] = Field(None, description="24-hour format, e.g. 09:00")
    end_time: Optional[Union[str, time]] = Field(None, description="24-hour format, e.g. 09:45")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_time(cls, v: Optional[Union[str, time]]) -> Optional[time]:
        if v is None:
            return None
        return _parse_time_24(v)


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

    @field_serializer("start_time", "end_time")
    def serialize_time_24(self, t: time) -> str:
        """Output as 24-hour string HH:MM (e.g. 09:00, 09:45)."""
        return t.strftime("%H:%M")
