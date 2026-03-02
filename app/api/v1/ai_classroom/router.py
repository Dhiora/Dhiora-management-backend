"""AI Classroom API router."""

import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.config import settings
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    DoubtAskRequest,
    DoubtAskResponse,
    DoubtChatResponse,
    DoubtMessageResponse,
    LectureCreate,
    LectureResponse,
    RecordingStartRequest,
    RecordingStartResponse,
    RecordingStatusResponse,
    TranscriptUpdateRequest,
)

router = APIRouter(prefix="/api/v1/ai-classroom", tags=["ai-classroom"])


def _lecture_to_response(lecture) -> LectureResponse:
    return LectureResponse(
        id=lecture.id,
        tenant_id=lecture.tenant_id,
        academic_year_id=lecture.academic_year_id,
        class_id=lecture.class_id,
        section_id=lecture.section_id,
        subject_id=lecture.subject_id,
        teacher_id=lecture.teacher_id,
        title=lecture.title,
        transcript=lecture.transcript,
        structured_notes=lecture.structured_notes,
        status=lecture.status,
        recording_started_at=lecture.recording_started_at,
        recording_paused_at=lecture.recording_paused_at,
        total_recording_seconds=lecture.total_recording_seconds,
        is_active_recording=lecture.is_active_recording,
        audio_buffer_size_bytes=lecture.audio_buffer_size_bytes,
        created_at=lecture.created_at,
        class_name=getattr(lecture, '_class_name', None),
        subject_name=getattr(lecture, '_subject_name', None),
        section_name=getattr(lecture, '_section_name', None),
        session_name=lecture.title,
    )


def _message_to_response(msg) -> DoubtMessageResponse:
    return DoubtMessageResponse(
        id=msg.id,
        chat_id=msg.chat_id,
        role=msg.role,
        message=msg.message,
        created_at=msg.created_at,
    )


def _chat_to_response(chat) -> DoubtChatResponse:
    return DoubtChatResponse(
        id=chat.id,
        tenant_id=chat.tenant_id,
        student_id=chat.student_id,
        lecture_id=chat.lecture_id,
        created_at=chat.created_at,
        messages=[_message_to_response(msg) for msg in chat.messages],
    )


@router.post(
    "/lectures",
    response_model=LectureResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("ai_classroom", "create_lecture"))],
)
async def create_lecture(
    academic_year_id: UUID = Query(...),
    class_id: UUID = Query(...),
    section_id: Optional[UUID] = Query(None),
    subject_id: UUID = Query(...),
    title: str = Query(..., min_length=1, max_length=255),
    audio_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        payload = LectureCreate(
            academic_year_id=academic_year_id,
            class_id=class_id,
            section_id=section_id,
            subject_id=subject_id,
            title=title,
        )
        lecture = await service.create_lecture(
            db,
            current_user.tenant_id,
            current_user.id,
            payload,
            audio_file,
        )
        return _lecture_to_response(lecture)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/lectures",
    response_model=List[LectureResponse],
    dependencies=[Depends(check_permission("ai_classroom", "read"))],
)
async def list_lectures(
    teacher_id: Optional[UUID] = Query(None),
    class_id: Optional[UUID] = Query(None),
    subject_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        lectures = await service.list_lectures(
            db,
            current_user.tenant_id,
            teacher_id=teacher_id,
            class_id=class_id,
            subject_id=subject_id,
        )
        return [_lecture_to_response(lecture) for lecture in lectures]
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/lectures/{lecture_id}",
    response_model=LectureResponse,
    dependencies=[Depends(check_permission("ai_classroom", "read"))],
)
async def get_lecture(
    lecture_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        lecture = await service.get_lecture(db, current_user.tenant_id, lecture_id)
        if not lecture:
            raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)
        return _lecture_to_response(lecture)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch(
    "/lectures/{lecture_id}/transcript",
    response_model=LectureResponse,
    dependencies=[Depends(check_permission("ai_classroom", "update_lecture"))],
)
async def update_transcript(
    lecture_id: UUID,
    payload: TranscriptUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update transcript and regenerate embeddings."""
    try:
        lecture = await service.update_transcript(
            db,
            current_user.tenant_id,
            current_user.id,
            lecture_id,
            payload.transcript,
        )
        return _lecture_to_response(lecture)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/doubts",
    response_model=DoubtAskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("ai_classroom", "ask_doubt"))],
)
async def ask_doubt(
    payload: DoubtAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        chat, ai_message = await service.ask_doubt(
            db,
            current_user.tenant_id,
            current_user.id,
            payload,
        )
        return DoubtAskResponse(
            chat_id=chat.id,
            answer=ai_message.message,
            message=_message_to_response(ai_message),
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/doubts/{chat_id}",
    response_model=DoubtChatResponse,
    dependencies=[Depends(check_permission("ai_classroom", "read"))],
)
async def get_doubt_chat(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        student_id = None
        if current_user.user_type == "student":
            student_id = current_user.id

        chat = await service.get_doubt_chat(
            db,
            current_user.tenant_id,
            chat_id,
            student_id=student_id,
        )
        if not chat:
            raise ServiceError("Chat not found", status.HTTP_404_NOT_FOUND)
        return _chat_to_response(chat)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/doubts",
    response_model=List[DoubtChatResponse],
    dependencies=[Depends(check_permission("ai_classroom", "read"))],
)
async def list_doubt_chats(
    lecture_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        student_id = None
        if current_user.user_type == "student":
            student_id = current_user.id

        chats = await service.list_doubt_chats(
            db,
            current_user.tenant_id,
            student_id=student_id,
            lecture_id=lecture_id,
        )
        return [_chat_to_response(chat) for chat in chats]
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/recording/start",
    response_model=RecordingStartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("ai_classroom", "create_lecture"))],
)
async def start_recording(
    payload: RecordingStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        session = await service.start_recording(
            db,
            current_user.tenant_id,
            current_user.id,
            payload,
        )
        return RecordingStartResponse(
            session_id=session.id,
            status=session.status,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/recording/pause/{session_id}",
    response_model=RecordingStatusResponse,
    dependencies=[Depends(check_permission("ai_classroom", "update_lecture"))],
)
async def pause_recording(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        session = await service.pause_recording(
            db,
            current_user.tenant_id,
            current_user.id,
            session_id,
        )
        return RecordingStatusResponse(
            session_id=session.id,
            status=session.status,
            message="Recording paused successfully",
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/recording/resume/{session_id}",
    response_model=RecordingStatusResponse,
    dependencies=[Depends(check_permission("ai_classroom", "update_lecture"))],
)
async def resume_recording(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        session = await service.resume_recording(
            db,
            current_user.tenant_id,
            current_user.id,
            session_id,
        )
        return RecordingStatusResponse(
            session_id=session.id,
            status=session.status,
            message="Recording resumed successfully",
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/recording/stop/{session_id}",
    response_model=LectureResponse,
    dependencies=[Depends(check_permission("ai_classroom", "update_lecture"))],
)
async def stop_recording(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        session = await service.stop_recording(
            db,
            current_user.tenant_id,
            current_user.id,
            session_id,
        )
        return _lecture_to_response(session)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


async def get_user_from_websocket_token(token: str, db: AsyncSession) -> Optional[CurrentUser]:
    """Authenticate user from WebSocket token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None

    user_id_str = payload.get("user_id") or payload.get("sub")
    tenant_id_str = payload.get("tenant_id")
    role_name = payload.get("role")

    if not user_id_str or not tenant_id_str or not role_name:
        return None

    try:
        user_id = UUID(user_id_str)
        tenant_id = UUID(tenant_id_str)
    except ValueError:
        return None

    from app.auth.models import Role, User
    from sqlalchemy import select

    stmt = select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or user.status != "ACTIVE":
        return None

    role_stmt = select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name)
    role_result = await db.execute(role_stmt)
    role = role_result.scalar_one_or_none()

    permissions = {}
    if role and role.permissions:
        permissions = role.permissions

    academic_year_id = None
    academic_year_status = None
    ay_id_str = payload.get("academic_year_id")
    if ay_id_str:
        try:
            academic_year_id = UUID(ay_id_str)
        except ValueError:
            pass
    academic_year_status = payload.get("academic_year_status")

    return CurrentUser(
        id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        permissions=permissions or {},
        academic_year_id=academic_year_id,
        academic_year_status=academic_year_status,
    )


