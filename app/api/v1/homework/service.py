"""Homework service with permission checks and business logic."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import ServiceError
from app.core.models import (
    AcademicYear,
    Homework,
    HomeworkAssignment,
    HomeworkAttempt,
    HomeworkHintUsage,
    HomeworkQuestion,
    HomeworkSubmission,
    StudentAcademicRecord,
)

from .schemas import (
    HomeworkAssignmentCreate,
    HomeworkCreate,
    HomeworkQuestionCreate,
    HomeworkQuestionUpdate,
    HomeworkQuestionsBulkCreate,
    HomeworkSubmissionCreate,
    HomeworkUpdate,
)


def _is_admin(role: str) -> bool:
    return role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN")


def _is_teacher(role: str) -> bool:
    return role == "TEACHER"


def _is_student(role: str) -> bool:
    return role == "STUDENT"


async def _get_homework_or_404(db: AsyncSession, homework_id: UUID, tenant_id: UUID) -> Homework:
    hw = await db.get(Homework, homework_id)
    if not hw:
        raise ServiceError("Homework not found", status.HTTP_404_NOT_FOUND)
    teacher = await db.get(User, hw.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id:
        raise ServiceError("Homework not found", status.HTTP_404_NOT_FOUND)
    return hw


async def _get_assignment_or_404(db: AsyncSession, assignment_id: UUID, tenant_id: UUID) -> HomeworkAssignment:
    ha = await db.get(HomeworkAssignment, assignment_id)
    if not ha:
        raise ServiceError("Assignment not found", status.HTTP_404_NOT_FOUND)
    hw = await db.get(Homework, ha.homework_id)
    teacher = await db.get(User, hw.teacher_id) if hw else None
    if not teacher or teacher.tenant_id != tenant_id:
        raise ServiceError("Assignment not found", status.HTTP_404_NOT_FOUND)
    return ha


def _validate_time_mode(time_mode: str, total_time: Optional[int], per_question: Optional[int]) -> None:
    if time_mode == "TOTAL_TIME" and (total_time is None or total_time < 1):
        raise ServiceError("total_time_minutes required when time_mode is TOTAL_TIME", status.HTTP_400_BAD_REQUEST)
    if time_mode == "PER_QUESTION" and (per_question is None or per_question < 1):
        raise ServiceError("per_question_time_seconds required when time_mode is PER_QUESTION", status.HTTP_400_BAD_REQUEST)


# ----- Homework CRUD -----
async def create_homework(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    payload: HomeworkCreate,
) -> Homework:
    if not _is_admin(user_role) and not _is_teacher(user_role):
        raise ServiceError("Only teachers or admins can create homework", status.HTTP_403_FORBIDDEN)
    user = await db.get(User, user_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("User not found", status.HTTP_404_NOT_FOUND)
    teacher_id = user_id
    if _is_admin(user_role) and getattr(payload, "teacher_id", None):
        t = await db.get(User, payload.teacher_id)
        if t and t.tenant_id == tenant_id and t.user_type == "employee":
            teacher_id = payload.teacher_id
    if _is_teacher(user_role) and teacher_id != user_id:
        raise ServiceError("Teachers can only create homework for themselves", status.HTTP_403_FORBIDDEN)
    if payload.status not in ("DRAFT", "PUBLISHED", "ARCHIVED"):
        raise ServiceError("Invalid status", status.HTTP_400_BAD_REQUEST)
    if payload.time_mode not in ("NO_TIME", "TOTAL_TIME", "PER_QUESTION"):
        raise ServiceError("Invalid time_mode", status.HTTP_400_BAD_REQUEST)
    _validate_time_mode(payload.time_mode, payload.total_time_minutes, payload.per_question_time_seconds)
    hw = Homework(
        teacher_id=teacher_id,
        title=payload.title,
        description=payload.description,
        status=payload.status or "DRAFT",
        time_mode=payload.time_mode,
        total_time_minutes=payload.total_time_minutes,
        per_question_time_seconds=payload.per_question_time_seconds,
    )
    db.add(hw)
    await db.commit()
    await db.refresh(hw)
    return hw


async def list_homeworks(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    status_filter: Optional[str] = None,
) -> List[Homework]:
    stmt = select(Homework).join(User, Homework.teacher_id == User.id).where(User.tenant_id == tenant_id)
    if _is_teacher(user_role) and not _is_admin(user_role):
        stmt = stmt.where(Homework.teacher_id == user_id)
    if status_filter:
        stmt = stmt.where(Homework.status == status_filter)
    stmt = stmt.order_by(Homework.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_homework(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    homework_id: UUID,
) -> Homework:
    hw = await _get_homework_or_404(db, homework_id, tenant_id)
    if _is_teacher(user_role) and not _is_admin(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to view this homework", status.HTTP_403_FORBIDDEN)
    return hw


async def update_homework(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    homework_id: UUID,
    payload: HomeworkUpdate,
) -> Homework:
    hw = await _get_homework_or_404(db, homework_id, tenant_id)
    if _is_teacher(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to update this homework", status.HTTP_403_FORBIDDEN)
    if hw.status != "DRAFT":
        raise ServiceError("Homework can be edited only when status is DRAFT", status.HTTP_400_BAD_REQUEST)
    if payload.title is not None:
        hw.title = payload.title
    if payload.description is not None:
        hw.description = payload.description
    if payload.status is not None:
        if payload.status not in ("DRAFT", "PUBLISHED", "ARCHIVED"):
            raise ServiceError("Invalid status", status.HTTP_400_BAD_REQUEST)
        hw.status = payload.status
    if payload.time_mode is not None:
        if payload.time_mode not in ("NO_TIME", "TOTAL_TIME", "PER_QUESTION"):
            raise ServiceError("Invalid time_mode", status.HTTP_400_BAD_REQUEST)
        hw.time_mode = payload.time_mode
    if payload.total_time_minutes is not None:
        hw.total_time_minutes = payload.total_time_minutes
    if payload.per_question_time_seconds is not None:
        hw.per_question_time_seconds = payload.per_question_time_seconds
    _validate_time_mode(hw.time_mode, hw.total_time_minutes, hw.per_question_time_seconds)
    await db.commit()
    await db.refresh(hw)
    return hw


# ----- Questions CRUD -----
async def list_questions(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    homework_id: UUID,
) -> List[HomeworkQuestion]:
    hw = await _get_homework_or_404(db, homework_id, tenant_id)
    if _is_teacher(user_role) and not _is_admin(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to view questions", status.HTTP_403_FORBIDDEN)
    result = await db.execute(
        select(HomeworkQuestion).where(HomeworkQuestion.homework_id == homework_id).order_by(HomeworkQuestion.display_order, HomeworkQuestion.created_at)
    )
    return list(result.scalars().all())


async def add_question(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    homework_id: UUID,
    payload: HomeworkQuestionCreate,
) -> HomeworkQuestion:
    hw = await _get_homework_or_404(db, homework_id, tenant_id)
    if _is_teacher(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to add questions to this homework", status.HTTP_403_FORBIDDEN)
    if hw.status != "DRAFT":
        raise ServiceError("Questions can be added only when homework is DRAFT", status.HTTP_400_BAD_REQUEST)
    if payload.question_type not in ("MCQ", "FILL_IN_BLANK", "SHORT_ANSWER", "LONG_ANSWER", "MULTI_CHECK"):
        raise ServiceError("Invalid question_type", status.HTTP_400_BAD_REQUEST)
    if payload.question_type in ("MCQ", "MULTI_CHECK") and not payload.options:
        raise ServiceError(f"{payload.question_type} requires options", status.HTTP_400_BAD_REQUEST)
    q = HomeworkQuestion(
        homework_id=homework_id,
        question_text=payload.question_text,
        question_type=payload.question_type,
        options=payload.options,
        correct_answer=payload.correct_answer,
        hints=payload.hints or [],
        display_order=payload.display_order,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


async def add_questions_bulk(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    homework_id: UUID,
    payload: HomeworkQuestionsBulkCreate,
) -> List[HomeworkQuestion]:
    hw = await _get_homework_or_404(db, homework_id, tenant_id)
    if _is_teacher(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to add questions to this homework", status.HTTP_403_FORBIDDEN)
    if hw.status != "DRAFT":
        raise ServiceError("Questions can be added only when homework is DRAFT", status.HTTP_400_BAD_REQUEST)
    created: List[HomeworkQuestion] = []
    for i, item in enumerate(payload.questions):
        if item.question_type not in ("MCQ", "FILL_IN_BLANK", "SHORT_ANSWER", "LONG_ANSWER", "MULTI_CHECK"):
            raise ServiceError(f"Invalid question_type at index {i}", status.HTTP_400_BAD_REQUEST)
        if item.question_type in ("MCQ", "MULTI_CHECK") and not item.options:
            raise ServiceError(f"{item.question_type} requires options at index {i}", status.HTTP_400_BAD_REQUEST)
        display_order = item.display_order if item.display_order is not None else i
        q = HomeworkQuestion(
            homework_id=homework_id,
            question_text=item.question_text,
            question_type=item.question_type,
            options=item.options,
            correct_answer=item.correct_answer,
            hints=item.hints or [],
            display_order=display_order,
        )
        db.add(q)
        created.append(q)
    await db.commit()
    for q in created:
        await db.refresh(q)
    return created


async def update_question(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    question_id: UUID,
    payload: HomeworkQuestionUpdate,
) -> HomeworkQuestion:
    q = await db.get(HomeworkQuestion, question_id)
    if not q:
        raise ServiceError("Question not found", status.HTTP_404_NOT_FOUND)
    hw = await db.get(Homework, q.homework_id)
    if not hw:
        raise ServiceError("Homework not found", status.HTTP_404_NOT_FOUND)
    teacher = await db.get(User, hw.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id:
        raise ServiceError("Question not found", status.HTTP_404_NOT_FOUND)
    if _is_teacher(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to update this question", status.HTTP_403_FORBIDDEN)
    has_assignments = (await db.execute(select(HomeworkAssignment).where(HomeworkAssignment.homework_id == hw.id))).scalar_one_or_none()
    if has_assignments:
        raise ServiceError("Homework has been assigned; questions are locked", status.HTTP_400_BAD_REQUEST)
    if payload.question_text is not None:
        q.question_text = payload.question_text
    if payload.question_type is not None:
        if payload.question_type not in ("MCQ", "FILL_IN_BLANK", "SHORT_ANSWER", "LONG_ANSWER", "MULTI_CHECK"):
            raise ServiceError("Invalid question_type", status.HTTP_400_BAD_REQUEST)
        q.question_type = payload.question_type
    if payload.options is not None:
        q.options = payload.options
    if payload.correct_answer is not None:
        q.correct_answer = payload.correct_answer
    if payload.hints is not None:
        q.hints = payload.hints
    if payload.display_order is not None:
        q.display_order = payload.display_order
    await db.commit()
    await db.refresh(q)
    return q


async def delete_question(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    question_id: UUID,
) -> bool:
    q = await db.get(HomeworkQuestion, question_id)
    if not q:
        raise ServiceError("Question not found", status.HTTP_404_NOT_FOUND)
    hw = await db.get(Homework, q.homework_id)
    if not hw:
        raise ServiceError("Homework not found", status.HTTP_404_NOT_FOUND)
    teacher = await db.get(User, hw.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id:
        raise ServiceError("Question not found", status.HTTP_404_NOT_FOUND)
    if _is_teacher(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to delete this question", status.HTTP_403_FORBIDDEN)
    has_assignments = (await db.execute(select(HomeworkAssignment).where(HomeworkAssignment.homework_id == hw.id))).scalar_one_or_none()
    if has_assignments:
        raise ServiceError("Homework has been assigned; questions cannot be deleted", status.HTTP_400_BAD_REQUEST)
    await db.delete(q)
    await db.commit()
    return True


# ----- Assignment -----
async def create_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    payload: HomeworkAssignmentCreate,
) -> HomeworkAssignment:
    if not _is_admin(user_role) and not _is_teacher(user_role):
        raise ServiceError("Only teachers or admins can assign homework", status.HTTP_403_FORBIDDEN)
    hw = await _get_homework_or_404(db, payload.homework_id, tenant_id)
    if _is_teacher(user_role) and hw.teacher_id != user_id:
        raise ServiceError("Not allowed to assign this homework", status.HTTP_403_FORBIDDEN)
    if hw.status != "PUBLISHED":
        raise ServiceError("Only PUBLISHED homework can be assigned", status.HTTP_400_BAD_REQUEST)
    now = datetime.now(timezone.utc)
    if payload.due_date <= now:
        raise ServiceError("Due date must be in the future", status.HTTP_400_BAD_REQUEST)
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)
    if ay.status != "ACTIVE":
        raise ServiceError("Academic year must be ACTIVE to assign homework", status.HTTP_400_BAD_REQUEST)
    from app.api.v1.classes import service as class_service
    from app.api.v1.sections import service as section_service
    if not await class_service.get_class_by_id_for_tenant(db, tenant_id, payload.class_id, active_only=True):
        raise ServiceError("Class not found", status.HTTP_404_NOT_FOUND)
    if payload.section_id:
        sec = await section_service.get_section_by_id_for_tenant(db, tenant_id, payload.section_id, active_only=True)
        if not sec or sec.class_id != payload.class_id:
            raise ServiceError("Section not found or does not belong to class", status.HTTP_400_BAD_REQUEST)
    ha = HomeworkAssignment(
        homework_id=payload.homework_id,
        academic_year_id=payload.academic_year_id,
        class_id=payload.class_id,
        section_id=payload.section_id,
        due_date=payload.due_date,
        assigned_by=user_id,
    )
    db.add(ha)
    await db.commit()
    await db.refresh(ha)
    # TODO: Notify students of the class/section when notification service is available
    return ha


async def get_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    assignment_id: UUID,
) -> HomeworkAssignment:
    ha = await _get_assignment_or_404(db, assignment_id, tenant_id)
    if _is_student(user_role):
        sar = (
            await db.execute(
                select(StudentAcademicRecord)
                .where(
                    StudentAcademicRecord.student_id == user_id,
                    StudentAcademicRecord.status == "ACTIVE",
                    StudentAcademicRecord.academic_year_id == ha.academic_year_id,
                    StudentAcademicRecord.class_id == ha.class_id,
                )
            )
        ).scalar_one_or_none()
        if not sar:
            raise ServiceError("Assignment not found", status.HTTP_404_NOT_FOUND)
        if ha.section_id is not None and sar.section_id != ha.section_id:
            raise ServiceError("Assignment not found", status.HTTP_404_NOT_FOUND)
    return ha


async def list_assignments(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    homework_id: Optional[UUID] = None,
) -> List[HomeworkAssignment]:
    stmt = (
        select(HomeworkAssignment)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .join(User, Homework.teacher_id == User.id)
        .where(User.tenant_id == tenant_id)
    )
    if homework_id:
        stmt = stmt.where(HomeworkAssignment.homework_id == homework_id)
    if _is_teacher(user_role) and not _is_admin(user_role):
        stmt = stmt.where(Homework.teacher_id == user_id)
    stmt = stmt.order_by(HomeworkAssignment.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


# ----- Student: list assigned homework -----
async def list_assigned_for_student(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
) -> List[HomeworkAssignment]:
    sar = (
        await db.execute(
            select(StudentAcademicRecord)
            .where(
                StudentAcademicRecord.student_id == student_id,
                StudentAcademicRecord.status == "ACTIVE",
            )
            .order_by(StudentAcademicRecord.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not sar:
        return []
    stmt = (
        select(HomeworkAssignment)
        .join(Homework, HomeworkAssignment.homework_id == Homework.id)
        .join(User, Homework.teacher_id == User.id)
        .where(
            User.tenant_id == tenant_id,
            HomeworkAssignment.academic_year_id == sar.academic_year_id,
            HomeworkAssignment.class_id == sar.class_id,
            HomeworkAssignment.due_date > datetime.now(timezone.utc),
        )
    )
    stmt = stmt.where(
        (HomeworkAssignment.section_id.is_(None)) | (HomeworkAssignment.section_id == sar.section_id)
    )
    stmt = stmt.order_by(HomeworkAssignment.due_date.asc())
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


# ----- Attempt -----
async def start_attempt(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    assignment_id: UUID,
    payload: Optional[Dict[str, Any]] = None,
) -> HomeworkAttempt:
    ha = await _get_assignment_or_404(db, assignment_id, tenant_id)
    now = datetime.now(timezone.utc)
    if ha.due_date <= now:
        raise ServiceError("Cannot start homework after due date", status.HTTP_400_BAD_REQUEST)
    existing = (
        await db.execute(
            select(HomeworkAttempt)
            .where(
                HomeworkAttempt.homework_assignment_id == assignment_id,
                HomeworkAttempt.student_id == student_id,
            )
            .order_by(HomeworkAttempt.attempt_number.desc())
        )
    ).scalars().first()
    attempt_number = 1
    restart_reason = None
    if existing:
        if existing.completed_at is None:
            raise ServiceError("You have an active attempt. Complete or restart it first.", status.HTTP_400_BAD_REQUEST)
        attempt_number = existing.attempt_number + 1
        restart_reason = (payload or {}).get("restart_reason") if payload else None
        if not restart_reason or not restart_reason.strip():
            raise ServiceError("restart_reason is required when restarting an attempt", status.HTTP_400_BAD_REQUEST)
    att = HomeworkAttempt(
        homework_assignment_id=assignment_id,
        student_id=student_id,
        attempt_number=attempt_number,
        restart_reason=restart_reason,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return att


# ----- Submission -----
async def submit_homework(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    attempt_id: UUID,
    payload: HomeworkSubmissionCreate,
) -> HomeworkSubmission:
    att = await db.get(HomeworkAttempt, attempt_id)
    if not att or att.student_id != student_id:
        raise ServiceError("Attempt not found", status.HTTP_404_NOT_FOUND)
    ha = await db.get(HomeworkAssignment, att.homework_assignment_id)
    hw = await db.get(Homework, ha.homework_id)
    teacher = await db.get(User, hw.teacher_id)
    if not teacher or teacher.tenant_id != tenant_id:
        raise ServiceError("Attempt not found", status.HTTP_404_NOT_FOUND)
    now = datetime.now(timezone.utc)
    if ha.due_date <= now:
        raise ServiceError("Cannot submit after due date", status.HTTP_400_BAD_REQUEST)
    if att.completed_at:
        raise ServiceError("Attempt already submitted", status.HTTP_400_BAD_REQUEST)
    existing = (await db.execute(select(HomeworkSubmission).where(HomeworkSubmission.attempt_id == attempt_id))).scalar_one_or_none()
    if existing:
        raise ServiceError("Submission already exists for this attempt", status.HTTP_409_CONFLICT)
    sub = HomeworkSubmission(
        homework_assignment_id=att.homework_assignment_id,
        student_id=student_id,
        attempt_id=attempt_id,
        answers=payload.answers or {},
    )
    db.add(sub)
    att.completed_at = now
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Duplicate submission", status.HTTP_409_CONFLICT)
    await db.refresh(sub)
    return sub


# ----- Hint Usage -----
async def record_hint_view(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    attempt_id: UUID,
    question_id: UUID,
    hint_index: int,
) -> None:
    att = await db.get(HomeworkAttempt, attempt_id)
    if not att or att.student_id != student_id:
        raise ServiceError("Attempt not found", status.HTTP_404_NOT_FOUND)
    q = await db.get(HomeworkQuestion, question_id)
    if not q or q.homework_id != (await db.get(HomeworkAssignment, att.homework_assignment_id)).homework_id:
        raise ServiceError("Question not found", status.HTTP_404_NOT_FOUND)
    if hint_index < 0 or hint_index >= len(q.hints or []):
        raise ServiceError("Invalid hint index", status.HTTP_400_BAD_REQUEST)
    hu = HomeworkHintUsage(
        homework_question_id=question_id,
        homework_attempt_id=attempt_id,
        student_id=student_id,
        hint_index=hint_index,
    )
    db.add(hu)
    await db.commit()


async def get_hint_usage_for_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    assignment_id: UUID,
) -> List[Dict[str, Any]]:
    ha = await _get_assignment_or_404(db, assignment_id, tenant_id)
    hw = await db.get(Homework, ha.homework_id)
    if _is_teacher(user_role) and hw.teacher_id != user_id and not _is_admin(user_role):
        raise ServiceError("Not allowed to view hint usage for this assignment", status.HTTP_403_FORBIDDEN)
    stmt = (
        select(HomeworkHintUsage)
        .where(HomeworkHintUsage.homework_attempt_id.in_(
            select(HomeworkAttempt.id).where(HomeworkAttempt.homework_assignment_id == assignment_id)
        ))
    )
    result = await db.execute(stmt)
    usages = result.scalars().all()
    by_question: Dict[str, List[Dict]] = {}
    for u in usages:
        key = f"{u.homework_question_id}:{u.hint_index}"
        if key not in by_question:
            by_question[key] = {"question_id": str(u.homework_question_id), "hint_index": u.hint_index, "view_count": 0, "student_ids": []}
        by_question[key]["view_count"] += 1
        if u.student_id not in by_question[key]["student_ids"]:
            by_question[key]["student_ids"].append(u.student_id)
    return list(by_question.values())
