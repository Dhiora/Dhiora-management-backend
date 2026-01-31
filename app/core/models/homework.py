"""Homework Management models."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Homework(Base):
    """Homework created by teacher. Not linked to class until assigned."""

    __tablename__ = "homeworks"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="DRAFT")  # DRAFT | PUBLISHED | ARCHIVED
    time_mode = Column(Text, nullable=False, default="NO_TIME")  # NO_TIME | TOTAL_TIME | PER_QUESTION
    total_time_minutes = Column(Integer, nullable=True)
    per_question_time_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    teacher = relationship("User", foreign_keys=[teacher_id])
    questions = relationship("HomeworkQuestion", back_populates="homework", cascade="all, delete-orphan", order_by="HomeworkQuestion.display_order")
    assignments = relationship("HomeworkAssignment", back_populates="homework", cascade="all, delete-orphan")


class HomeworkQuestion(Base):
    """Question within homework. MCQ, FILL_IN_BLANK, SHORT_ANSWER, LONG_ANSWER, MULTI_CHECK."""

    __tablename__ = "homework_questions"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_id = Column(UUID(as_uuid=True), ForeignKey("school.homeworks.id", ondelete="CASCADE"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(Text, nullable=False)  # MCQ | FILL_IN_BLANK | SHORT_ANSWER | LONG_ANSWER | MULTI_CHECK
    options = Column(JSONB, nullable=True)  # MCQ/MULTI_CHECK: ["A","B","C"]; others: null
    correct_answer = Column(JSONB, nullable=True)  # MCQ: index; MULTI_CHECK: [indices]; FILL/SHORT/LONG: string or rubric
    hints = Column(JSONB, nullable=False, default=list)  # [{type, content, title?}]
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    homework = relationship("Homework", back_populates="questions")
    hint_usage = relationship("HomeworkHintUsage", back_populates="question", cascade="all, delete-orphan")


class HomeworkAssignment(Base):
    """Homework assigned to class/section. Visible to students only after assignment."""

    __tablename__ = "homework_assignments"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_id = Column(UUID(as_uuid=True), ForeignKey("school.homeworks.id", ondelete="CASCADE"), nullable=False)
    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("core.academic_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    class_id = Column(UUID(as_uuid=True), ForeignKey("core.classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("core.sections.id"), nullable=True)  # NULL = entire class
    due_date = Column(DateTime(timezone=True), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    homework = relationship("Homework", back_populates="assignments")
    attempts = relationship("HomeworkAttempt", back_populates="assignment", cascade="all, delete-orphan")
    submissions = relationship("HomeworkSubmission", back_populates="assignment", cascade="all, delete-orphan")


class HomeworkAttempt(Base):
    """Student attempt. Multiple allowed; restart requires reason."""

    __tablename__ = "homework_attempts"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_assignment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.homework_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, nullable=False, default=1)
    restart_reason = Column(Text, nullable=True)  # Required if attempt_number > 1
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    assignment = relationship("HomeworkAssignment", back_populates="attempts")
    submission = relationship("HomeworkSubmission", back_populates="attempt", uselist=False, cascade="all, delete-orphan")
    hint_usage = relationship("HomeworkHintUsage", back_populates="attempt", cascade="all, delete-orphan")


class HomeworkSubmission(Base):
    """One submission per attempt."""

    __tablename__ = "homework_submissions"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_assignment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.homework_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.homework_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    answers = Column(JSONB, nullable=False, default=dict)  # {question_id: answer}
    submitted_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    assignment = relationship("HomeworkAssignment", back_populates="submissions")
    attempt = relationship("HomeworkAttempt", back_populates="submission")


class HomeworkHintUsage(Base):
    """Tracks when student viewed a hint."""

    __tablename__ = "homework_hint_usage"
    __table_args__ = {"schema": "school"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.homework_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    homework_attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school.homework_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    hint_index = Column(Integer, nullable=False)
    viewed_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    question = relationship("HomeworkQuestion", back_populates="hint_usage")
    attempt = relationship("HomeworkAttempt", back_populates="hint_usage")
