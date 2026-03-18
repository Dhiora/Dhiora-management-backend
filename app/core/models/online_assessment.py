"""Online Assessment models.

Tables (all in 'school' schema):
  - online_assessments      : the assessment entity (teacher creates)
  - assessment_questions    : questions belonging to an assessment (polymorphic types)
  - assessment_attempts     : one row per student attempt
  - assessment_attempt_answers : one row per question per attempt (auto-graded)
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class OnlineAssessment(Base):
    """Assessment created by a teacher and assigned to a class/section."""

    __tablename__ = "online_assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','UPCOMING','COMPLETED')",
            name="chk_online_assessment_status",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Ownership / assignment
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    class_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.classes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.sections.id", ondelete="RESTRICT"),
        nullable=True,  # NULL = all sections in the class
    )
    subject_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.subjects.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Content
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Config
    duration_minutes = Column(Integer, nullable=False, default=30)
    attempts_allowed = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="DRAFT")
    due_date = Column(Date, nullable=True)

    # Denormalised counters (kept in sync by service layer)
    total_questions = Column(Integer, nullable=False, default=0)
    total_marks = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    questions = relationship(
        "AssessmentQuestion",
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="AssessmentQuestion.order_index",
    )
    attempts = relationship(
        "AssessmentAttempt",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )


class AssessmentQuestion(Base):
    """A single question within an assessment.

    Supports multiple question types (currently MCQ; extensible to
    FILL_IN_BLANK, MULTI_SELECT, SHORT_ANSWER, LONG_ANSWER, …).

    ``options``       – JSONB list of option strings (MCQ / MULTI_SELECT); null otherwise.
    ``correct_answer``– JSONB:
                          MCQ         → single string matching one option
                          MULTI_SELECT→ list of strings matching options
                          FILL_IN_BLANK/ SHORT_ANSWER → single string
                          LONG_ANSWER → null or rubric dict (manual grading)
    """

    __tablename__ = "assessment_questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('MCQ','FILL_IN_BLANK','MULTI_SELECT','SHORT_ANSWER','LONG_ANSWER')",
            name="chk_assessment_question_type",
        ),
        CheckConstraint(
            "difficulty IN ('easy','medium','hard')",
            name="chk_assessment_question_difficulty",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.online_assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question_text = Column(Text, nullable=False)
    question_type = Column(String(30), nullable=False, default="MCQ")

    # For MCQ / MULTI_SELECT: ["option A", "option B", …]
    options = Column(JSONB, nullable=True)
    # Flexible: str | list[str] | null
    correct_answer = Column(JSONB, nullable=True)

    marks = Column(Integer, nullable=False, default=1)
    difficulty = Column(String(10), nullable=True)  # easy | medium | hard
    order_index = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    assessment = relationship("OnlineAssessment", back_populates="questions")
    attempt_answers = relationship(
        "AssessmentAttemptAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
    )


class AssessmentAttempt(Base):
    """One attempt by a student for an assessment."""

    __tablename__ = "assessment_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('IN_PROGRESS','SUBMITTED','ABORTED','TIMED_OUT')",
            name="chk_assessment_attempt_status",
        ),
        # Prevent duplicate IN_PROGRESS attempts
        UniqueConstraint(
            "assessment_id",
            "student_id",
            "attempt_number",
            name="uq_assessment_attempt_number",
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.online_assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    attempt_number = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="IN_PROGRESS")

    # Filled on submission / time-out
    score = Column(Integer, nullable=True)
    total_marks = Column(Integer, nullable=True)
    correct_count = Column(Integer, nullable=True)
    wrong_count = Column(Integer, nullable=True)
    skipped_count = Column(Integer, nullable=True)
    time_taken_seconds = Column(Integer, nullable=True)

    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    assessment = relationship("OnlineAssessment", back_populates="attempts")
    answers = relationship(
        "AssessmentAttemptAnswer",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class AssessmentAttemptAnswer(Base):
    """Student answer for one question within an attempt (auto-graded on submit)."""

    __tablename__ = "assessment_attempt_answers"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "question_id", name="uq_attempt_question_answer"
        ),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.assessment_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.assessment_questions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # null = question was skipped
    selected_answer = Column(JSONB, nullable=True)

    # Filled by auto-grader on submission (null for LONG_ANSWER / manual grading)
    is_correct = Column(Boolean, nullable=True)
    marks_awarded = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    attempt = relationship("AssessmentAttempt", back_populates="answers")
    question = relationship("AssessmentQuestion", back_populates="attempt_answers")