@router.websocket("/recording/stream/{session_id}")
async def websocket_stream(
    websocket: WebSocket,
    session_id: UUID,
    token: Optional[str] = None,
):
    """WebSocket endpoint for streaming audio chunks."""
    await websocket.accept()

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            if not token:
                await websocket.close(code=1008)
                return

            current_user = await get_user_from_websocket_token(token, db)
            if not current_user:
                await websocket.close(code=1008)
                return

            session = await service.get_recording_session(
                db,
                current_user.tenant_id,
                session_id,
                teacher_id=current_user.id,
            )

            if not session:
                await websocket.send_json({"error": "Session not found or access denied"})
                await websocket.close(code=1008)
                return

            if session.status != "RECORDING":
                await websocket.send_json({"error": f"Session is not recording. Status: {session.status}"})
                await websocket.close(code=1008)
                return

            import logging
            from app.api.v1.ai_classroom.audio_buffer_manager import buffer_manager

            logger = logging.getLogger(__name__)

            await buffer_manager.initialize(session_id)
            logger.info(f"WebSocket connected for session {session_id}, teacher {current_user.id}")

            await websocket.send_json({
                "status": "connected",
                "session_id": str(session_id),
                "message": "Send audio chunks as binary data. Audio will be transcribed when recording stops."
            })

            MAX_BUFFER_SIZE = 200 * 1024 * 1024  # 200MB

            while True:
                try:
                    data = await websocket.receive()

                    if "bytes" in data:
                        audio_bytes = data["bytes"]

                        if len(audio_bytes) < 1024:  # Ignore chunks < 1KB
                            continue

                        session = await service.get_recording_session(
                            db,
                            current_user.tenant_id,
                            session_id,
                            teacher_id=current_user.id,
                        )

                        if not session or session.status != "RECORDING":
                            await websocket.send_json({"error": "Session is no longer recording"})
                            break

                        current_size = await buffer_manager.append_chunk(session_id, audio_bytes)

                        if current_size > MAX_BUFFER_SIZE:
                            logger.error(f"Buffer size {current_size} exceeds limit for session {session_id}")
                            session.status = "PROCESSING"
                            session.is_active_recording = False
                            await db.commit()
                            await buffer_manager.clear(session_id)
                            await websocket.send_json({
                                "error": "Buffer size limit exceeded (200MB). Recording stopped automatically."
                            })
                            break

                        session.audio_buffer_size_bytes = current_size
                        await db.commit()

                        logger.debug(f"Chunk received for session {session_id}, buffer size: {current_size} bytes")

                        await websocket.send_json({
                            "status": "chunk_received",
                            "size": current_size,
                        })


                except WebSocketDisconnect:
                    break
                except Exception as e:
                    await websocket.send_json({"error": f"Processing error: {str(e)}"})
                    break

        except Exception as e:
            try:
                await websocket.send_json({"error": f"Connection error: {str(e)}"})
            except Exception:
                pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

