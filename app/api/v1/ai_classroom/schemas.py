"""AI Classroom schemas."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LectureCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    section_id: Optional[UUID] = None
    subject_id: UUID
    title: str = Field(..., min_length=1, max_length=255)


class LectureResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    class_id: UUID
    section_id: Optional[UUID] = None
    subject_id: UUID
    teacher_id: UUID
    title: str
    transcript: str
    structured_notes: Optional[dict] = None
    status: str
    recording_started_at: Optional[datetime] = None
    recording_paused_at: Optional[datetime] = None
    total_recording_seconds: int
    is_active_recording: bool
    audio_buffer_size_bytes: int
    upload_completed: bool = False
    audio_file_path: Optional[str] = None
    processing_stage: Optional[str] = None
    last_chunk_received_at: Optional[datetime] = None
    upload_progress_percent: int = 0
    created_at: datetime
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    section_name: Optional[str] = None
    session_name: Optional[str] = None

    class Config:
        from_attributes = True


class DoubtAskRequest(BaseModel):
    lecture_id: UUID
    question: str = Field(..., min_length=1)


class DoubtMessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    role: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class DoubtAskResponse(BaseModel):
    chat_id: UUID
    answer: str
    message: DoubtMessageResponse


class DoubtChatResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    student_id: UUID
    lecture_id: UUID
    created_at: datetime
    messages: List[DoubtMessageResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class RecordingStartRequest(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    section_id: Optional[UUID] = None
    subject_id: UUID
    title: str = Field(..., min_length=1, max_length=255)


class RecordingStartResponse(BaseModel):
    session_id: UUID
    status: str


class RecordingStatusResponse(BaseModel):
    session_id: UUID
    status: str
    message: str


class StopRecordingResponse(BaseModel):
    """Returned by POST /recording/stop/{session_id}. Frontend then opens WebSocket to upload audio."""

    status: str = "UPLOADING"
    message: str = "Recording stopped. Uploading in progress."


class TranscriptUpdateRequest(BaseModel):
    transcript: str = Field(..., min_length=1)

