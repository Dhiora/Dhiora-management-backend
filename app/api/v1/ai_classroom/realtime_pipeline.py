import asyncio
import io
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional
from uuid import UUID

import openai
from openai import AsyncOpenAI
from sqlalchemy import select

from app.core.config import settings
from app.core.models import AILectureChunk, AILectureSession
from app.db.session import AsyncSessionLocal

from .audio_buffer_manager import buffer_manager
from .service import chunk_text, generate_embeddings_batch

logger = logging.getLogger(__name__)

SendFn = Callable[[dict], Awaitable[None]]


@dataclass
class RealtimeConfig:
    enabled: bool = True
    # Incoming WS frames are expected ~10-50KB.
    max_frame_bytes: int = 80_000

    # Chunking is done in bytes (codec-aware on client: webm/opus preferred).
    target_chunk_bytes: int = 800_000  # ~0.8MB
    min_chunk_bytes: int = 200_000
    max_chunk_bytes: int = 1_200_000
    overlap_bytes: int = 120_000
    max_buffer_size_bytes: int = 3_000_000

    # Queue / backpressure
    max_queue_size: int = 8
    drop_oldest_on_full: bool = True

    # Workers / rate limiting
    workers: int = 1
    whisper_timeout_s: float = 35.0
    whisper_rps_limit: float = 0.8  # requests per second per session

    # Adaptive chunk sizing
    enable_adaptive_chunking: bool = True
    lag_soft_ms: int = 1500
    lag_hard_ms: int = 3500

    # Events
    buffer_health_every_n_frames: int = 8


async def transcribe_chunk(client: AsyncOpenAI, audio_bytes: bytes, *, timeout_s: float) -> str:
    """
    Async chunk transcription using Whisper.
    - NO temp files
    - Resilient: returns "" on failure
    """
    if not audio_bytes:
        return ""
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "chunk.webm"
    try:
        transcription = await asyncio.wait_for(
            client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                temperature=0,
            ),
            timeout=timeout_s,
        )
        return transcription if isinstance(transcription, str) else (transcription.text or "")
    except (asyncio.TimeoutError, openai.APIError) as e:
        logger.warning("Whisper chunk transcription failed: %s", e)
        return ""
    except Exception as e:
        logger.exception("Unexpected Whisper chunk transcription error: %s", e)
        return ""


class _RateLimiter:
    """Simple per-session RPS limiter."""

    def __init__(self, rps: float) -> None:
        self._min_interval = 1.0 / max(0.01, rps)
        self._lock = asyncio.Lock()
        self._last_ts = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.time()
            delta = now - self._last_ts
            if delta < self._min_interval:
                await asyncio.sleep(self._min_interval - delta)
            self._last_ts = time.time()


@dataclass
class _SessionState:
    queue: "asyncio.Queue[bytes]"
    send: SendFn
    stop_event: asyncio.Event
    tasks: list
    limiter: _RateLimiter
    last_processing_ms: float = 0.0
    last_emit_ts: float = 0.0


class RealtimePipelineManager:
    """
    Manages realtime transcription/RAG per recording session.
    One queue per session, N workers per session.
    """

    def __init__(self) -> None:
        self._states: Dict[UUID, _SessionState] = {}
        self._lock = asyncio.Lock()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def start(self, session_id: UUID, send: SendFn, cfg: RealtimeConfig) -> None:
        async with self._lock:
            if session_id in self._states:
                return
            q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=max(1, cfg.max_queue_size))
            state = _SessionState(
                queue=q,
                send=send,
                stop_event=asyncio.Event(),
                tasks=[],
                limiter=_RateLimiter(cfg.whisper_rps_limit),
            )
            self._states[session_id] = state

            for idx in range(max(1, cfg.workers)):
                state.tasks.append(asyncio.create_task(self._worker(session_id, idx, cfg)))

    async def stop(self, session_id: UUID, *, drain_timeout_s: float = 20.0) -> None:
        state = self._states.get(session_id)
        if not state:
            return
        state.stop_event.set()
        try:
            await asyncio.wait_for(state.queue.join(), timeout=drain_timeout_s)
        except asyncio.TimeoutError:
            pass
        for t in state.tasks:
            t.cancel()
        await asyncio.gather(*state.tasks, return_exceptions=True)
        async with self._lock:
            self._states.pop(session_id, None)

    async def enqueue(self, session_id: UUID, audio_chunk: bytes, cfg: RealtimeConfig) -> bool:
        state = self._states.get(session_id)
        if not state or state.stop_event.is_set():
            return False
        try:
            state.queue.put_nowait(audio_chunk)
            return True
        except asyncio.QueueFull:
            if not cfg.drop_oldest_on_full:
                return False
            try:
                _ = state.queue.get_nowait()
                state.queue.task_done()
            except asyncio.QueueEmpty:
                pass
            try:
                state.queue.put_nowait(audio_chunk)
                return True
            except asyncio.QueueFull:
                return False

    async def _append_transcript(self, session_id: UUID, new_text: str) -> None:
        if not new_text:
            return
        async with AsyncSessionLocal() as db:
            # Single worker per session keeps this sequential; still use FOR UPDATE for safety.
            stmt = select(AILectureSession).where(AILectureSession.id == session_id).with_for_update()
            res = await db.execute(stmt)
            session = res.scalar_one_or_none()
            if not session:
                return
            base = (session.transcript or "").strip()
            session.transcript = (base + " " + new_text).strip() if base else new_text.strip()
            await db.commit()

    async def _embed_and_insert(self, session_id: UUID, tenant_id: UUID, text: str) -> None:
        if not text:
            return
        try:
            chunks = chunk_text(text)
            if not chunks:
                return
            embeddings = await generate_embeddings_batch(chunks)
            async with AsyncSessionLocal() as db:
                for c, emb in zip(chunks, embeddings):
                    db.add(
                        AILectureChunk(
                            tenant_id=tenant_id,
                            lecture_id=session_id,
                            content=c,
                            embedding=emb,
                        )
                    )
                await db.commit()
        except Exception:
            logger.exception("Embedding/insert failed for session %s", session_id)

    async def _worker(self, session_id: UUID, worker_idx: int, cfg: RealtimeConfig) -> None:
        state = self._states[session_id]
        while not state.stop_event.is_set():
            audio_bytes = await state.queue.get()
            started = time.time()
            try:
                await state.limiter.wait()
                text = await transcribe_chunk(self._client, audio_bytes, timeout_s=cfg.whisper_timeout_s)
                if text:
                    # Fetch tenant_id once per chunk (cheap) for RAG insert.
                    async with AsyncSessionLocal() as db:
                        res = await db.execute(
                            select(AILectureSession.tenant_id).where(AILectureSession.id == session_id)
                        )
                        tenant_id = res.scalar_one_or_none()
                    if tenant_id:
                        await self._append_transcript(session_id, text)
                        # Do embeddings async and non-blocking w.r.t. transcription pipeline
                        asyncio.create_task(self._embed_and_insert(session_id, tenant_id, text))
                        await state.send({"type": "transcript_chunk", "text": text})
            except Exception:
                logger.exception("Realtime worker %s failed for session %s", worker_idx, session_id)
            finally:
                state.queue.task_done()
                elapsed_ms = (time.time() - started) * 1000.0
                state.last_processing_ms = elapsed_ms


realtime_pipeline = RealtimePipelineManager()

