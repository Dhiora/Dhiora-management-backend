"""In-memory rolling audio buffer manager for real-time streaming."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class BufferHealth:
    buffer_size_bytes: int
    max_buffer_size_bytes: int
    dropped_bytes_total: int
    chunks_emitted_total: int
    last_append_ts: float
    last_emit_ts: float


@dataclass
class ChunkingConfig:
    target_chunk_bytes: int
    overlap_bytes: int
    max_buffer_size_bytes: int


class _SessionBuffer:
    __slots__ = (
        "data",
        "lock",
        "cfg",
        "dropped_bytes_total",
        "chunks_emitted_total",
        "last_append_ts",
        "last_emit_ts",
    )

    def __init__(self, cfg: ChunkingConfig) -> None:
        self.data = bytearray()
        self.lock = asyncio.Lock()
        self.cfg = cfg
        self.dropped_bytes_total = 0
        self.chunks_emitted_total = 0
        now = time.time()
        self.last_append_ts = now
        self.last_emit_ts = 0.0


class AudioBufferManager:
    """
    Rolling in-memory buffer per session.

    - Append tiny frames continuously
    - Emit fixed-ish size chunks with overlap
    - Never clears entire buffer unless asked; trims oldest bytes only
    """

    _instance: Optional["AudioBufferManager"] = None
    _global_lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._buffers: Dict[UUID, _SessionBuffer] = {}
        return cls._instance

    async def initialize(
        self,
        session_id: UUID,
        *,
        target_chunk_bytes: int,
        overlap_bytes: int,
        max_buffer_size_bytes: int,
    ) -> None:
        async with self._global_lock:
            if session_id in self._buffers:
                self._buffers[session_id].cfg = ChunkingConfig(
                    target_chunk_bytes=target_chunk_bytes,
                    overlap_bytes=overlap_bytes,
                    max_buffer_size_bytes=max_buffer_size_bytes,
                )
                return
            self._buffers[session_id] = _SessionBuffer(
                ChunkingConfig(
                    target_chunk_bytes=target_chunk_bytes,
                    overlap_bytes=overlap_bytes,
                    max_buffer_size_bytes=max_buffer_size_bytes,
                )
            )
            logger.info("Initialized rolling audio buffer for session %s", session_id)

    async def clear(self, session_id: UUID) -> None:
        async with self._global_lock:
            self._buffers.pop(session_id, None)

    async def append(self, session_id: UUID, frame: bytes) -> Tuple[int, int]:
        """
        Append frame bytes.
        Returns: (buffer_size_bytes, dropped_bytes_on_this_append)
        """
        sb = self._buffers.get(session_id)
        if sb is None:
            raise RuntimeError(f"Buffer not initialized for session {session_id}")
        dropped = 0
        now = time.time()
        async with sb.lock:
            sb.data.extend(frame)
            sb.last_append_ts = now

            # Hard cap: trim from the front (oldest) if buffer exceeds limit.
            max_size = max(1, sb.cfg.max_buffer_size_bytes)
            if len(sb.data) > max_size:
                to_drop = len(sb.data) - max_size
                del sb.data[:to_drop]
                dropped = to_drop
                sb.dropped_bytes_total += to_drop

            return len(sb.data), dropped

    async def has_ready_chunk(self, session_id: UUID) -> bool:
        sb = self._buffers.get(session_id)
        if sb is None:
            return False
        async with sb.lock:
            return len(sb.data) >= sb.cfg.target_chunk_bytes

    async def pop_ready_chunk(self, session_id: UUID) -> bytes:
        """
        Emit next chunk with overlap retained in buffer.
        If insufficient data, returns b"".
        """
        sb = self._buffers.get(session_id)
        if sb is None:
            return b""
        now = time.time()
        async with sb.lock:
            if len(sb.data) < sb.cfg.target_chunk_bytes:
                return b""

            chunk_size = sb.cfg.target_chunk_bytes
            overlap = min(sb.cfg.overlap_bytes, chunk_size - 1) if chunk_size > 1 else 0
            chunk = bytes(sb.data[:chunk_size])

            # Retain overlap bytes; delete only the consumed portion.
            del sb.data[: max(0, chunk_size - overlap)]

            sb.chunks_emitted_total += 1
            sb.last_emit_ts = now
            return chunk

    async def pop_remaining(self, session_id: UUID) -> bytes:
        """Force-flush all remaining bytes regardless of chunk target size.
        Used at end of recording to ensure partial buffers are not discarded."""
        sb = self._buffers.get(session_id)
        if sb is None:
            return b""
        async with sb.lock:
            if not sb.data:
                return b""
            remaining = bytes(sb.data)
            sb.data.clear()
            return remaining

    async def set_chunk_target(self, session_id: UUID, target_chunk_bytes: int) -> None:
        sb = self._buffers.get(session_id)
        if sb is None:
            return
        async with sb.lock:
            sb.cfg.target_chunk_bytes = max(10_000, int(target_chunk_bytes))

    async def get_size(self, session_id: UUID) -> int:
        sb = self._buffers.get(session_id)
        if sb is None:
            return 0
        async with sb.lock:
            return len(sb.data)

    async def health(self, session_id: UUID) -> BufferHealth:
        sb = self._buffers.get(session_id)
        if sb is None:
            return BufferHealth(
                buffer_size_bytes=0,
                max_buffer_size_bytes=0,
                dropped_bytes_total=0,
                chunks_emitted_total=0,
                last_append_ts=0.0,
                last_emit_ts=0.0,
            )
        async with sb.lock:
            return BufferHealth(
                buffer_size_bytes=len(sb.data),
                max_buffer_size_bytes=sb.cfg.max_buffer_size_bytes,
                dropped_bytes_total=sb.dropped_bytes_total,
                chunks_emitted_total=sb.chunks_emitted_total,
                last_append_ts=sb.last_append_ts,
                last_emit_ts=sb.last_emit_ts,
            )


buffer_manager = AudioBufferManager()

