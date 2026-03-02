"""In-memory audio buffer manager for WebSocket streaming."""

import asyncio
import logging
from typing import Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class AudioBufferManager:
    """Thread-safe in-memory audio buffer manager per session."""

    _instance: Optional["AudioBufferManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.buffers: Dict[UUID, bytearray] = {}
            cls._instance.locks: Dict[UUID, asyncio.Lock] = {}
        return cls._instance

    async def _get_lock(self, session_id: UUID) -> asyncio.Lock:
        """Get or create lock for session."""
        async with self._lock:
            if session_id not in self.locks:
                self.locks[session_id] = asyncio.Lock()
            return self.locks[session_id]

    async def initialize(self, session_id: UUID) -> None:
        """Initialize buffer for session."""
        lock = await self._get_lock(session_id)
        async with lock:
            if session_id not in self.buffers:
                self.buffers[session_id] = bytearray()
                logger.info(f"Initialized audio buffer for session {session_id}")

    async def append_chunk(self, session_id: UUID, chunk: bytes) -> int:
        """Append audio chunk to buffer. Returns new buffer size."""
        lock = await self._get_lock(session_id)
        async with lock:
            if session_id not in self.buffers:
                self.buffers[session_id] = bytearray()
            self.buffers[session_id].extend(chunk)
            size = len(self.buffers[session_id])
            logger.debug(f"Appended {len(chunk)} bytes to session {session_id}, total: {size} bytes")
            return size

    async def get_buffer(self, session_id: UUID) -> bytes:
        """Get full buffer as bytes."""
        lock = await self._get_lock(session_id)
        async with lock:
            if session_id not in self.buffers:
                return b""
            return bytes(self.buffers[session_id])

    async def clear(self, session_id: UUID) -> None:
        """Clear buffer for session."""
        lock = await self._get_lock(session_id)
        async with lock:
            if session_id in self.buffers:
                size = len(self.buffers[session_id])
                del self.buffers[session_id]
                logger.info(f"Cleared audio buffer for session {session_id} (was {size} bytes)")
            if session_id in self.locks:
                del self.locks[session_id]

    async def get_size(self, session_id: UUID) -> int:
        """Get current buffer size in bytes."""
        lock = await self._get_lock(session_id)
        async with lock:
            if session_id not in self.buffers:
                return 0
            return len(self.buffers[session_id])


buffer_manager = AudioBufferManager()

