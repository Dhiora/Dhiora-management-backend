"""
Global WebSocket connection manager for project-wide real-time communication.

Used by: students, employees, admins — subscribe to channels (e.g. session, user, tenant)
and receive/send messages. AI classroom upload progress, processing status, and any
future real-time features use this manager.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Global WebSocket connection manager. Channel-based broadcast."""

    def __init__(self) -> None:
        # channel_id -> set of WebSockets subscribed to this channel
        self._channels: Dict[str, Set[WebSocket]] = {}
        # websocket -> set of channel_ids (for cleanup on disconnect)
        self._connection_channels: Dict[WebSocket, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        channel_ids: List[str],
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Accept connection and subscribe to channels. Multi-tenant safe by channel naming."""
        await websocket.accept()
        async with self._lock:
            self._connection_channels[websocket] = set(channel_ids)
            for ch in channel_ids:
                self._channels.setdefault(ch, set()).add(websocket)
        logger.info("WS connected to channels %s (user=%s tenant=%s)", channel_ids, user_id, tenant_id)

    def register(self, websocket: WebSocket, channel_ids: List[str]) -> None:
        """Register an already-accepted websocket to channels (e.g. from another WS endpoint). Call under lock or before any concurrent send."""
        self._connection_channels[websocket] = set(channel_ids)
        for ch in channel_ids:
            self._channels.setdefault(ch, set()).add(websocket)
        logger.debug("WS registered to channels %s", channel_ids)

    def subscribe(self, websocket: WebSocket, channel_id: str) -> None:
        """Add a channel subscription for an already-connected websocket (call under lock)."""
        self._channels.setdefault(channel_id, set()).add(websocket)
        self._connection_channels.setdefault(websocket, set()).add(channel_id)

    async def add_channel(self, websocket: WebSocket, channel_id: str) -> None:
        """Add a single channel subscription for an already-registered websocket."""
        async with self._lock:
            self._channels.setdefault(channel_id, set()).add(websocket)
            self._connection_channels.setdefault(websocket, set()).add(channel_id)
        logger.debug("WS subscribed to channel %s", channel_id)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove websocket from all channels."""
        async with self._lock:
            channels = self._connection_channels.pop(websocket, set())
            for ch in channels:
                s = self._channels.get(ch)
                if s:
                    s.discard(websocket)
                    if not s:
                        self._channels.pop(ch, None)
        logger.debug("WS disconnected from %s channels", len(channels))

    async def send_to_channel(self, channel_id: str, data: Any) -> None:
        """Send message (dict → JSON) to all connections subscribed to channel_id."""
        async with self._lock:
            sockets = list(self._channels.get(channel_id, set()))
        if not sockets:
            logger.debug("No connections for channel %s", channel_id)
            return
        dead: List[WebSocket] = []
        for ws in sockets:
            try:
                if isinstance(data, dict):
                    await ws.send_json(data)
                else:
                    await ws.send_text(str(data))
            except Exception as e:
                logger.warning("Send to channel %s failed for one connection: %s", channel_id, e)
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    def channel_for_session(self, session_id: str) -> str:
        """Channel id for a recording/lecture session (upload progress, processing, completed)."""
        return f"session:{session_id}"

    def channel_for_user(self, user_id: str) -> str:
        """Channel id for user-specific notifications."""
        return f"user:{user_id}"

    def channel_for_tenant(self, tenant_id: str) -> str:
        """Channel id for tenant-wide broadcast."""
        return f"tenant:{tenant_id}"


# Singleton used across the project (AI classroom, notifications, etc.)
connection_manager = ConnectionManager()
