"""Public API — no authentication required. Called before login."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

from . import service
from .schemas import (
    ChatRequest,
    ChatResponse,
    ContactSubmitRequest,
    ContactSubmitResponse,
)

router = APIRouter(prefix="/api/v1/public", tags=["public / chatbot"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Public AI chatbot for the Dhiora website. No authentication required.

    - Pass `session_id` from the previous response to continue the conversation.
    - `limit_reached: true` means the free quota (3 000 tokens) is exhausted.
      Switch the frontend to the contact-form UI and call `POST /api/v1/public/contact`.
    - `tokens_remaining` tells the frontend how many tokens are left so it can
      show a progress indicator if desired.
    """
    if not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message cannot be empty",
        )
    result = await service.chat(db, payload.session_id, payload.message.strip())
    return ChatResponse(**result)


@router.post("/contact", response_model=ContactSubmitResponse)
async def submit_contact(
    payload: ContactSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> ContactSubmitResponse:
    """
    Submit contact details after the AI token limit is reached.

    The frontend should render a structured form (name / phone / email) and call
    this endpoint on submit. If some fields are still missing, `all_collected`
    will be `false` and `missing_fields` will list what's still needed.
    Keep calling until `all_collected` is `true`.
    """
    result = await service.submit_contact(
        db,
        payload.session_id,
        payload.name,
        payload.phone,
        str(payload.email) if payload.email else None,
    )
    return ContactSubmitResponse(**result)
