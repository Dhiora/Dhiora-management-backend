from datetime import datetime, time
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator


class TimeSlotCreateItem(BaseModel):
    name: str = Field(..., max_length=100)
    start_time: str = Field(..., description="24-hour format HH:MM")
    end_time: str = Field(..., description="24-hour format HH:MM")
    slot_type: str = Field(..., description="CLASS or BREAK")
    order_index: int = Field(..., ge=1)

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        v = v.strip()
        # Validate parseable
        datetime.strptime(v, "%H:%M")
        return v


class TimeSlotCreateRequest(BaseModel):
    slots: List[TimeSlotCreateItem]


class TimeSlotResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    start_time: time
    end_time: time
    slot_type: str
    order_index: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("start_time", "end_time")
    def serialize_time(self, v: time) -> str:
        return v.strftime("%H:%M")

