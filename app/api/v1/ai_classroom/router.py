"""AI Classroom API router."""

import asyncio
import json
from typing import Dict, List, Optional
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
    AdminDoubtRequest,
    DoubtAskRequest,
    DoubtAskResponse,
    DoubtChatResponse,
    DoubtMessageResponse,
    LectureCreate,
    LectureResponse,
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
    response_model=DoubtAskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
    tags=["AI Classroom"],
)
async def ask_doubt_student(
    payload: StudentDoubtRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        chat, ai_message = await service.ask_doubt_student(
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
    "/doubt/admin",
    response_model=DoubtAskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
    tags=["AI Classroom"],
)
async def ask_doubt_admin(
    payload: AdminDoubtRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        chat, ai_message = await service.ask_doubt_admin(
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
    response_model=StopRecordingResponse,
    dependencies=[Depends(check_permission("ai_classroom", "update_lecture"))],
)
async def stop_recording(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        await service.stop_recording(
            db,
            current_user.tenant_id,
            current_user.id,
            session_id,
        )
        return StopRecordingResponse(status="UPLOADING", message="Recording stopped. Uploading in progress.")
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


# In-memory upload state: session_id (str) -> { "total_size": int, "received_size": int }
_upload_state: Dict[str, dict] = {}
_upload_state_lock = asyncio.Lock()

UPLOAD_DIR = "/tmp"


@router.websocket("/recording/stream/{session_id}")
async def websocket_stream(
    websocket: WebSocket,
    session_id: UUID,
    token: Optional[str] = None,
):
    """
    WebSocket for upload-after-stop: teacher sends upload_start (total_size), then binary chunks,
    then upload_complete. Server writes to /tmp/lecture_{session_id}.webm and reports progress.
    On upload_complete, background processing runs and status 'completed'/'failed' is sent to this channel.
    """
    import logging
    from datetime import datetime, timezone

    from app.core.websocket import connection_manager
    from app.db.session import AsyncSessionLocal

    logger = logging.getLogger(__name__)
    await websocket.accept()

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

            if session.status != "UPLOADING":
                await websocket.send_json({
                    "error": f"Session must be UPLOADING (call STOP first). Current: {session.status}",
                })
                await websocket.close(code=1008)
                return

            channel_id = connection_manager.channel_for_session(str(session_id))
            connection_manager.register(websocket, [channel_id])

            await websocket.send_json({
                "status": "connected",
                "session_id": str(session_id),
                "message": "Send first message: {\"type\": \"upload_start\", \"total_size\": <bytes>}. Then binary chunks. Then {\"type\": \"upload_complete\"}.",
            })

            sid_str = str(session_id)
            file_path = f"{UPLOAD_DIR}/lecture_{session_id}.webm"

            while True:
                try:
                    data = await websocket.receive()

                    if "text" in data:
                        try:
                            msg = json.loads(data["text"])
                        except json.JSONDecodeError:
                            await websocket.send_json({"error": "Invalid JSON"})
                            continue

                        if msg.get("type") == "upload_start":
                            total = msg.get("total_size")
                            if total is None or not isinstance(total, (int, float)) or total <= 0:
                                await websocket.send_json({"error": "upload_start requires total_size (positive number)"})
                                continue
                            async with _upload_state_lock:
                                _upload_state[sid_str] = {"total_size": int(total), "received_size": 0}
                            with open(file_path, "wb") as _:
                                pass
                            await websocket.send_json({"status": "upload_started", "total_size": int(total)})
                            continue

                        if msg.get("type") == "upload_complete":
                            session = await service.get_recording_session(
                                db, current_user.tenant_id, session_id, teacher_id=current_user.id
                            )
                            if not session or session.status != "UPLOADING":
                                await websocket.send_json({"error": "Session not in UPLOADING state"})
                                break
                            session.upload_completed = True
                            session.status = "PROCESSING"
                            session.processing_stage = "TRANSCRIBING"
                            session.audio_file_path = file_path
                            await db.commit()
                            asyncio.create_task(service.process_lecture_background(session_id))
                            await websocket.send_json({"status": "processing"})
                            async with _upload_state_lock:
                                _upload_state.pop(sid_str, None)
                            break

                    if "bytes" in data:
                        audio_bytes = data["bytes"]
                        if not audio_bytes:
                            continue
                        async with _upload_state_lock:
                            state = _upload_state.get(sid_str)
                        if not state:
                            await websocket.send_json({"error": "Send upload_start with total_size first"})
                            continue
                        with open(file_path, "ab") as f:
                            f.write(audio_bytes)
                        async with _upload_state_lock:
                            _upload_state[sid_str]["received_size"] += len(audio_bytes)
                            received = _upload_state[sid_str]["received_size"]
                            total = _upload_state[sid_str]["total_size"]
                        progress = min(100, int((received / total) * 100)) if total else 0

                        session = await service.get_recording_session(
                            db, current_user.tenant_id, session_id, teacher_id=current_user.id
                        )
                        if session and session.status == "UPLOADING":
                            session.upload_progress_percent = progress
                            session.last_chunk_received_at = datetime.now(timezone.utc)
                            await db.commit()
                        await websocket.send_json({"status": "uploading", "progress": progress})

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
            async with _upload_state_lock:
                _upload_state.pop(str(session_id), None)
            try:
                await connection_manager.disconnect(websocket)
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass

