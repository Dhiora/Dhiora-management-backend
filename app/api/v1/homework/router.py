"""Homework API router."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    HomeworkAssignmentCreate,
    HomeworkAssignmentResponse,
    HomeworkAttemptResponse,
    HomeworkCreate,
    HomeworkQuestionCreate,
    HomeworkQuestionResponse,
    HomeworkQuestionUpdate,
    HomeworkQuestionsBulkCreate,
    HomeworkQuestionsBulkResponse,
    HomeworkResponse,
    HomeworkSubmissionCreate,
    HomeworkSubmissionResponse,
    HomeworkUpdate,
)

router = APIRouter(prefix="/api/v1/homework", tags=["homework"])


def _hw_to_resp(hw) -> HomeworkResponse:
    return HomeworkResponse(
        id=hw.id,
        teacher_id=hw.teacher_id,
        title=hw.title,
        description=hw.description,
        status=hw.status,
        time_mode=hw.time_mode,
        total_time_minutes=hw.total_time_minutes,
        per_question_time_seconds=hw.per_question_time_seconds,
        created_at=hw.created_at,
    )


def _q_to_resp(q, include_correct: bool = False) -> HomeworkQuestionResponse:
    data = {
        "id": q.id,
        "homework_id": q.homework_id,
        "question_text": q.question_text,
        "question_type": q.question_type,
        "options": q.options,
        "correct_answer": q.correct_answer if include_correct else None,
        "hints": q.hints or [],
        "display_order": q.display_order,
        "created_at": q.created_at,
    }
    return HomeworkQuestionResponse(**data)


def _ha_to_resp(ha) -> HomeworkAssignmentResponse:
    return HomeworkAssignmentResponse(
        id=ha.id,
        homework_id=ha.homework_id,
        academic_year_id=ha.academic_year_id,
        class_id=ha.class_id,
        section_id=ha.section_id,
        due_date=ha.due_date,
        assigned_by=ha.assigned_by,
        created_at=ha.created_at,
    )


def _att_to_resp(att) -> HomeworkAttemptResponse:
    return HomeworkAttemptResponse(
        id=att.id,
        homework_assignment_id=att.homework_assignment_id,
        student_id=att.student_id,
        attempt_number=att.attempt_number,
        restart_reason=att.restart_reason,
        started_at=att.started_at,
        completed_at=att.completed_at,
        created_at=att.created_at,
    )


def _sub_to_resp(sub) -> HomeworkSubmissionResponse:
    return HomeworkSubmissionResponse(
        id=sub.id,
        homework_assignment_id=sub.homework_assignment_id,
        student_id=sub.student_id,
        attempt_id=sub.attempt_id,
        answers=sub.answers or {},
        submitted_at=sub.submitted_at,
    )


# ----- Homework -----
@router.post(
    "/",
    response_model=HomeworkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("homework", "create"))],
)
async def create_homework(
    payload: HomeworkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        hw = await service.create_homework(db, current_user.tenant_id, current_user.id, current_user.role, payload)
        return _hw_to_resp(hw)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/",
    response_model=List[HomeworkResponse],
    dependencies=[Depends(check_permission("homework", "read"))],
)
async def list_homeworks(
    status_filter: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        rows = await service.list_homeworks(db, current_user.tenant_id, current_user.id, current_user.role, status_filter)
        return [_hw_to_resp(h) for h in rows]
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/{homework_id}",
    response_model=HomeworkResponse,
    dependencies=[Depends(check_permission("homework", "read"))],
)
async def get_homework(
    homework_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        hw = await service.get_homework(db, current_user.tenant_id, current_user.id, current_user.role, homework_id)
        return _hw_to_resp(hw)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/{homework_id}",
    response_model=HomeworkResponse,
    dependencies=[Depends(check_permission("homework", "update"))],
)
async def update_homework(
    homework_id: UUID,
    payload: HomeworkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        hw = await service.update_homework(db, current_user.tenant_id, current_user.id, current_user.role, homework_id, payload)
        return _hw_to_resp(hw)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Questions -----
@router.get(
    "/{homework_id}/questions",
    response_model=List[HomeworkQuestionResponse],
    dependencies=[Depends(check_permission("homework", "read"))],
)
async def list_questions(
    homework_id: UUID,
    include_correct: bool = Query(True, description="Include correct_answer (false for student view)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        rows = await service.list_questions(db, current_user.tenant_id, current_user.id, current_user.role, homework_id)
        return [_q_to_resp(q, include_correct=include_correct) for q in rows]
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{homework_id}/questions",
    response_model=HomeworkQuestionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("homework", "create"))],
)
async def add_question(
    homework_id: UUID,
    payload: HomeworkQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        q = await service.add_question(db, current_user.tenant_id, current_user.id, current_user.role, homework_id, payload)
        return _q_to_resp(q, include_correct=True)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{homework_id}/questions/bulk",
    response_model=HomeworkQuestionsBulkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("homework", "create"))],
)
async def add_questions_bulk(
    homework_id: UUID,
    payload: HomeworkQuestionsBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        questions = await service.add_questions_bulk(
            db, current_user.tenant_id, current_user.id, current_user.role, homework_id, payload
        )
        return HomeworkQuestionsBulkResponse(
            created=[_q_to_resp(q, include_correct=True) for q in questions],
            count=len(questions),
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/questions/{question_id}",
    response_model=HomeworkQuestionResponse,
    dependencies=[Depends(check_permission("homework", "update"))],
)
async def update_question(
    question_id: UUID,
    payload: HomeworkQuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        q = await service.update_question(db, current_user.tenant_id, current_user.id, current_user.role, question_id, payload)
        return _q_to_resp(q, include_correct=True)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("homework", "delete"))],
)
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        await service.delete_question(db, current_user.tenant_id, current_user.id, current_user.role, question_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Assignments -----
@router.post(
    "/assignments",
    response_model=HomeworkAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("homework", "create")), Depends(require_writable_academic_year)],
)
async def create_assignment(
    payload: HomeworkAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        ha = await service.create_assignment(db, current_user.tenant_id, current_user.id, current_user.role, payload)
        return _ha_to_resp(ha)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/assignments/{assignment_id}",
    response_model=HomeworkAssignmentResponse,
    dependencies=[Depends(check_permission("homework", "read"))],
)
async def get_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        ha = await service.get_assignment(db, current_user.tenant_id, current_user.id, current_user.role, assignment_id)
        return _ha_to_resp(ha)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/assignments",
    response_model=List[HomeworkAssignmentResponse],
    dependencies=[Depends(check_permission("homework", "read"))],
)
async def list_assignments(
    homework_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        rows = await service.list_assignments(db, current_user.tenant_id, current_user.id, current_user.role, homework_id)
        return [_ha_to_resp(h) for h in rows]
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Student: assigned homework -----
@router.get(
    "/my-assignments",
    response_model=List[HomeworkAssignmentResponse],
    dependencies=[Depends(check_permission("homework", "read"))],
)
async def list_my_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        rows = await service.list_assigned_for_student(db, current_user.tenant_id, current_user.id)
        return [_ha_to_resp(h) for h in rows]
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Attempt -----
@router.post(
    "/assignments/{assignment_id}/start",
    response_model=HomeworkAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("homework", "create")), Depends(require_writable_academic_year)],
)
async def start_attempt(
    assignment_id: UUID,
    payload: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        att = await service.start_attempt(db, current_user.tenant_id, current_user.id, assignment_id, payload)
        return _att_to_resp(att)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Submission -----
@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=HomeworkSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("homework", "create")), Depends(require_writable_academic_year)],
)
async def submit_homework(
    attempt_id: UUID,
    payload: HomeworkSubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        sub = await service.submit_homework(db, current_user.tenant_id, current_user.id, attempt_id, payload)
        return _sub_to_resp(sub)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Hint usage -----
@router.post(
    "/attempts/{attempt_id}/hint-view",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("homework", "create"))],
)
async def record_hint_view(
    attempt_id: UUID,
    question_id: UUID = Query(...),
    hint_index: int = Query(..., ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        await service.record_hint_view(db, current_user.tenant_id, current_user.id, attempt_id, question_id, hint_index)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/assignments/{assignment_id}/hint-usage",
    dependencies=[Depends(check_permission("homework", "read"))],
)
async def get_hint_usage(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return await service.get_hint_usage_for_assignment(db, current_user.tenant_id, current_user.id, current_user.role, assignment_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
