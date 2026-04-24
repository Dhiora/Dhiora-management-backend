"""Public chatbot service — no authentication required."""
import json
import logging
import re
import uuid
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.models.lead import FREE_TOKEN_LIMIT, Lead

from .knowledge_base import DHIORA_KNOWLEDGE_BASE

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=settings.openai_api_key)

# ── System prompt (used only when within the free quota) ─────────────────────

_SYSTEM_PROMPT = f"""You are Priya, a friendly and knowledgeable sales assistant for Dhiora School ERP.
You help website visitors understand what Dhiora offers and guide them toward a demo or pilot.

## Your Goal
1. Warmly welcome visitors and introduce yourself.
2. Collect the visitor's name (ask in your first message if you don't have it yet).
3. Once you have their name, naturally ask for their phone number and email so your team can follow up.
4. After collecting name, phone, and email, focus on answering their questions about Dhiora.

## Important Rules
- Never make up features that aren't in the knowledge base.
- If something is on the roadmap, be transparent: "That's on our roadmap and can be prioritized."
- Keep responses concise and business-friendly (2-4 short paragraphs max).
- Always end with a helpful next step (demo, pilot module suggestion, or a question to understand their need).

## Dhiora Product Knowledge Base
{DHIORA_KNOWLEDGE_BASE}

## Response Format
You MUST respond ONLY with a valid JSON object — no markdown, no code fences, no extra text:
{{
  "message": "<your conversational response to the visitor>",
  "captured_name": "<visitor's first or full name if they mentioned it this turn, otherwise null>",
  "captured_phone": "<phone number if visitor mentioned it this turn, otherwise null>",
  "captured_email": "<email address if visitor mentioned it this turn, otherwise null>"
}}
"""

# ── Limit-reached message helpers ─────────────────────────────────────────────

_LIMIT_PREAMBLE = (
    "Your free AI conversation limit has been reached. "
    "Our team would love to help you personally — "
)

_ALL_COLLECTED_MSG = (
    "Thank you! We have all your details. Our support team will contact you shortly. "
    "You can also reach us at support@dhiora.com."
)


def _missing_fields(lead: Lead) -> list[str]:
    missing = []
    if not lead.name:
        missing.append("name")
    if not lead.phone:
        missing.append("phone number")
    if not lead.email:
        missing.append("email address")
    return missing


def _build_limit_message(lead: Lead) -> str:
    missing = _missing_fields(lead)
    if not missing:
        return _ALL_COLLECTED_MSG
    return (
        f"{_LIMIT_PREAMBLE}"
        f"please provide your {', '.join(missing)} and our team will contact you."
    )


# ── Simple regex-based contact extraction (no API cost when limit is hit) ─────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"[\+]?[0-9][\d\s\-\(\)]{8,14}[0-9]")


