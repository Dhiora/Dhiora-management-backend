"""
Global WebSocket endpoint for project-wide real-time communication.

Students, employees, and admins connect here for real-time updates (e.g. lecture
processing status, notifications, future features). Authenticate with token in query.
Subscribe to channels via JSON messages: { "type": "subscribe", "channel": "session:uuid" }
or { "type": "subscribe", "channels": ["session:uuid", "user:uuid"] }.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.websocket import connection_manager
from app.db.session import AsyncSessionLocal
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])


async def get_user_from_ws_token(token: str) -> Optional[dict]:
    """Validate JWT and return user_id, tenant_id, role for multi-tenant safety."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None
    user_id = payload.get("user_id") or payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")
    if not user_id or not tenant_id or not role:
        return None
    return {"user_id": str(user_id), "tenant_id": str(tenant_id), "role": role}


@router.websocket("")
async def global_websocket(
    websocket: WebSocket,
    token: Optional[str] = None,
):
    """
    Global WebSocket: connect with ?token=JWT. Then send:
    - {"type": "subscribe", "channel": "session:uuid"} or
    - {"type": "subscribe", "channels": ["session:uuid", "user:uuid"]}
    to receive messages for those channels. Used project-wide for real-time communication.
    """
    if not token:
        await websocket.close(code=1008)
        return

    user = await get_user_from_ws_token(token)
    if not user:
        await websocket.close(code=1008)
        return

    user_id = user["user_id"]
    tenant_id = user["tenant_id"]

    await connection_manager.connect(
        websocket,
        channel_ids=[connection_manager.channel_for_user(user_id)],
        user_id=user_id,
        tenant_id=tenant_id,
    )

    await websocket.send_json({
        "status": "connected",
        "message": f"Send {{\"type\": \"subscribe\", \"channel\": \"...\"}} or {{\"channels\": [...]}} to subscribe. You are subscribed to user:{user_id} by default.",
        "user_id": user_id,
    })

    try:
        while True:
            data = await websocket.receive()
            if "text" not in data:
                continue
            try:
                msg = json.loads(data["text"])
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            msg_type = msg.get("type")
            if msg_type == "subscribe":
                channel = msg.get("channel")
                channels = msg.get("channels")
                if channel:
                    await connection_manager.add_channel(websocket, channel)
                    await websocket.send_json({"status": "subscribed", "channel": channel})
                elif isinstance(channels, list):
                    for ch in channels:
                        if isinstance(ch, str):
                            await connection_manager.add_channel(websocket, ch)
                    await websocket.send_json({"status": "subscribed", "channels": channels})
                else:
                    await websocket.send_json({"error": "subscribe requires 'channel' or 'channels'"})
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("Global WebSocket error")
    finally:
        await connection_manager.disconnect(websocket)
