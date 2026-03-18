"""Service layer for Online Assessment."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models.academic_year import AcademicYear
from app.core.models.class_model import SchoolClass
from app.core.models.online_assessment import (
    AssessmentAttempt,
    AssessmentAttemptAnswer,
    AssessmentQuestion,
    OnlineAssessment,
)
from app.core.models.school_subject import SchoolSubject
from app.core.models.section_model import Section
from app.core.models.student_academic_record import StudentAcademicRecord

from .schemas import (
    AssessmentCreate,
    AssessmentListItem,
    AssessmentResultsResponse,
    AssessmentUpdate,
    AttemptAnswerDetail,
    AttemptDetailResponse,
    QuestionCreate,
    QuestionUpdate,
    StartAttemptResponse,
    StudentResultItem,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEACHER_ROLES = {"SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN", "EMPLOYEE"}
STUDENT_ROLE = "STUDENT"


def _is_teacher(role: str) -> bool:
    return role.upper() in TEACHER_ROLES


async def _get_assessment_or_404(
    db: AsyncSession, tenant_id: UUID, assessment_id: UUID
) -> OnlineAssessment:
    result = await db.execute(
        select(OnlineAssessment).where(
            OnlineAssessment.tenant_id == tenant_id,
            OnlineAssessment.id == assessment_id,
        )
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise ServiceError("Assessment not found", status.HTTP_404_NOT_FOUND)
    return assessment


async def _refresh_counters(db: AsyncSession, assessment: OnlineAssessment) -> None:
    """Recalculate total_questions and total_marks from questions table."""
    result = await db.execute(
        select(
            func.count(AssessmentQuestion.id),
            func.coalesce(func.sum(AssessmentQuestion.marks), 0),
        ).where(AssessmentQuestion.assessment_id == assessment.id)
    )
    count, total = result.one()
    assessment.total_questions = count
    assessment.total_marks = int(total)


# ---------------------------------------------------------------------------
# Assessment CRUD
# ---------------------------------------------------------------------------

async def create_assessment(
    db: AsyncSession, tenant_id: UUID, user_id: UUID, payload: AssessmentCreate
) -> OnlineAssessment:
    # Validate academic_year belongs to tenant
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)

    # Validate class belongs to tenant
    sc = await db.get(SchoolClass, payload.class_id)
    if not sc or sc.tenant_id != tenant_id:
        raise ServiceError("Class not found", status.HTTP_404_NOT_FOUND)

    assessment = OnlineAssessment(
        tenant_id=tenant_id,
        created_by=user_id,
        academic_year_id=payload.academic_year_id,
        class_id=payload.class_id,
        section_id=payload.section_id,
        subject_id=payload.subject_id,
        title=payload.title,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        attempts_allowed=payload.attempts_allowed,
        status=payload.status,
        due_date=payload.due_date,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment


async def update_assessment(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    assessment_id: UUID,
    payload: AssessmentUpdate,
) -> OnlineAssessment:
    assessment = await _get_assessment_or_404(db, tenant_id, assessment_id)

    # Only creator or admin can update
    if not _is_teacher(role):
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(assessment, field, value)
    assessment.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(assessment)
    return assessment


async def delete_assessment(
    db: AsyncSession, tenant_id: UUID, user_id: UUID, role: str, assessment_id: UUID
) -> None:
    assessment = await _get_assessment_or_404(db, tenant_id, assessment_id)
    if not _is_teacher(role):
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)
    if assessment.status != "DRAFT":
        raise ServiceError(
            "Only DRAFT assessments can be deleted", status.HTTP_400_BAD_REQUEST
        )
    await db.delete(assessment)
    await db.commit()


# ---------------------------------------------------------------------------
# Question CRUD
# ---------------------------------------------------------------------------

async def add_question(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    assessment_id: UUID,
    payload: QuestionCreate,
) -> AssessmentQuestion:
    assessment = await _get_assessment_or_404(db, tenant_id, assessment_id)
    if not _is_teacher(role):
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)

    question = AssessmentQuestion(
        assessment_id=assessment.id,
        question_text=payload.question_text,
        question_type=payload.question_type,
        options=payload.options,
        correct_answer=payload.correct_answer,
        marks=payload.marks,
        difficulty=payload.difficulty,
        order_index=payload.order_index,
    )
    db.add(question)
    await db.flush()  # get the new question into session

    # Update counters on assessment
    await _refresh_counters(db, assessment)
    assessment.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(question)
    return question


async def add_questions_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    assessment_id: UUID,
    questions_data: List[QuestionCreate],
) -> List[AssessmentQuestion]:
    assessment = await _get_assessment_or_404(db, tenant_id, assessment_id)
    if not _is_teacher(role):
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)

    created: List[AssessmentQuestion] = []
    for payload in questions_data:
        question = AssessmentQuestion(
            assessment_id=assessment.id,
            question_text=payload.question_text,
            question_type=payload.question_type,
            options=payload.options,
            correct_answer=payload.correct_answer,
            marks=payload.marks,
            difficulty=payload.difficulty,
            order_index=payload.order_index,
        )
        db.add(question)
        created.append(question)

    await db.flush()
    await _refresh_counters(db, assessment)
    assessment.updated_at = datetime.utcnow()
    await db.commit()

    for q in created:
        await db.refresh(q)
    return created


async def update_question(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    question_id: UUID,
    payload: QuestionUpdate,
) -> AssessmentQuestion:
    if not _is_teacher(role):
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)

    result = await db.execute(
        select(AssessmentQuestion)
        .join(OnlineAssessment, OnlineAssessment.id == AssessmentQuestion.assessment_id)
        .where(
            AssessmentQuestion.id == question_id,
            OnlineAssessment.tenant_id == tenant_id,
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise ServiceError("Question not found", status.HTTP_404_NOT_FOUND)

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(question, field, value)

    # Refresh counters
    assessment = await db.get(OnlineAssessment, question.assessment_id)
    await db.flush()
    await _refresh_counters(db, assessment)
    assessment.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(question)
    return question


async def delete_question(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    question_id: UUID,
) -> None:
    if not _is_teacher(role):
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)

    result = await db.execute(
        select(AssessmentQuestion)
        .join(OnlineAssessment, OnlineAssessment.id == AssessmentQuestion.assessment_id)
        .where(
            AssessmentQuestion.id == question_id,
            OnlineAssessment.tenant_id == tenant_id,
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise ServiceError("Question not found", status.HTTP_404_NOT_FOUND)

    assessment = await db.get(OnlineAssessment, question.assessment_id)
    await db.delete(question)
    await db.flush()
    await _refresh_counters(db, assessment)
    assessment.updated_at = datetime.utcnow()
    await db.commit()


async def list_questions(
    db: AsyncSession,
    tenant_id: UUID,
    assessment_id: UUID,
    include_correct: bool = True,
) -> List[AssessmentQuestion]:
    # Validate tenant owns assessment
    await _get_assessment_or_404(db, tenant_id, assessment_id)

    result = await db.execute(
        select(AssessmentQuestion)
        .where(AssessmentQuestion.assessment_id == assessment_id)
        .order_by(AssessmentQuestion.order_index)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# List assessments (student / teacher view)
# ---------------------------------------------------------------------------

async def list_assessments(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    academic_year_id: UUID,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    class_id: Optional[UUID] = None,
    subject_id: Optional[UUID] = None,
) -> List[AssessmentListItem]:

    query = (
        select(OnlineAssessment)
        .where(
            OnlineAssessment.tenant_id == tenant_id,
            OnlineAssessment.academic_year_id == academic_year_id,
        )
    )

    # Students only see assessments for their enrolled class/section
    if role.upper() == STUDENT_ROLE:
        sar_result = await db.execute(
            select(StudentAcademicRecord).where(
                StudentAcademicRecord.student_id == user_id,
                StudentAcademicRecord.academic_year_id == academic_year_id,
                StudentAcademicRecord.status == "ACTIVE",
            )
        )
        sar = sar_result.scalar_one_or_none()
        if not sar:
            return []
        # Filter: assessment class matches; section either matches or is "all-class" (null)
        query = query.where(
            OnlineAssessment.class_id == sar.class_id,
            (OnlineAssessment.section_id == sar.section_id)
            | (OnlineAssessment.section_id.is_(None)),
        )
        # Students don't see DRAFT
        query = query.where(OnlineAssessment.status != "DRAFT")

    if status_filter:
        query = query.where(OnlineAssessment.status == status_filter.upper())

    if search:
        query = query.where(OnlineAssessment.title.ilike(f"%{search}%"))

    if class_id:
        query = query.where(OnlineAssessment.class_id == class_id)

    if subject_id:
        query = query.where(OnlineAssessment.subject_id == subject_id)

    result = await db.execute(query.order_by(OnlineAssessment.created_at.desc()))
    assessments = list(result.scalars().all())

    # Build list items
    items: List[AssessmentListItem] = []
    for a in assessments:
        # Resolve subject name
        subject_name: Optional[str] = None
        if a.subject_id:
            subj = await db.get(SchoolSubject, a.subject_id)
            subject_name = subj.name if subj else None

        # Resolve class label
        sc = await db.get(SchoolClass, a.class_id)
        class_label = sc.name if sc else str(a.class_id)
        if a.section_id:
            sec = await db.get(Section, a.section_id)
            if sec:
                class_label = f"{class_label} – Section {sec.name}"

        # Count this user's attempts
        att_result = await db.execute(
            select(func.count(AssessmentAttempt.id)).where(
                AssessmentAttempt.assessment_id == a.id,
                AssessmentAttempt.student_id == user_id,
                AssessmentAttempt.status.in_(["SUBMITTED", "TIMED_OUT"]),
            )
        )
        attempts_taken = att_result.scalar() or 0

        # Best score from submitted attempts
        score: Optional[int] = None
        if attempts_taken > 0:
            score_result = await db.execute(
                select(func.max(AssessmentAttempt.score)).where(
                    AssessmentAttempt.assessment_id == a.id,
                    AssessmentAttempt.student_id == user_id,
                    AssessmentAttempt.status.in_(["SUBMITTED", "TIMED_OUT"]),
                )
            )
            score = score_result.scalar()

        items.append(
            AssessmentListItem(
                id=a.id,
                title=a.title,
                subject=subject_name,
                class_label=class_label,
                total_questions=a.total_questions,
                total_marks=a.total_marks,
                duration_minutes=a.duration_minutes,
                status=a.status,
                due_date=a.due_date,
                attempts_allowed=a.attempts_allowed,
                attempts_taken=attempts_taken,
                description=a.description,
                score=score,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Start attempt
# ---------------------------------------------------------------------------

async def start_attempt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    assessment_id: UUID,
) -> StartAttemptResponse:
    assessment = await _get_assessment_or_404(db, tenant_id, assessment_id)

    if assessment.status != "ACTIVE":
        raise ServiceError(
            "Assessment is not currently active", status.HTTP_400_BAD_REQUEST
        )

    # Count existing finished attempts by this student
    finished_result = await db.execute(
        select(func.count(AssessmentAttempt.id)).where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.student_id == user_id,
            AssessmentAttempt.status.in_(["SUBMITTED", "TIMED_OUT"]),
        )
    )
    finished_count = finished_result.scalar() or 0
    if finished_count >= assessment.attempts_allowed:
        raise ServiceError(
            "Maximum attempts reached for this assessment",
            status.HTTP_400_BAD_REQUEST,
        )

    # Check for already in-progress attempt
    in_progress_result = await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.student_id == user_id,
            AssessmentAttempt.status == "IN_PROGRESS",
        )
    )
    existing_attempt = in_progress_result.scalar_one_or_none()
    if existing_attempt:
        raise ServiceError(
            "You already have an attempt in progress for this assessment",
            status.HTTP_400_BAD_REQUEST,
        )

    attempt = AssessmentAttempt(
        assessment_id=assessment_id,
        student_id=user_id,
        attempt_number=finished_count + 1,
        status="IN_PROGRESS",
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    # Load questions (without correct_answer in student response)
    questions = await list_questions(db, tenant_id, assessment_id, include_correct=False)

    from .schemas import QuestionResponse

    question_responses = [
        QuestionResponse(
            id=q.id,
            assessment_id=q.assessment_id,
            question_text=q.question_text,
            question_type=q.question_type,
            options=q.options,
            correct_answer=None,  # Never send to student during attempt
            marks=q.marks,
            difficulty=q.difficulty,
            order_index=q.order_index,
            created_at=q.created_at,
        )
        for q in questions
    ]

    return StartAttemptResponse(attempt_id=attempt.id, questions=question_responses)


# ---------------------------------------------------------------------------
# Submit answers
# ---------------------------------------------------------------------------

def _grade_answer(question: AssessmentQuestion, selected: Any) -> tuple[bool, int]:
    """
    Returns (is_correct, marks_awarded).

    Grading rules per question type:
      MCQ          : exact string match against correct_answer
      MULTI_SELECT : set equality between selected list and correct_answer list
      FILL_IN_BLANK: case-insensitive string match
      SHORT_ANSWER : case-insensitive string match (simple auto-grading)
      LONG_ANSWER  : always None / 0 (manual grading required)
    """
    qt = question.question_type
    correct = question.correct_answer

    if selected is None:
        return False, 0

    if qt == "MCQ":
        is_correct = str(selected).strip() == str(correct).strip()
    elif qt == "MULTI_SELECT":
        selected_set = set(str(s).strip() for s in (selected if isinstance(selected, list) else [selected]))
        correct_set = set(str(c).strip() for c in (correct if isinstance(correct, list) else [correct]))
        is_correct = selected_set == correct_set
    elif qt in ("FILL_IN_BLANK", "SHORT_ANSWER"):
        is_correct = str(selected).strip().lower() == str(correct).strip().lower()
    else:
        # LONG_ANSWER – manual grading; mark as None
        return None, 0  # type: ignore[return-value]

    return is_correct, question.marks if is_correct else 0


async def submit_answers(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    assessment_id: UUID,
    payload: SubmitAnswersRequest,
) -> SubmitAnswersResponse:
    assessment = await _get_assessment_or_404(db, tenant_id, assessment_id)

    # Load the attempt
    att_result = await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.id == payload.attempt_id,
            AssessmentAttempt.student_id == user_id,
            AssessmentAttempt.assessment_id == assessment_id,
        )
    )
    attempt = att_result.scalar_one_or_none()
    if not attempt:
        raise ServiceError("Attempt not found", status.HTTP_404_NOT_FOUND)
    if attempt.status != "IN_PROGRESS":
        raise ServiceError(
            "Attempt is already submitted or aborted", status.HTTP_400_BAD_REQUEST
        )

    # Load all questions
    questions = await list_questions(db, tenant_id, assessment_id)
    question_map = {str(q.id): q for q in questions}

    score = 0
    correct_count = 0
    wrong_count = 0
    skipped_count = 0

    for question in questions:
        qid_str = str(question.id)
        selected = payload.answers.get(qid_str)

        if selected is None:
            skipped_count += 1
            answer_row = AssessmentAttemptAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_answer=None,
                is_correct=None,
                marks_awarded=0,
            )
        else:
            is_correct, marks_awarded = _grade_answer(question, selected)
            if is_correct is None:
                # LONG_ANSWER – treat as pending
                pass
            elif is_correct:
                correct_count += 1
                score += marks_awarded
            else:
                wrong_count += 1

            answer_row = AssessmentAttemptAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_answer=selected,
                is_correct=is_correct,
                marks_awarded=marks_awarded,
            )

        db.add(answer_row)

    # Update attempt
    attempt.status = "SUBMITTED"
    attempt.score = score
    attempt.total_marks = assessment.total_marks
    attempt.correct_count = correct_count
    attempt.wrong_count = wrong_count
    attempt.skipped_count = skipped_count
    attempt.time_taken_seconds = payload.time_taken_seconds
    attempt.submitted_at = datetime.utcnow()

    await db.commit()

    return SubmitAnswersResponse(
        attempt_id=attempt.id,
        score=score,
        total_marks=assessment.total_marks,
        correct=correct_count,
        wrong=wrong_count,
        skipped=skipped_count,
        time_taken_seconds=payload.time_taken_seconds,
    )


# ---------------------------------------------------------------------------
# Attempt detail / review
# ---------------------------------------------------------------------------

async def get_attempt_detail(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    attempt_id: UUID,
) -> AttemptDetailResponse:
    att_result = await db.execute(
        select(AssessmentAttempt)
        .options(selectinload(AssessmentAttempt.answers))
        .join(OnlineAssessment, OnlineAssessment.id == AssessmentAttempt.assessment_id)
        .where(
            AssessmentAttempt.id == attempt_id,
            OnlineAssessment.tenant_id == tenant_id,
        )
    )
    attempt = att_result.scalar_one_or_none()
    if not attempt:
        raise ServiceError("Attempt not found", status.HTTP_404_NOT_FOUND)

    # Students can only view their own attempts
    if role.upper() == STUDENT_ROLE and attempt.student_id != user_id:
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)

    # Load questions
    questions = await list_questions(db, tenant_id, attempt.assessment_id)
    question_map = {q.id: q for q in questions}
    answer_map = {a.question_id: a for a in attempt.answers}

    answer_details: List[AttemptAnswerDetail] = []
    for q in questions:
        ans = answer_map.get(q.id)
        answer_details.append(
            AttemptAnswerDetail(
                question_id=q.id,
                question_text=q.question_text,
                question_type=q.question_type,
                options=q.options,
                correct_answer=q.correct_answer,
                selected_answer=ans.selected_answer if ans else None,
                is_correct=ans.is_correct if ans else None,
                marks_awarded=ans.marks_awarded if ans else None,
                marks=q.marks,
            )
        )

    return AttemptDetailResponse(
        attempt_id=attempt.id,
        assessment_id=attempt.assessment_id,
        student_id=attempt.student_id,
        attempt_number=attempt.attempt_number,
        status=attempt.status,
        score=attempt.score,
        total_marks=attempt.total_marks,
        correct_count=attempt.correct_count,
        wrong_count=attempt.wrong_count,
        skipped_count=attempt.skipped_count,
        time_taken_seconds=attempt.time_taken_seconds,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        answers=answer_details,
    )


# ---------------------------------------------------------------------------
# Abort attempt
# ---------------------------------------------------------------------------

async def abort_attempt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    attempt_id: UUID,
    reason: Optional[str] = None,
) -> None:
    att_result = await db.execute(
        select(AssessmentAttempt)
        .join(OnlineAssessment, OnlineAssessment.id == AssessmentAttempt.assessment_id)
        .where(
            AssessmentAttempt.id == attempt_id,
            AssessmentAttempt.student_id == user_id,
            OnlineAssessment.tenant_id == tenant_id,
        )
    )
    attempt = att_result.scalar_one_or_none()
    if not attempt:
        raise ServiceError("Attempt not found", status.HTTP_404_NOT_FOUND)
    if attempt.status != "IN_PROGRESS":
        raise ServiceError(
            "Only in-progress attempts can be aborted", status.HTTP_400_BAD_REQUEST
        )
    attempt.status = "ABORTED"
    await db.commit()


# ---------------------------------------------------------------------------
# Teacher: results overview
# ---------------------------------------------------------------------------

async def get_assessment_results(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    role: str,
    assessment_id: UUID,
) -> AssessmentResultsResponse:
    if not _is_teacher(role):
        raise ServiceError("Forbidden", status.HTTP_403_FORBIDDEN)

    assessment = await _get_assessment_or_404(db, tenant_id, assessment_id)

    att_result = await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.assessment_id == assessment_id,
            AssessmentAttempt.status.in_(["SUBMITTED", "TIMED_OUT"]),
        )
    )
    attempts = list(att_result.scalars().all())

    results: List[StudentResultItem] = []
    for att in attempts:
        user = await db.get(User, att.student_id)
        results.append(
            StudentResultItem(
                student_id=att.student_id,
                student_name=user.full_name if user else str(att.student_id),
                attempt_number=att.attempt_number,
                attempt_id=att.id,
                status=att.status,
                score=att.score,
                total_marks=att.total_marks,
                correct_count=att.correct_count,
                wrong_count=att.wrong_count,
                skipped_count=att.skipped_count,
                time_taken_seconds=att.time_taken_seconds,
                submitted_at=att.submitted_at,
            )
        )

    return AssessmentResultsResponse(
        assessment_id=assessment.id,
        title=assessment.title,
        total_marks=assessment.total_marks,
        results=results,
    )
