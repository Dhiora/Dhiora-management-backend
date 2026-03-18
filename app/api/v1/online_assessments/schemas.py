"""Pydantic schemas for Online Assessment API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Question schemas
# ---------------------------------------------------------------------------

class QuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=1)
    question_type: str = Field("MCQ", description="MCQ | FILL_IN_BLANK | MULTI_SELECT | SHORT_ANSWER | LONG_ANSWER")
    options: Optional[List[str]] = Field(None, description="Required for MCQ / MULTI_SELECT")
    correct_answer: Optional[Any] = Field(
        None,
        description=(
            "MCQ: string matching one option; "
            "MULTI_SELECT: list of strings; "
            "FILL_IN_BLANK/SHORT_ANSWER: string; "
            "LONG_ANSWER: null or rubric dict"
        ),
    )
    marks: int = Field(1, ge=1)
    difficulty: Optional[str] = Field(None, description="easy | medium | hard")
    order_index: int = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_question_type_fields(self) -> "QuestionCreate":
        qt = self.question_type.upper()
        valid_types = {"MCQ", "FILL_IN_BLANK", "MULTI_SELECT", "SHORT_ANSWER", "LONG_ANSWER"}
        if qt not in valid_types:
            raise ValueError(f"question_type must be one of {valid_types}")
        if qt in ("MCQ", "MULTI_SELECT") and not self.options:
            raise ValueError("options are required for MCQ and MULTI_SELECT questions")
        if self.difficulty and self.difficulty.lower() not in ("easy", "medium", "hard"):
            raise ValueError("difficulty must be easy, medium, or hard")
        self.question_type = qt
        if self.difficulty:
            self.difficulty = self.difficulty.lower()
        return self


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=1)
    question_type: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[Any] = None
    marks: Optional[int] = Field(None, ge=1)
    difficulty: Optional[str] = None
    order_index: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_fields(self) -> "QuestionUpdate":
        if self.question_type:
            qt = self.question_type.upper()
            valid_types = {"MCQ", "FILL_IN_BLANK", "MULTI_SELECT", "SHORT_ANSWER", "LONG_ANSWER"}
            if qt not in valid_types:
                raise ValueError(f"question_type must be one of {valid_types}")
            self.question_type = qt
        if self.difficulty:
            d = self.difficulty.lower()
            if d not in ("easy", "medium", "hard"):
                raise ValueError("difficulty must be easy, medium, or hard")
            self.difficulty = d
        return self


class QuestionsBulkCreate(BaseModel):
    questions: List[QuestionCreate] = Field(..., min_length=1)


class QuestionResponse(BaseModel):
    id: UUID
    assessment_id: UUID
    question_text: str
    question_type: str
    options: Optional[List[str]]
    correct_answer: Optional[Any]  # omitted in student view
    marks: int
    difficulty: Optional[str]
    order_index: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Assessment schemas
# ---------------------------------------------------------------------------

class AssessmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    academic_year_id: UUID
    class_id: UUID
    section_id: Optional[UUID] = None
    subject_id: Optional[UUID] = None
    duration_minutes: int = Field(30, ge=5)
    attempts_allowed: int = Field(1, ge=1, le=10)
    status: str = Field("DRAFT", description="DRAFT | ACTIVE | UPCOMING | COMPLETED")
    due_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_status(self) -> "AssessmentCreate":
        valid = {"DRAFT", "ACTIVE", "UPCOMING", "COMPLETED"}
        if self.status.upper() not in valid:
            raise ValueError(f"status must be one of {valid}")
        self.status = self.status.upper()
        return self


class AssessmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    subject_id: Optional[UUID] = None
    duration_minutes: Optional[int] = Field(None, ge=5)
    attempts_allowed: Optional[int] = Field(None, ge=1, le=10)
    status: Optional[str] = None
    due_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_status(self) -> "AssessmentUpdate":
        if self.status:
            valid = {"DRAFT", "ACTIVE", "UPCOMING", "COMPLETED"}
            if self.status.upper() not in valid:
                raise ValueError(f"status must be one of {valid}")
            self.status = self.status.upper()
        return self


class AssessmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    created_by: Optional[UUID]
    academic_year_id: UUID
    class_id: UUID
    section_id: Optional[UUID]
    subject_id: Optional[UUID]
    title: str
    description: Optional[str]
    duration_minutes: int
    attempts_allowed: int
    status: str
    due_date: Optional[date]
    total_questions: int
    total_marks: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssessmentListItem(BaseModel):
    """List-view shape – includes per-student attempt info."""

    id: UUID
    title: str
    subject: Optional[str]       # subject name (resolved)
    class_label: str             # "Class 9 – Section A" (resolved)
    total_questions: int
    total_marks: int
    duration_minutes: int
    status: str
    due_date: Optional[date]
    attempts_allowed: int
    attempts_taken: int          # how many attempts current user has used
    description: Optional[str]
    score: Optional[int]         # best score if completed attempt exists


# ---------------------------------------------------------------------------
# Start attempt
# ---------------------------------------------------------------------------

class StartAttemptResponse(BaseModel):
    attempt_id: UUID
    questions: List[QuestionResponse]


# ---------------------------------------------------------------------------
# Submit answers
# ---------------------------------------------------------------------------

class SubmitAnswersRequest(BaseModel):
    attempt_id: UUID
    answers: Dict[str, Any] = Field(
        ...,
        description="Map of question_id (str) → selected answer (str or list[str])",
    )
    time_taken_seconds: int = Field(..., ge=0)


class SubmitAnswersResponse(BaseModel):
    attempt_id: UUID
    score: int
    total_marks: int
    correct: int
    wrong: int
    skipped: int
    time_taken_seconds: int


# ---------------------------------------------------------------------------
# Attempt detail (review)
# ---------------------------------------------------------------------------

class AttemptAnswerDetail(BaseModel):
    question_id: UUID
    question_text: str
    question_type: str
    options: Optional[List[str]]
    correct_answer: Optional[Any]
    selected_answer: Optional[Any]
    is_correct: Optional[bool]
    marks_awarded: Optional[int]
    marks: int


class AttemptDetailResponse(BaseModel):
    attempt_id: UUID
    assessment_id: UUID
    student_id: UUID
    attempt_number: int
    status: str
    score: Optional[int]
    total_marks: Optional[int]
    correct_count: Optional[int]
    wrong_count: Optional[int]
    skipped_count: Optional[int]
    time_taken_seconds: Optional[int]
    started_at: datetime
    submitted_at: Optional[datetime]
    answers: List[AttemptAnswerDetail]


# ---------------------------------------------------------------------------
# Teacher: results overview
# ---------------------------------------------------------------------------

class StudentResultItem(BaseModel):
    student_id: UUID
    student_name: str
    attempt_number: int
    attempt_id: UUID
    status: str
    score: Optional[int]
    total_marks: Optional[int]
    correct_count: Optional[int]
    wrong_count: Optional[int]
    skipped_count: Optional[int]
    time_taken_seconds: Optional[int]
    submitted_at: Optional[datetime]


class AssessmentResultsResponse(BaseModel):
    assessment_id: UUID
    title: str
    total_marks: int
    results: List[StudentResultItem]
