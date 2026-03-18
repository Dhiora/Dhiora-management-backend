"""Online Assessment API router."""

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
    AssessmentCreate,
    AssessmentListItem,
    AssessmentResponse,
    AssessmentResultsResponse,
    AssessmentUpdate,
    AttemptDetailResponse,
    QuestionCreate,
    QuestionResponse,
    QuestionsBulkCreate,
    QuestionUpdate,
    StartAttemptResponse,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
)

router = APIRouter(prefix="/api/v1/assessments", tags=["online-assessments"])


# ---------------------------------------------------------------------------
# Assessment management (teacher/admin)
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(check_permission("assessments", "create")),
        Depends(require_writable_academic_year),
    ],
)
async def create_assessment(
    payload: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new assessment (teacher / admin)."""
    try:
        result = await service.create_assessment(db, current_user.tenant_id, current_user.id, payload)
        return result
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/{assessment_id}",
    response_model=AssessmentResponse,
    dependencies=[
        Depends(check_permission("assessments", "update")),
        Depends(require_writable_academic_year),
    ],
)
async def update_assessment(
    assessment_id: UUID,
    payload: AssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update an assessment (teacher / admin)."""
    try:
        result = await service.update_assessment(
            db, current_user.tenant_id, current_user.id, current_user.role, assessment_id, payload
        )
        return result
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{assessment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(check_permission("assessments", "delete")),
        Depends(require_writable_academic_year),
    ],
)
async def delete_assessment(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete an assessment (DRAFT only)."""
    try:
        await service.delete_assessment(
            db, current_user.tenant_id, current_user.id, current_user.role, assessment_id
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ---------------------------------------------------------------------------
# Question management (teacher/admin)
# ---------------------------------------------------------------------------

@router.post(
    "/{assessment_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("assessments", "create"))],
)
async def add_question(
    assessment_id: UUID,
    payload: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Add a single question to an assessment."""
    try:
        question = await service.add_question(
            db, current_user.tenant_id, current_user.id, current_user.role, assessment_id, payload
        )
        return question
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{assessment_id}/questions/bulk",
    response_model=List[QuestionResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("assessments", "create"))],
)
async def add_questions_bulk(
    assessment_id: UUID,
    payload: QuestionsBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Bulk-add questions to an assessment."""
    try:
        questions = await service.add_questions_bulk(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            assessment_id,
            payload.questions,
        )
        return questions
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/{assessment_id}/questions",
    response_model=List[QuestionResponse],
    dependencies=[Depends(check_permission("assessments", "read"))],
)
async def list_questions(
    assessment_id: UUID,
    include_correct: bool = Query(True, description="Set false to hide correct_answer (student preview)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all questions for an assessment."""
    try:
        questions = await service.list_questions(
            db, current_user.tenant_id, assessment_id, include_correct=include_correct
        )
        if not include_correct:
            for q in questions:
                q.correct_answer = None
        return questions
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/questions/{question_id}",
    response_model=QuestionResponse,
    dependencies=[Depends(check_permission("assessments", "update"))],
)
async def update_question(
    question_id: UUID,
    payload: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a single question."""
    try:
        question = await service.update_question(
            db, current_user.tenant_id, current_user.id, current_user.role, question_id, payload
        )
        return question
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("assessments", "delete"))],
)
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a question from an assessment."""
    try:
        await service.delete_question(
            db, current_user.tenant_id, current_user.id, current_user.role, question_id
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ---------------------------------------------------------------------------
# Shared: list assessments
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[AssessmentListItem],
    dependencies=[Depends(check_permission("assessments", "read"))],
)
async def list_assessments(
    status_filter: Optional[str] = Query(None, alias="status", description="ACTIVE | UPCOMING | COMPLETED | DRAFT"),
    search: Optional[str] = Query(None),
    class_id: Optional[UUID] = Query(None),
    subject_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List assessments.
    - Students: only assessments for their class/section (auto-filtered).
    - Teachers/Admin: all assessments for the current academic year.
    """
    if not current_user.academic_year_id:
        raise HTTPException(status_code=400, detail="No active academic year")
    try:
        return await service.list_assessments(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            current_user.academic_year_id,
            status_filter=status_filter,
            search=search,
            class_id=class_id,
            subject_id=subject_id,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ---------------------------------------------------------------------------
# Student: start attempt
# ---------------------------------------------------------------------------

@router.post(
    "/{assessment_id}/start",
    response_model=StartAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("assessments", "read"))],
)
async def start_attempt(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Start (or re-start) an attempt for the given assessment.
    Returns attempt_id + questions (without correct answers).
    """
    try:
        return await service.start_attempt(
            db, current_user.tenant_id, current_user.id, assessment_id
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ---------------------------------------------------------------------------
# Student: submit answers
# ---------------------------------------------------------------------------

@router.post(
    "/{assessment_id}/submit",
    response_model=SubmitAnswersResponse,
    dependencies=[Depends(check_permission("assessments", "read"))],
)
async def submit_answers(
    assessment_id: UUID,
    payload: SubmitAnswersRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Submit answers for an in-progress attempt.
    Scores the attempt immediately (auto-gradable question types).
    """
    try:
        return await service.submit_answers(
            db, current_user.tenant_id, current_user.id, assessment_id, payload
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ---------------------------------------------------------------------------
# Attempt detail / review
# ---------------------------------------------------------------------------

@router.get(
    "/attempts/{attempt_id}",
    response_model=AttemptDetailResponse,
    dependencies=[Depends(check_permission("assessments", "read"))],
)
async def get_attempt_detail(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get detailed result + answer review for a completed attempt.
    Students can only view their own; teachers/admins can view any.
    """
    try:
        return await service.get_attempt_detail(
            db, current_user.tenant_id, current_user.id, current_user.role, attempt_id
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ---------------------------------------------------------------------------
# Abort attempt
# ---------------------------------------------------------------------------

@router.post(
    "/attempts/{attempt_id}/abort",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("assessments", "read"))],
)
async def abort_attempt(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Abort an in-progress attempt (user clicked Exit)."""
    try:
        await service.abort_attempt(
            db, current_user.tenant_id, current_user.id, attempt_id
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ---------------------------------------------------------------------------
# Teacher: results overview
# ---------------------------------------------------------------------------

@router.get(
    "/{assessment_id}/results",
    response_model=AssessmentResultsResponse,
    dependencies=[Depends(check_permission("assessments", "read"))],
)
async def get_assessment_results(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all student results for an assessment (teacher/admin only)."""
    try:
        return await service.get_assessment_results(
            db, current_user.tenant_id, current_user.id, current_user.role, assessment_id
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