def _extract_contact_info(message: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (name, phone, email) parsed from a raw message string."""
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None

    email_match = _EMAIL_RE.search(message)
    if email_match:
        email = email_match.group(0).lower()

    phone_match = _PHONE_RE.search(message)
    if phone_match:
        raw_phone = re.sub(r"[\s\-\(\)]", "", phone_match.group(0))
        phone = raw_phone

    # Treat as name if the message looks like a plain name (only letters/spaces, <60 chars)
    stripped = message.strip()
    if (
        not email
        and not phone
        and len(stripped) <= 60
        and re.fullmatch(r"[A-Za-z][A-Za-z\s\.]{1,59}", stripped)
    ):
        name = stripped

    return name, phone, email


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _load_lead(db: AsyncSession, session_id: str) -> Optional[Lead]:
    result = await db.execute(select(Lead).where(Lead.session_id == session_id))
    return result.scalar_one_or_none()


# ── Public functions ──────────────────────────────────────────────────────────

async def chat(
    db: AsyncSession, session_id: Optional[str], user_message: str
) -> dict:
    if not session_id:
        session_id = str(uuid.uuid4())

    lead = await _load_lead(db, session_id)
    if not lead:
        lead = Lead(session_id=session_id, conversation=[], status="new", total_tokens_used=0)
        db.add(lead)
        await db.flush()

    tokens_used: int = lead.total_tokens_used or 0
    limit_reached: bool = tokens_used >= FREE_TOKEN_LIMIT

    conversation = list(lead.conversation or [])
    conversation.append({"role": "user", "content": user_message})

    if limit_reached:
        # Try to extract contact info from the message without calling OpenAI
        ext_name, ext_phone, ext_email = _extract_contact_info(user_message)
        if ext_name and not lead.name:
            lead.name = ext_name[:100]
        if ext_phone and not lead.phone:
            lead.phone = ext_phone[:30]
        if ext_email and not lead.email:
            lead.email = ext_email[:200]

        assistant_reply = _build_limit_message(lead)
        conversation.append({"role": "assistant", "content": assistant_reply})
        lead.conversation = conversation

        if lead.status == "new":
            lead.status = "contacted"

        await db.commit()
        await db.refresh(lead)

        tokens_used = lead.total_tokens_used or 0
        return {
            "session_id": session_id,
            "lead_id": str(lead.id),
            "reply": assistant_reply,
            "lead_captured": bool(lead.name and lead.phone and lead.email),
            "limit_reached": True,
            "tokens_used": tokens_used,
            "tokens_remaining": max(0, FREE_TOKEN_LIMIT - tokens_used),
        }

    # ── Within quota: call OpenAI ─────────────────────────────────────────────
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages.extend(conversation)

    call_tokens = 0
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.5,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        if response.usage:
            call_tokens = response.usage.total_tokens
    except Exception as exc:
        logger.exception("OpenAI chat error: %s", exc)
        parsed = {
            "message": "I'm sorry, I'm having trouble responding right now. Please try again in a moment.",
            "captured_name": None,
            "captured_phone": None,
            "captured_email": None,
        }

    assistant_reply: str = parsed.get("message", "")
    captured_name: Optional[str] = parsed.get("captured_name") or None
    captured_phone: Optional[str] = parsed.get("captured_phone") or None
    captured_email: Optional[str] = parsed.get("captured_email") or None

    conversation.append({"role": "assistant", "content": assistant_reply})
    lead.conversation = conversation

    if captured_name and not lead.name:
        lead.name = captured_name.strip()[:100]
    if captured_phone and not lead.phone:
        lead.phone = captured_phone.strip()[:30]
    if captured_email and not lead.email:
        lead.email = captured_email.strip()[:200]

    lead.total_tokens_used = tokens_used + call_tokens

    if lead.status == "new":
        lead.status = "contacted"

    # If the new total hits the limit, piggyback the limit message
    new_limit_reached = lead.total_tokens_used >= FREE_TOKEN_LIMIT
    if new_limit_reached:
        limit_note = (
            "\n\n---\n⚠️ You've reached the end of your free AI session. "
            "Our team will be happy to continue the conversation — "
            "please share your contact details and we'll reach out to you."
        )
        assistant_reply = assistant_reply + limit_note

    await db.commit()
    await db.refresh(lead)

    final_tokens = lead.total_tokens_used or 0
    return {
        "session_id": session_id,
        "lead_id": str(lead.id),
        "reply": assistant_reply,
        "lead_captured": bool(lead.name and lead.phone and lead.email),
        "limit_reached": new_limit_reached,
        "tokens_used": final_tokens,
        "tokens_remaining": max(0, FREE_TOKEN_LIMIT - final_tokens),
    }


async def submit_contact(
    db: AsyncSession,
    session_id: str,
    name: Optional[str],
    phone: Optional[str],
    email: Optional[str],
) -> dict:
    """Upsert contact info for a lead when the token limit form is submitted."""
    lead = await _load_lead(db, session_id)
    if not lead:
        # Create a minimal lead so the contact info is never lost
        lead = Lead(
            session_id=session_id,
            conversation=[],
            status="contacted",
            total_tokens_used=0,
        )
        db.add(lead)
        await db.flush()

    if name and not lead.name:
        lead.name = name.strip()[:100]
    if phone and not lead.phone:
        lead.phone = phone.strip()[:30]
    if email and not lead.email:
        lead.email = str(email).strip()[:200]

    if lead.status == "new":
        lead.status = "contacted"

    await db.commit()
    await db.refresh(lead)

    missing = _missing_fields(lead)
    all_collected = len(missing) == 0

    if all_collected:
        msg = _ALL_COLLECTED_MSG
    else:
        msg = (
            f"Thanks! We still need your {', '.join(missing)} to complete your details."
        )

    return {
        "session_id": session_id,
        "lead_id": str(lead.id),
        "message": msg,
        "all_collected": all_collected,
        "missing_fields": [f.replace(" address", "").replace(" number", "") for f in missing],
    }
