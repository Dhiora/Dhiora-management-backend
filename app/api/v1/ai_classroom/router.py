"""AI Classroom API router."""

import asyncio
import json
import time
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

    PRIMARY: realtime chunk pipeline (transcribe + embed + RAG while recording).
    FALLBACK: file-based buffering + batch processing.
    """
    import logging
    from datetime import datetime, timezone

    from app.db.session import AsyncSessionLocal
    from app.api.v1.ai_classroom.audio_buffer_manager import buffer_manager
    from app.api.v1.ai_classroom.realtime_pipeline import RealtimeConfig, realtime_pipeline
    from app.core.config import settings

    logger = logging.getLogger(__name__)
    await websocket.accept()

    real_cfg = RealtimeConfig(
        enabled=bool(settings.ai_realtime_enabled),
        max_frame_bytes=int(settings.ai_realtime_max_frame_bytes),
        target_chunk_bytes=int(settings.ai_realtime_target_chunk_bytes),
        min_chunk_bytes=int(settings.ai_realtime_min_chunk_bytes),
        max_chunk_bytes=int(settings.ai_realtime_max_chunk_bytes),
        overlap_bytes=int(settings.ai_realtime_overlap_bytes),
        max_buffer_size_bytes=int(settings.ai_realtime_max_buffer_size_bytes),
        max_queue_size=int(settings.ai_realtime_max_queue_size),
        workers=int(settings.ai_realtime_workers),
        whisper_timeout_s=float(settings.ai_realtime_whisper_timeout_s),
        whisper_rps_limit=float(settings.ai_realtime_whisper_rps_limit),
        enable_adaptive_chunking=bool(settings.ai_realtime_enable_adaptive_chunking),
        lag_soft_ms=int(settings.ai_realtime_lag_soft_ms),
        lag_hard_ms=int(settings.ai_realtime_lag_hard_ms),
        buffer_health_every_n_frames=int(settings.ai_realtime_buffer_health_every_n_frames),
    )

    send_lock = asyncio.Lock()

    async def _safe_send(payload: dict) -> None:
        try:
            async with send_lock:
                await websocket.send_json(payload)
        except Exception:
            # Never crash receive loop because client is gone
            pass

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
                "real_time_enabled": bool(real_cfg.enabled),
            })

            if real_cfg.enabled:
                await buffer_manager.initialize(
                    session_id,
                    target_chunk_bytes=real_cfg.target_chunk_bytes,
                    overlap_bytes=real_cfg.overlap_bytes,
                    max_buffer_size_bytes=real_cfg.max_buffer_size_bytes,
                )
                await realtime_pipeline.start(session_id, _safe_send, real_cfg)
                await _safe_send({"type": "processing_status", "stage": "STREAMING"})
            else:
                # Fallback: write incoming audio to disk in chunks
                file_path = f"{UPLOAD_DIR}/lecture_{session_id}.webm"
                f = await asyncio.to_thread(open, file_path, "ab")
                FLUSH_THRESHOLD_BYTES = 5 * 1024 * 1024  # 5MB
                await buffer_manager.initialize(
                    session_id,
                    target_chunk_bytes=FLUSH_THRESHOLD_BYTES,
                    overlap_bytes=0,
                    max_buffer_size_bytes=FLUSH_THRESHOLD_BYTES,
                )

            frames_seen = 0
            last_health_send = 0.0
            # How long to wait on receive() before checking session status.
            # Short enough to detect STOPPING quickly; long enough to not spam DB.
            RECEIVE_IDLE_TIMEOUT_S = 2.0

            while True:
                try:
                    # Use a timeout so that if the frontend stops sending frames (e.g. after
                    # calling POST /recording/stop) but doesn't immediately close the WebSocket,
                    # we can detect the STOPPING status and break cleanly rather than hanging
                    # forever at `await websocket.receive()`.
                    try:
                        message = await asyncio.wait_for(
                            websocket.receive(), timeout=RECEIVE_IDLE_TIMEOUT_S
                        )
                    except asyncio.TimeoutError:
                        # No frame arrived — check whether the frontend has requested stop.
                        try:
                            current_session = await service.get_recording_session(
                                db, current_user.tenant_id, session_id, teacher_id=current_user.id
                            )
                            if current_session and current_session.status == "STOPPING":
                                # Frontend stopped sending; proceed to finalize.
                                logger.info(
                                    "Session %s is STOPPING and no audio received for %.1fs — finalizing.",
                                    session_id, RECEIVE_IDLE_TIMEOUT_S,
                                )
                                break
                        except Exception:
                            pass
                        continue

                    msg_type = message.get("type")

                    if msg_type == "websocket.disconnect":
                        break

                    if msg_type != "websocket.receive":
                        continue

                    # Handle text frames: check for end-of-stream signal from the frontend.
                    # Frontend should send {"type": "end_of_stream"} when it has finished
                    # sending all audio chunks and wants the backend to finalize.
                    text_data = message.get("text")
                    if text_data:
                        try:
                            ctrl = json.loads(text_data)
                            if ctrl.get("type") in ("end_of_stream", "stop_stream"):
                                logger.info(
                                    "Session %s received end_of_stream signal — finalizing.",
                                    session_id,
                                )
                                break
                        except (json.JSONDecodeError, Exception):
                            pass
                        # Any other text frame: ignore and keep listening for audio.
                        continue

                    # Binary frame: process as audio.
                    audio_bytes = message.get("bytes")
                    if audio_bytes and len(audio_bytes) > 0:
                        if len(audio_bytes) > real_cfg.max_frame_bytes:
                            # Drop oversized frames to prevent spikes
                            await _safe_send({"type": "buffer_health", "dropped": len(audio_bytes), "reason": "frame_too_large"})
                            continue

                        frames_seen += 1
                        await buffer_manager.append(session_id, audio_bytes)

                        if real_cfg.enabled:
                            # Emit chunks without blocking receive loop
                            while await buffer_manager.has_ready_chunk(session_id):
                                chunk = await buffer_manager.pop_ready_chunk(session_id)
                                if not chunk:
                                    break
                                ok = await realtime_pipeline.enqueue(session_id, chunk, real_cfg)
                                if not ok:
                                    # Queue full and drop occurred; remaining ready chunks stay
                                    # in buffer_manager and will be flushed on finalization.
                                    break

                            # Adaptive chunk sizing based on lag/queue pressure (cheap heuristic)
                            if real_cfg.enable_adaptive_chunking:
                                health = await buffer_manager.health(session_id)
                                now = time.time()
                                lag_ms = max(0.0, (now - health.last_emit_ts) * 1000.0) if health.last_emit_ts else 0.0
                                if lag_ms > real_cfg.lag_hard_ms:
                                    new_target = max(real_cfg.min_chunk_bytes, int(health.buffer_size_bytes * 0.5))
                                    await buffer_manager.set_chunk_target(session_id, new_target)
                                elif lag_ms < real_cfg.lag_soft_ms:
                                    await buffer_manager.set_chunk_target(session_id, real_cfg.target_chunk_bytes)

                            # Periodic health event
                            if frames_seen % max(1, real_cfg.buffer_health_every_n_frames) == 0:
                                health = await buffer_manager.health(session_id)
                                now = time.time()
                                if now - last_health_send > 0.4:
                                    last_health_send = now
                                    await _safe_send(
                                        {
                                            "type": "buffer_health",
                                            "buffer_size": health.buffer_size_bytes,
                                            "max_buffer_size": health.max_buffer_size_bytes,
                                            "dropped_bytes_total": health.dropped_bytes_total,
                                            "chunks_emitted_total": health.chunks_emitted_total,
                                        }
                                    )
                        else:
                            # Fallback: flush to disk only when threshold reached
                            if await buffer_manager.has_ready_chunk(session_id):
                                data_to_write = await buffer_manager.pop_ready_chunk(session_id)
                                if data_to_write:
                                    await asyncio.to_thread(f.write, data_to_write)
                                    await asyncio.to_thread(f.flush)

                        # Lightweight session heartbeat (do not block too often)
                        if frames_seen % 10 == 0:
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
                    try:
                        await websocket.send_json({"error": f"Processing error: {str(e)}"})
                    except Exception:
                        pass
                    break

        except Exception as e:
            logger.exception("WebSocket stream connection error")
            try:
                await websocket.send_json({"error": str(e)})
            except Exception:
                pass
        finally:
            if real_cfg.enabled:
                # Drain: emit all ready chunks, then force-flush any remaining partial buffer.
                try:
                    while await buffer_manager.has_ready_chunk(session_id):
                        chunk = await buffer_manager.pop_ready_chunk(session_id)
                        if not chunk:
                            break
                        await realtime_pipeline.enqueue(session_id, chunk, real_cfg)
                    # Force-flush bytes below target_chunk_bytes (short recordings or tail audio)
                    remaining = await buffer_manager.pop_remaining(session_id)
                    if remaining:
                        await realtime_pipeline.enqueue(session_id, remaining, real_cfg)
                except Exception:
                    pass

                # Transition states as per existing lifecycle
                try:
                    session = await service.get_recording_session(
                        db, current_user.tenant_id, session_id, teacher_id=current_user.id
                    )
                    if session and session.status in ("RECORDING", "PAUSED", "STOPPING"):
                        session.upload_completed = True
                        session.status = "PROCESSING"
                        session.processing_stage = "FINALIZING"
                        session.upload_progress_percent = 95
                        await db.commit()
                        await _safe_send({"type": "processing_status", "stage": "FINALIZING"})
                except Exception:
                    logger.exception("Failed to transition session %s to PROCESSING (realtime)", session_id)

                await realtime_pipeline.stop(
                    session_id,
                    drain_timeout_s=20.0,
                    whisper_timeout_s=real_cfg.whisper_timeout_s,
                )

                try:
                    session = await service.get_recording_session(
                        db, current_user.tenant_id, session_id, teacher_id=current_user.id
                    )
                    if session:
                        session.status = "COMPLETED"
                        session.processing_stage = "DONE"
                        session.upload_progress_percent = 100
                        await db.commit()
                        await _safe_send({"type": "processing_status", "stage": "DONE"})
                except Exception:
                    logger.exception("Failed to finalize session %s (realtime)", session_id)
            else:
                # Fallback: flush remaining data and run background processor
                try:
                    remaining = b""
                    while await buffer_manager.has_ready_chunk(session_id):
                        remaining += await buffer_manager.pop_ready_chunk(session_id)
                    if remaining and f is not None:
                        await asyncio.to_thread(f.write, remaining)
                        await asyncio.to_thread(f.flush)
                except Exception:
                    logger.exception("Failed flushing remaining buffer for session %s (fallback)", session_id)
                finally:
                    try:
                        if f is not None:
                            await asyncio.to_thread(f.close)
                    except Exception:
                        pass

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

