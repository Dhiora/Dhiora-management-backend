"""AI Classroom API router."""

import asyncio
import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
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
    AdminDoubtRequest,
    DoubtAskRequest,
    DoubtAskResponse,
    DoubtChatResponse,
    DoubtMessageResponse,
    LectureCreate,
    LectureResponse,
    ManagementChatRequest,
    RecordingStartRequest,
    RecordingStartResponse,
    RecordingStatusResponse,
    StudentDoubtRequest,
    StopRecordingResponse,
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
        upload_completed=getattr(lecture, "upload_completed", False),
        audio_file_path=getattr(lecture, "audio_file_path", None),
        processing_stage=getattr(lecture, "processing_stage", None),
        last_chunk_received_at=getattr(lecture, "last_chunk_received_at", None),
        upload_progress_percent=getattr(lecture, "upload_progress_percent", 0),
        created_at=lecture.created_at,
        class_name=getattr(lecture, "_class_name", None),
        subject_name=getattr(lecture, "_subject_name", None),
        section_name=getattr(lecture, "_section_name", None),
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


@router.delete(
    "/lectures/{lecture_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("ai_classroom", "delete_lecture"))],
)
async def delete_lecture(
    lecture_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Permanently delete a lecture and its related data."""
    try:
        is_admin = current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN")
        deleted = await service.delete_lecture(
        db,
        current_user.tenant_id,
        current_user.id,
        lecture_id,
        is_admin=is_admin,
    )
        if not deleted:
            raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)
        return
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


@router.post(
    "/doubt/student",
    dependencies=[Depends(get_current_user)],
    tags=["AI Classroom"],
)
async def ask_doubt_student(
    payload: StudentDoubtRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Student doubt: returns Event Stream (SSE). Events: chunk (content), then done (chat_id, message)."""
    async def event_stream():
        try:
            async for event in service.ask_doubt_student_stream(
                db,
                current_user.tenant_id,
                current_user.id,
                payload,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except ServiceError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': e.message, 'status_code': e.status_code})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/doubt/admin",
    dependencies=[Depends(get_current_user)],
    tags=["AI Classroom"],
)
async def ask_doubt_admin(
    payload: AdminDoubtRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Admin doubt: returns Event Stream (SSE). Events: chunk (content), then done (chat_id, message)."""
    async def event_stream():
        try:
            async for event in service.ask_doubt_admin_stream(
                db,
                current_user.tenant_id,
                current_user.id,
                payload,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except ServiceError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': e.message, 'status_code': e.status_code})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


@router.post(
    "/management/chat",
    dependencies=[Depends(get_current_user)],
    tags=["AI Classroom"],
)
async def management_chat(
    payload: ManagementChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Single unified management chat API.

    - Uses vector DB (management_knowledge_chunks) to answer questions
    - Enforces role-based access: if the relevant data is not readable
      for this user, it returns an access-denied message instead of data
    - Returns SSE stream: events 'chunk' and 'done' (and 'error' on failure)
    """

    async def event_stream():
        try:
            async for event in service.management_chat_stream(
                db=db,
                current_user=current_user,
                payload=payload,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except ServiceError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': e.message, 'status_code': e.status_code})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    response_model=StopRecordingResponse,
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
        return StopRecordingResponse(
            status=session.status,
            message="Recording stopped. Processing lecture in background.",
        )
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


UPLOAD_DIR = "/tmp"


@router.websocket("/recording/stream/{session_id}")
async def websocket_stream(
    websocket: WebSocket,
    session_id: UUID,
    token: Optional[str] = None,
):
    """
    WebSocket for live audio chunk streaming during recording.

    - Receives bytes frames only (audio chunks)
    - Buffers chunks in memory (bytearray) and flushes to disk when >= 5MB
    - On client disconnect (stop recording), flushes remaining buffer, marks session PROCESSING,
      and triggers background processing (transcription + embeddings).
    """
    import logging
    from datetime import datetime, timezone

    from app.db.session import AsyncSessionLocal
    from app.api.v1.ai_classroom.audio_buffer_manager import buffer_manager

    logger = logging.getLogger(__name__)
    await websocket.accept()

    file_path = f"{UPLOAD_DIR}/lecture_{session_id}.webm"
    f = None
    FLUSH_THRESHOLD_BYTES = 5 * 1024 * 1024  # 5MB

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

            if session.status not in ("RECORDING", "PAUSED", "STOPPING"):
                await websocket.send_json({
                    "error": f"Session must be RECORDING/PAUSED to stream. Current: {session.status}",
                })
                await websocket.close(code=1008)
                return

            await websocket.send_json({
                "status": "connected",
                "session_id": str(session_id),
                "message": "Send audio as binary WebSocket frames. Close the socket to stop & finalize.",
            })

            await buffer_manager.initialize(session_id)
            # Keep file handle open to minimize disk I/O overhead
            f = open(file_path, "ab")

            while True:
                try:
                    audio_bytes = await websocket.receive_bytes()
                    if not audio_bytes:
                        continue

                    await buffer_manager.append_chunk(session_id, audio_bytes)

                    # Flush to disk only when threshold reached
                    if await buffer_manager.should_flush(session_id, FLUSH_THRESHOLD_BYTES):
                        data_to_write = await buffer_manager.pop_all(session_id)
                        if data_to_write:
                            f.write(data_to_write)
                            f.flush()

                    # Lightweight session heartbeat (optional)
                    session = await service.get_recording_session(
                        db, current_user.tenant_id, session_id, teacher_id=current_user.id
                    )
                    if session and session.status in ("RECORDING", "PAUSED", "STOPPING"):
                        session.last_chunk_received_at = datetime.now(timezone.utc)
                        session.audio_buffer_size_bytes = await buffer_manager.get_size(session_id)
                        await db.commit()

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.exception("WebSocket stream error")
                    await websocket.send_json({"error": f"Processing error: {str(e)}"})
                    break

        except Exception as e:
            logger.exception("WebSocket stream connection error")
            try:
                await websocket.send_json({"error": str(e)})
            except Exception:
                pass
        finally:
            try:
                # Flush any remaining buffered data before closing
                if f is None:
                    f = open(file_path, "ab")
                remaining = await buffer_manager.pop_all(session_id)
                if remaining:
                    f.write(remaining)
                    f.flush()
            except Exception:
                logger.exception("Failed flushing remaining buffer for session %s", session_id)
            finally:
                try:
                    if f is not None:
                        f.close()
                except Exception:
                    pass

            # After all audio has been written, mark session PROCESSING and start background task.
            try:
                session = await service.get_recording_session(
                    db, current_user.tenant_id, session_id, teacher_id=current_user.id
                )
                if session and session.status in ("RECORDING", "PAUSED", "STOPPING"):
                    session.audio_file_path = file_path
                    session.upload_completed = True
                    session.status = "PROCESSING"
                    session.processing_stage = "TRANSCRIBING"
                    session.upload_progress_percent = max(getattr(session, "upload_progress_percent", 0) or 0, 10)
                    await db.commit()

                    from app.core.websocket import connection_manager

                    # Notify UI that processing has started
                    await connection_manager.send_to_channel(
                        connection_manager.channel_for_session(str(session_id)),
                        {
                            "status": "processing",
                            "processing_stage": session.processing_stage,
                            "upload_completed": bool(getattr(session, "upload_completed", False)),
                            "progress": session.upload_progress_percent,
                        },
                    )

                    asyncio.create_task(service.process_lecture_background(session_id))
            except Exception:
                logger.exception("Failed to transition session %s to PROCESSING after stream close", session_id)

            try:
                await buffer_manager.clear(session_id)
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass

