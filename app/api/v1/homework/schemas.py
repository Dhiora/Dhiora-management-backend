"""Homework schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----- Hint -----
class HintItem(BaseModel):
    type: str = Field(..., description="TEXT or VIDEO_LINK")
    content: str = Field(...)
    title: Optional[str] = None


# ----- Homework -----
class HomeworkCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    status: str = Field("DRAFT", description="DRAFT | PUBLISHED | ARCHIVED")
    time_mode: str = Field("NO_TIME", description="NO_TIME | TOTAL_TIME | PER_QUESTION")
    total_time_minutes: Optional[int] = Field(None, ge=1)
    per_question_time_seconds: Optional[int] = Field(None, ge=1)
    teacher_id: Optional[UUID] = Field(None, description="Admin only: assign to teacher. Omit for self.")


class HomeworkUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    status: Optional[str] = None
    time_mode: Optional[str] = None
    total_time_minutes: Optional[int] = Field(None, ge=1)
    per_question_time_seconds: Optional[int] = Field(None, ge=1)


class HomeworkResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    title: str
    description: Optional[str] = None
    status: str
    time_mode: str
    total_time_minutes: Optional[int] = None
    per_question_time_seconds: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Homework Question -----
class HomeworkQuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=1)
    question_type: str = Field(
        ...,
        description="MCQ | FILL_IN_BLANK | SHORT_ANSWER | LONG_ANSWER | MULTI_CHECK",
    )
    options: Optional[List[Any]] = None  # Required for MCQ, MULTI_CHECK
    correct_answer: Optional[Any] = None
    hints: List[Dict[str, Any]] = Field(default_factory=list)
    display_order: int = 0


class HomeworkQuestionUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=1)
    question_type: Optional[str] = None  # MCQ | FILL_IN_BLANK | SHORT_ANSWER | LONG_ANSWER | MULTI_CHECK
    options: Optional[List[Any]] = None
    correct_answer: Optional[Any] = None
    hints: Optional[List[Dict[str, Any]]] = None
    display_order: Optional[int] = None


class HomeworkQuestionResponse(BaseModel):
    id: UUID
    homework_id: UUID
    question_text: str
    question_type: str
    options: Optional[List[Any]] = None
    correct_answer: Optional[Any] = None  # Exclude for student view
    hints: List[Dict[str, Any]] = Field(default_factory=list)
    display_order: int
    created_at: datetime

    class Config:
        from_attributes = True


class HomeworkQuestionsBulkCreate(BaseModel):
    questions: List[HomeworkQuestionCreate] = Field(..., min_length=1, description="List of questions to create")


class HomeworkQuestionsBulkResponse(BaseModel):
    created: List[HomeworkQuestionResponse]
    count: int


# ----- Homework Assignment -----
class HomeworkAssignmentCreate(BaseModel):
    homework_id: UUID
    academic_year_id: UUID
    class_id: UUID
    section_id: Optional[UUID] = None
    due_date: datetime = Field(..., description="Must be in future")


class HomeworkAssignmentResponse(BaseModel):
    id: UUID
    homework_id: UUID
    academic_year_id: UUID
    class_id: UUID
    section_id: Optional[UUID] = None
    due_date: datetime
    assigned_by: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Homework Attempt -----
class HomeworkAttemptStart(BaseModel):
    restart_reason: Optional[str] = Field(None, description="Required if attempt_number > 1")


class HomeworkAttemptResponse(BaseModel):
    id: UUID
    homework_assignment_id: UUID
    student_id: UUID
    attempt_number: int
    restart_reason: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Submission -----
class HomeworkSubmissionCreate(BaseModel):
    answers: Dict[str, Any] = Field(default_factory=dict, description="question_id -> answer")


class HomeworkSubmissionResponse(BaseModel):
    id: UUID
    homework_assignment_id: UUID
    student_id: UUID
    attempt_id: UUID
    answers: Dict[str, Any]
    submitted_at: datetime

    class Config:
        from_attributes = True


# ----- Hint Usage -----
class HintUsageRecord(BaseModel):
    homework_question_id: UUID
    hint_index: int
    viewed_at: datetime


# ----- Analytics -----
class HintUsageSummary(BaseModel):
    question_id: UUID
    hint_index: int
    view_count: int
    student_ids: List[UUID]
