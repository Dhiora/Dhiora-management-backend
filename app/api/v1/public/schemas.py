from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.core.models.lead import FREE_TOKEN_LIMIT


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(
        None, description="Existing session ID to resume a conversation. Omit to start a new one."
    )
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: str
    lead_id: Optional[str] = None
    reply: str
    lead_captured: bool = Field(False, description="True once name, phone, and email have all been collected")
    limit_reached: bool = Field(False, description="True when the free token quota is exhausted")
    tokens_used: int = Field(0, description="Cumulative tokens consumed in this session")
    tokens_remaining: int = Field(FREE_TOKEN_LIMIT, description="Tokens left before limit is reached")


class ContactSubmitRequest(BaseModel):
    session_id: str = Field(..., description="The session_id from the chat conversation")
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None


class ContactSubmitResponse(BaseModel):
    session_id: str
    lead_id: str
    message: str
    all_collected: bool = Field(
        False, description="True once name, phone, and email are all stored"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Which fields are still needed: name | phone | email",
    )
