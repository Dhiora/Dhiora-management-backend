"""AI Classroom service with transcription, embedding, RAG, and management chat."""

import asyncio
import io
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, Iterable, List, Optional, Tuple
from uuid import UUID

import openai
from fastapi import HTTPException, UploadFile, status
from openai import AsyncOpenAI
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import CurrentUser
from app.core.config import settings
from app.core.exceptions import ServiceError
from app.core.models import (
    AIDoubtChat,
    AIDoubtMessage,
    AILectureChunk,
    AILectureSession,
    AcademicYear,
    ManagementKnowledgeChunk,
    SchoolClass,
    SchoolSubject,
    Section,
)

from .schemas import (
    AdminDoubtRequest,
    DoubtAskRequest,
    LectureCreate,
    ManagementChatRequest,
    RecordingStartRequest,
    StudentDoubtRequest,
)

client = AsyncOpenAI(api_key=settings.openai_api_key)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into semantic chunks with overlap."""
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        if end >= text_length:
            chunks.append(text[start:].strip())
            break

        # Try to break at sentence boundary
        chunk = text[start:end]
        last_period = chunk.rfind(".")
        last_newline = chunk.rfind("\n")

        if last_period > chunk_size * 0.7 or last_newline > chunk_size * 0.7:
            end = start + max(last_period + 1, last_newline + 1)

        chunks.append(text[start:end].strip())
        start = end - overlap

    return [chunk for chunk in chunks if chunk]


async def transcribe_audio(file: UploadFile) -> str:
    """Transcribe audio file using OpenAI Whisper API."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise ServiceError("Invalid file type. Expected audio file.", status.HTTP_400_BAD_REQUEST)

    try:
        contents = await file.read()
        audio_file = io.BytesIO(contents)
        
        # 🔥 CRITICAL: Set filename - OpenAI uses this to infer format
        if file.filename:
            audio_file.name = file.filename
        else:
            # Infer from content_type or default to webm
            content_type_map = {
                "audio/webm": "audio.webm",
                "audio/mpeg": "audio.mp3",
                "audio/mp3": "audio.mp3",
                "audio/wav": "audio.wav",
                "audio/x-wav": "audio.wav",
                "audio/mp4": "audio.m4a",
                "audio/m4a": "audio.m4a",
            }
            audio_file.name = content_type_map.get(file.content_type, "audio.webm")

        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json"
        )

        return transcription if isinstance(transcription, str) else transcription.text
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Transcription error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)


async def generate_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI text-embedding-3-small."""
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Embedding generation error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Generic management-knowledge indexing helpers (called from CRUD services)
# ---------------------------------------------------------------------------


def _serialize_student_summary(student: "Student") -> str:  # type: ignore[name-defined]
    """
    Turn a student ORM instance into a concise natural-language summary.
    This is an example; extend as needed for your domain.
    """
    parts: List[str] = []
    if getattr(student, "admission_no", None):
        parts.append(f"Admission No: {student.admission_no}")
    parts.append(f"Name: {student.first_name} {getattr(student, 'last_name', '')}".strip())
    if getattr(student, "class_name", None):
        parts.append(f"Class: {student.class_name}")
    if getattr(student, "section_name", None):
        parts.append(f"Section: {student.section_name}")
    if getattr(student, "parent_phone", None):
        parts.append(f"Parent Phone: {student.parent_phone}")
    return ". ".join(parts)


async def index_management_entity(
    db: AsyncSession,
    tenant_id: UUID,
    entity_type: str,
    entity_id: Optional[UUID],
    content: str,
) -> ManagementKnowledgeChunk:
    """
    Create a vectorized knowledge chunk for any management entity.

    - entity_type: high-level domain label, e.g. STUDENT, EMPLOYEE, FEE, GENERAL
    - entity_id: optional source primary key
    - content: natural-language representation to be used in RAG
    """
    if not content:
        raise ServiceError("Cannot index empty content", status.HTTP_400_BAD_REQUEST)

    embedding = await generate_embedding(content)
    chunk = ManagementKnowledgeChunk(
        tenant_id=tenant_id,
        entity_type=entity_type.upper(),
        entity_id=entity_id,
        content=content,
        embedding=embedding,
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    return chunk


async def bulk_index_management_entities(
    db: AsyncSession,
    tenant_id: UUID,
    entity_type: str,
    items: Iterable[Tuple[Optional[UUID], str]],
) -> None:
    """
    Helper to index many entities of the same type at once.

    Each item is (entity_id, content).
    """
    for entity_id, content in items:
        await index_management_entity(db, tenant_id, entity_type, entity_id, content)


# ---------------------------------------------------------------------------
# Organization-wide management chat (role-based, vector-backed, SSE)
# ---------------------------------------------------------------------------


def _resolve_allowed_entity_types(current_user: CurrentUser) -> List[str]:
    """
    Map CurrentUser.permissions to a list of entity types they can query.

    This is a conservative default; extend mappings as your RBAC evolves.
    """
    # Full admins can see all management entities for their tenant
    if current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN"):
        return ["STUDENT", "EMPLOYEE", "FEE", "GENERAL"]

    perms = current_user.permissions or {}
    allowed: List[str] = ["GENERAL"]

    def _has_read(module_key: str) -> bool:
        module_perms = perms.get(module_key) or {}
        return bool(module_perms.get("read") or module_perms.get("READ"))

    if _has_read("students") or _has_read("student"):
        allowed.append("STUDENT")
    if _has_read("employees") or _has_read("employee"):
        allowed.append("EMPLOYEE")
    if _has_read("fees") or _has_read("fee"):
        allowed.append("FEE")

    return allowed


async def management_chat_stream(
    db: AsyncSession,
    current_user: CurrentUser,
    payload: ManagementChatRequest,
) -> AsyncGenerator[dict, None]:
    """
    Single unified chat endpoint for management data.

    - Uses tenant-scoped ManagementKnowledgeChunk pgvector table
    - Enforces role-based access: if top matches are in an entity_type
      the user cannot read, respond with access-denied instead of data
    - Streams answer as SSE-style events: chunk, then done, or a single
      access-denied message.
    """
    tenant_id = current_user.tenant_id
    question = payload.message.strip()
    if not question:
        raise ServiceError("Question cannot be empty", status.HTTP_400_BAD_REQUEST)

    allowed_entity_types = [et.upper() for et in _resolve_allowed_entity_types(current_user)]

    # Embed the question
    q_embedding = await generate_embedding(question)
    embedding_str = "[" + ",".join(map(str, q_embedding)) + "]"

    # Pull top N candidate chunks for this tenant
    stmt = text(
        """
        SELECT id, content, entity_type
        FROM school.management_knowledge_chunks
        WHERE tenant_id = :tenant_id
        ORDER BY embedding <-> (:q_embedding)::vector
        LIMIT 20
        """
    )
    result = await db.execute(
        stmt,
        {
            "tenant_id": str(tenant_id),
            "q_embedding": embedding_str,
        },
    )
    rows = result.fetchall()

    if not rows:
        # No knowledge at all; answer generically
        denial = (
            "I do not have any management data indexed for your organization yet, "
            "so I cannot answer this question."
        )
        yield {"type": "chunk", "content": denial}
        yield {"type": "done"}
        return

    # Separate authorized vs unauthorized chunks
    authorized_contents: List[str] = []
    unauthorized_present = False
    for row in rows:
        entity_type = str(row[2] or "").upper()
        if entity_type and entity_type not in allowed_entity_types:
            unauthorized_present = True
            continue
        authorized_contents.append(row[1])

    if not authorized_contents and unauthorized_present:
        # User is clearly asking about something they don't have rights to see
        denial = (
            "Sorry, you do not have access to view this information for your organization. "
            "Please contact your administrator if you believe this is a mistake."
        )
        yield {"type": "chunk", "content": denial}
        yield {"type": "done"}
        return

    if not authorized_contents:
        # Nothing relevant was found
        no_data = (
            "I could not find any relevant information in the management data I have access to. "
            "Try rephrasing your question or check if the data exists."
        )
        yield {"type": "chunk", "content": no_data}
        yield {"type": "done"}
        return

    context = "\n\n".join(authorized_contents)
    system_prompt = (
        "You are an AI assistant for a school management system. "
        "Use ONLY the provided management data to answer the user's question. "
        "If specific details are not present in the context, say you don't have that data "
        "instead of guessing. Be concise and clear."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Management data:\n\n{context}\n\n\nUser question: {question}",
        },
    ]

    try:
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.2,
            stream=True,
        )
        full_content: List[str] = []
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0 and getattr(chunk.choices[0].delta, "content", None):
                content = chunk.choices[0].delta.content
                full_content.append(content)
                yield {"type": "chunk", "content": content}
        _ = "".join(full_content)
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating management answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)

    # For now we do not persist chat history; this can be added later.
    yield {"type": "done"}


async def create_lecture(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    payload: LectureCreate,
    audio_file: UploadFile,
) -> AILectureSession:
    """Create lecture session with transcription and embeddings."""
    user = await db.get(User, teacher_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("Teacher not found", status.HTTP_404_NOT_FOUND)

    if user.user_type != "employee" and user.role not in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN"):
        raise ServiceError("Only teachers can create lectures", status.HTTP_403_FORBIDDEN)

    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)

    cls = await db.get(SchoolClass, payload.class_id)
    if not cls or cls.tenant_id != tenant_id:
        raise ServiceError("Class not found", status.HTTP_404_NOT_FOUND)

    if payload.section_id:
        from app.core.models.section_model import Section

        sec = await db.get(Section, payload.section_id)
        if not sec or sec.tenant_id != tenant_id or sec.class_id != payload.class_id:
            raise ServiceError("Section not found", status.HTTP_404_NOT_FOUND)

    subj = await db.get(SchoolSubject, payload.subject_id)
    if not subj or subj.tenant_id != tenant_id:
        raise ServiceError("Subject not found", status.HTTP_404_NOT_FOUND)

    transcript = await transcribe_audio(audio_file)

    lecture = AILectureSession(
        tenant_id=tenant_id,
        academic_year_id=payload.academic_year_id,
        class_id=payload.class_id,
        section_id=payload.section_id,
        subject_id=payload.subject_id,
        teacher_id=teacher_id,
        title=payload.title,
        transcript=transcript,
    )

    db.add(lecture)
    await db.flush()

    chunks = chunk_text(transcript)
    for chunk_content in chunks:
        embedding = await generate_embedding(chunk_content)
        chunk = AILectureChunk(
            tenant_id=tenant_id,
            lecture_id=lecture.id,
            content=chunk_content,
            embedding=embedding,
        )
        db.add(chunk)

    await db.commit()
    await db.refresh(lecture)

    # Attach class, subject, and section names for response
    lecture._class_name = cls.name
    lecture._subject_name = subj.name
    lecture._section_name = sec.name if payload.section_id and sec else None

    return lecture


async def ask_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    payload: DoubtAskRequest,
) -> Tuple[AIDoubtChat, AIDoubtMessage]:
    """Answer student doubt using RAG."""
    user = await db.get(User, student_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("Student not found", status.HTTP_404_NOT_FOUND)

    if user.user_type != "student" and user.role not in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN"):
        raise ServiceError("Only students can ask doubts", status.HTTP_403_FORBIDDEN)

    lecture = await db.get(AILectureSession, payload.lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)

    question_embedding = await generate_embedding(payload.question)

    embedding_str = "[" + ",".join(map(str, question_embedding)) + "]"

    stmt = text("""
        SELECT content
        FROM school.ai_lecture_chunks
        WHERE tenant_id = :tenant_id
        AND lecture_id = :lecture_id
        ORDER BY embedding <-> (:question_embedding)::vector
        LIMIT 5
    """)

    result = await db.execute(
        stmt,
        {
            "tenant_id": str(tenant_id),
            "lecture_id": str(payload.lecture_id),
            "question_embedding": embedding_str,
        },
    )

    relevant_chunks = [row[0] for row in result.fetchall()]
    context = "\n\n".join(relevant_chunks)

    system_prompt = """You are an assistant teacher. Answer only from the provided context. 
If the answer is not found in the context, politely say that this topic was not discussed in the lecture."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context from lecture:\n\n{context}\n\n\nStudent question: {payload.question}"},
            ],
            temperature=0.7,
        )

        ai_answer = response.choices[0].message.content
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)

    chat = await db.execute(
        select(AIDoubtChat).where(
            AIDoubtChat.tenant_id == tenant_id,
            AIDoubtChat.student_id == student_id,
            AIDoubtChat.lecture_id == payload.lecture_id,
        )
    )
    chat_obj = chat.scalar_one_or_none()

    if not chat_obj:
        chat_obj = AIDoubtChat(
            tenant_id=tenant_id,
            student_id=student_id,
            lecture_id=payload.lecture_id,
        )
        db.add(chat_obj)
        await db.flush()

    student_message = AIDoubtMessage(
        chat_id=chat_obj.id,
        role="STUDENT",
        message=payload.question,
    )
    db.add(student_message)

    ai_message = AIDoubtMessage(
        chat_id=chat_obj.id,
        role="AI",
        message=ai_answer,
    )
    db.add(ai_message)

    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)

    return chat_obj, ai_message


async def get_chat_history(db: AsyncSession, chat_id: UUID) -> List[dict]:
    """
    Return last 20 messages from AIDoubtMessage for a given chat_id.
    Map role: "STUDENT" → "user", "AI" → "assistant"
    Order by created_at ascending.
    Return as List[dict] with keys: "role", "content"
    """
    stmt = (
        select(AIDoubtMessage)
        .where(AIDoubtMessage.chat_id == chat_id)
        .order_by(AIDoubtMessage.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    # Reverse so chronological order (oldest first)
    ordered = list(reversed(rows))
    return [
        {
            "role": "user" if m.role == "STUDENT" else "assistant",
            "content": m.message,
        }
        for m in ordered
    ]


async def get_similar_chunks(
    db: AsyncSession,
    tenant_id: UUID,
    lecture_id: UUID,
    query: str,
    limit: int = 5,
) -> List[str]:
    """
    Generate embedding for query, run pgvector similarity search on
    school.ai_lecture_chunks, return top `limit` chunk contents as List[str].
    Use same SQL pattern as existing ask_doubt() function.
    """
    embedding = await generate_embedding(query)
    embedding_str = "[" + ",".join(map(str, embedding)) + "]"
    stmt = text("""
        SELECT content
        FROM school.ai_lecture_chunks
        WHERE tenant_id = :tenant_id
        AND lecture_id = :lecture_id
        ORDER BY embedding <-> (:question_embedding)::vector
        LIMIT :limit
    """)
    result = await db.execute(
        stmt,
        {
            "tenant_id": str(tenant_id),
            "lecture_id": str(lecture_id),
            "question_embedding": embedding_str,
            "limit": limit,
        },
    )
    return [row[0] for row in result.fetchall()]


async def _get_or_create_doubt_chat(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    chat_id: Optional[UUID],
) -> AIDoubtChat:
    """Get existing chat by chat_id (with validation) or by (tenant, user, lecture); create if missing."""
    if chat_id:
        chat_obj = await db.get(AIDoubtChat, chat_id)
        if not chat_obj or chat_obj.tenant_id != tenant_id or chat_obj.student_id != user_id or chat_obj.lecture_id != lecture_id:
            raise ServiceError("Chat not found", status.HTTP_404_NOT_FOUND)
        return chat_obj
    chat = await db.execute(
        select(AIDoubtChat).where(
            AIDoubtChat.tenant_id == tenant_id,
            AIDoubtChat.student_id == user_id,
            AIDoubtChat.lecture_id == lecture_id,
        )
    )
    chat_obj = chat.scalar_one_or_none()
    if not chat_obj:
        chat_obj = AIDoubtChat(
            tenant_id=tenant_id,
            student_id=user_id,
            lecture_id=lecture_id,
        )
        db.add(chat_obj)
        await db.flush()
    return chat_obj


async def _handle_basic_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    subject_name: str,
    topic_name: str,
    message: str,
    chat_id: Optional[UUID],
) -> Tuple[AIDoubtChat, AIDoubtMessage]:
    chunks = await get_similar_chunks(db, tenant_id, lecture_id, message, limit=5)
    context = "\n\n".join(chunks)
    system_prompt = (
        f"You are a helpful teacher assistant for {subject_name}, topic: {topic_name}. "
        "Answer the student's question ONLY using the lecture content provided below. "
        f"If the answer is not in the lecture content, respond with: "
        f"'This was not covered in today's lecture on {topic_name}.' "
        "Keep answers clear, simple, and encouraging. Do not go beyond the lecture content."
    )
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Lecture content:\n\n{context}\n\n\nStudent question: {message}"},
            ],
            temperature=0.5,
        )
        ai_answer = response.choices[0].message.content
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)
    return chat_obj, ai_message


async def _handle_pro_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    subject_name: str,
    topic_name: str,
    message: str,
    chat_id: Optional[UUID],
    message_type: str,
) -> Tuple[AIDoubtChat, AIDoubtMessage]:
    chunks = await get_similar_chunks(db, tenant_id, lecture_id, message, limit=5)
    context = "\n\n".join(chunks)
    history = await get_chat_history(db, chat_id) if chat_id else []
    if message_type == "QUESTION":
        system_prompt = (
            f"You are an expert teacher for {subject_name}, topic: {topic_name}. "
            "STEP 1: Answer the student's question clearly using only the lecture content below. "
            "STEP 2: After your answer, always end with ONE comprehension check question. "
            "Format it exactly as: 'Quick check: [your question]' "
            f"Lecture content:\n{context}\n\nRules: "
            "Answer only from lecture content. "
            "Comprehension question must be about what you just explained. Be encouraging and clear."
        )
    else:
        system_prompt = (
            f"You are an expert teacher for {subject_name}, topic: {topic_name}. "
            "The student just answered your comprehension check question. "
            "STEP 1: Evaluate if their answer is correct or not. "
            "STEP 2A: If CORRECT → Praise briefly + ask 'Do you have any other doubts?' "
            "STEP 2B: If WRONG or INCOMPLETE → Gently say it is not quite right; "
            "Re-explain using a DIFFERENT approach (use analogy, real example, or simpler breakdown); "
            "Ask the same comprehension question again but phrased differently. "
            f"Lecture content:\n{context}"
        )
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
        )
        ai_answer = response.choices[0].message.content
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)
    return chat_obj, ai_message


async def _handle_ultra_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    subject_name: str,
    topic_name: str,
    message: str,
    chat_id: Optional[UUID],
    session_stage: str,
) -> Tuple[AIDoubtChat, AIDoubtMessage]:
    chunks = await get_similar_chunks(db, tenant_id, lecture_id, topic_name, limit=5)
    context = "\n\n".join(chunks)
    history_raw = await get_chat_history(db, chat_id) if chat_id else []
    history = history_raw[-10:]  # last 10 messages
    stage_prompts = {
        "START": (
            f"You are an elite IIT-level mentor for {subject_name}. Today's topic: {topic_name}. "
            f"Lecture content:\n{context}\n\nYour task: "
            "Give a sharp 3-line recap of what was taught in the lecture. "
            "Say: 'Now let me show you what IIT toppers know about this that most students miss'. "
            f"Share ONE advanced insight about {topic_name} that goes beyond the lecture. "
            "End with: 'Ready to be challenged at the next level? Reply yes to begin.' "
            "Tone: Confident, exciting, like a mentor who believes in this student."
        ),
        "TEACHING": (
            f"You are an elite IIT-level mentor for {subject_name}, topic: {topic_name}. "
            "The student wants to go deeper. You are in TEACHING mode. "
            "Your task: Teach the advanced version of {topic_name} beyond what the lecture covered. "
            "Show how this topic appears in real IIT exam questions. "
            "Teach one powerful problem-solving technique IIT toppers use for this topic. "
            "End with: 'Now I will give you 3 questions — easy to IIT-hard. Type ready when you are.' "
            f"Lecture base:\n{context}"
        ),
        "CHALLENGING": (
            f"You are an IIT-level examiner for {subject_name}, topic: {topic_name}. "
            "You are in CHALLENGE mode. Ask 3 questions progressively: "
            "Question 1: Board/NCERT level (build confidence); "
            "Question 2: JEE Mains level (push them); "
            "Question 3: JEE Advanced level (real IIT challenge). "
            "Rules for each answer: CORRECT → Praise + explain the deeper insight + move to next question. "
            "WRONG → Identify the exact mistake + explain the correct approach + ask a different question at the same difficulty. "
            "'I don't know' → Teach that concept clearly + ask a simpler version of same question. "
            "Always show: 'Question [X] of 3' at the start of each question. "
            "After all 3 questions are done, tell student to type 'evaluate me'. "
            f"Lecture content:\n{context}"
        ),
        "EVALUATING": (
            f"You are an IIT mentor giving end-of-session feedback for {topic_name}. "
            "Based on this conversation, give the student: "
            "A score: X/10 for this session with one sentence explanation. "
            "What they understood well (be specific, not generic). "
            "One or two gaps they need to work on. "
            "ONE homework problem at IIT level to solve before next class. "
            "A closing motivational message — make it personal to what THEY showed in this session, not a generic 'you can do it'. "
            "This should feel like a real mentor's honest debrief, not a report card."
        ),
    }
    system_prompt = stage_prompts.get(session_stage, stage_prompts["START"])
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    if message:
        messages.append({"role": "user", "content": message})
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.8,
        )
        ai_answer = response.choices[0].message.content
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    chat_obj.session_stage = session_stage
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)
    return chat_obj, ai_message


async def _stream_basic_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    subject_name: str,
    topic_name: str,
    message: str,
    chat_id: Optional[UUID],
) -> AsyncGenerator[dict, None]:
    """Stream BASIC tier doubt response as SSE-style events."""
    chunks = await get_similar_chunks(db, tenant_id, lecture_id, message, limit=5)
    context = "\n\n".join(chunks)
    system_prompt = (
        f"You are a helpful teacher assistant for {subject_name}, topic: {topic_name}. "
        "Answer the student's question ONLY using the lecture content provided below. "
        f"If the answer is not in the lecture content, respond with: "
        f"'This was not covered in today's lecture on {topic_name}.' "
        "Keep answers clear, simple, and encouraging. Do not go beyond the lecture content."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Lecture content:\n\n{context}\n\n\nStudent question: {message}"},
    ]
    try:
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.5,
            stream=True,
        )
        full_content = []
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content.append(content)
                yield {"type": "chunk", "content": content}
        ai_answer = "".join(full_content)
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)
    yield {
        "type": "done",
        "chat_id": str(chat_obj.id),
        "message": {
            "id": str(ai_message.id),
            "chat_id": str(ai_message.chat_id),
            "role": ai_message.role,
            "message": ai_message.message,
            "created_at": ai_message.created_at.isoformat() if ai_message.created_at else None,
        },
    }


async def _stream_pro_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    subject_name: str,
    topic_name: str,
    message: str,
    chat_id: Optional[UUID],
    message_type: str,
) -> AsyncGenerator[dict, None]:
    """Stream PRO tier doubt response as SSE-style events."""
    chunks = await get_similar_chunks(db, tenant_id, lecture_id, message, limit=5)
    context = "\n\n".join(chunks)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    history = await get_chat_history(db, chat_obj.id)
    if message_type == "QUESTION":
        system_prompt = (
            f"You are an expert teacher for {subject_name}, topic: {topic_name}. "
            "STEP 1: Answer the student's question clearly using only the lecture content below. "
            "STEP 2: After your answer, always end with ONE comprehension check question. "
            "Format it exactly as: 'Quick check: [your question]' "
            f"Lecture content:\n{context}\n\nRules: "
            "Answer only from lecture content. "
            "Comprehension question must be about what you just explained. Be encouraging and clear."
        )
    else:
        system_prompt = (
            f"You are an expert teacher for {subject_name}, topic: {topic_name}. "
            "The student just answered your comprehension check question. "
            "STEP 1: Evaluate if their answer is correct or not. "
            "STEP 2A: If CORRECT → Praise briefly + ask 'Do you have any other doubts?' "
            "STEP 2B: If WRONG or INCOMPLETE → Gently say it is not quite right; "
            "Re-explain using a DIFFERENT approach (use analogy, real example, or simpler breakdown); "
            "Ask the same comprehension question again but phrased differently. "
            f"Lecture content:\n{context}"
        )
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    try:
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            stream=True,
        )
        full_content = []
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content.append(content)
                yield {"type": "chunk", "content": content}
        ai_answer = "".join(full_content)
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)
    yield {
        "type": "done",
        "chat_id": str(chat_obj.id),
        "message": {
            "id": str(ai_message.id),
            "chat_id": str(ai_message.chat_id),
            "role": ai_message.role,
            "message": ai_message.message,
            "created_at": ai_message.created_at.isoformat() if ai_message.created_at else None,
        },
    }


async def _stream_ultra_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    subject_name: str,
    topic_name: str,
    message: str,
    chat_id: Optional[UUID],
    session_stage: str,
) -> AsyncGenerator[dict, None]:
    """Stream ULTRA tier doubt response as SSE-style events."""
    chunks = await get_similar_chunks(db, tenant_id, lecture_id, topic_name, limit=5)
    context = "\n\n".join(chunks)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    history_raw = await get_chat_history(db, chat_obj.id)
    history = history_raw[-10:]
    stage_prompts = {
        "START": (
            f"You are an elite IIT-level mentor for {subject_name}. Today's topic: {topic_name}. "
            f"Lecture content:\n{context}\n\nYour task: "
            "Give a sharp 3-line recap of what was taught in the lecture. "
            "Say: 'Now let me show you what IIT toppers know about this that most students miss'. "
            f"Share ONE advanced insight about {topic_name} that goes beyond the lecture. "
            "End with: 'Ready to be challenged at the next level? Reply yes to begin.' "
            "Tone: Confident, exciting, like a mentor who believes in this student."
        ),
        "TEACHING": (
            f"You are an elite IIT-level mentor for {subject_name}, topic: {topic_name}. "
            "The student wants to go deeper. You are in TEACHING mode. "
            "Your task: Teach the advanced version of {topic_name} beyond what the lecture covered. "
            "Show how this topic appears in real IIT exam questions. "
            "Teach one powerful problem-solving technique IIT toppers use for this topic. "
            "End with: 'Now I will give you 3 questions — easy to IIT-hard. Type ready when you are.' "
            f"Lecture base:\n{context}"
        ),
        "CHALLENGING": (
            f"You are an IIT-level examiner for {subject_name}, topic: {topic_name}. "
            "You are in CHALLENGE mode. Ask 3 questions progressively: "
            "Question 1: Board/NCERT level (build confidence); "
            "Question 2: JEE Mains level (push them); "
            "Question 3: JEE Advanced level (real IIT challenge). "
            "Rules for each answer: CORRECT → Praise + explain the deeper insight + move to next question. "
            "WRONG → Identify the exact mistake + explain the correct approach + ask a different question at the same difficulty. "
            "'I don't know' → Teach that concept clearly + ask a simpler version of same question. "
            "Always show: 'Question [X] of 3' at the start of each question. "
            "After all 3 questions are done, tell student to type 'evaluate me'. "
            f"Lecture content:\n{context}"
        ),
        "EVALUATING": (
            f"You are an IIT mentor giving end-of-session feedback for {topic_name}. "
            "Based on this conversation, give the student: "
            "A score: X/10 for this session with one sentence explanation. "
            "What they understood well (be specific, not generic). "
            "One or two gaps they need to work on. "
            "ONE homework problem at IIT level to solve before next class. "
            "A closing motivational message — make it personal to what THEY showed in this session, not a generic 'you can do it'. "
            "This should feel like a real mentor's honest debrief, not a report card."
        ),
    }
    system_prompt = stage_prompts.get(session_stage, stage_prompts["START"])
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    if message:
        messages.append({"role": "user", "content": message})
    try:
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.8,
            stream=True,
        )
        full_content = []
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content.append(content)
                yield {"type": "chunk", "content": content}
        ai_answer = "".join(full_content)
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    chat_obj.session_stage = session_stage
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)
    yield {
        "type": "done",
        "chat_id": str(chat_obj.id),
        "message": {
            "id": str(ai_message.id),
            "chat_id": str(ai_message.chat_id),
            "role": ai_message.role,
            "message": ai_message.message,
            "created_at": ai_message.created_at.isoformat() if ai_message.created_at else None,
        },
    }


async def ask_doubt_student(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    payload: StudentDoubtRequest,
) -> Tuple[AIDoubtChat, AIDoubtMessage]:
    """
    Student doubt endpoint. Auto-routes to BASIC/PRO/ULTRA based on
    student's subscription_plan field on User model.
    """
    user = await db.get(User, student_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("Student not found", status.HTTP_404_NOT_FOUND)
    if user.user_type != "student":
        raise ServiceError("Only students can use this endpoint", status.HTTP_403_FORBIDDEN)
    lecture = await db.get(AILectureSession, payload.lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)
    plan = getattr(user, "subscription_plan", "BASIC")
    if plan not in ("BASIC", "PRO", "ULTRA"):
        plan = "BASIC"
    if plan == "BASIC":
        return await _handle_basic_doubt(
            db, tenant_id, student_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        )
    if plan == "PRO":
        return await _handle_pro_doubt(
            db, tenant_id, student_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
            payload.message_type or "QUESTION",
        )
    return await _handle_ultra_doubt(
        db, tenant_id, student_id, payload.lecture_id,
        payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        payload.session_stage or "START",
    )


async def ask_doubt_student_stream(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: UUID,
    payload: StudentDoubtRequest,
) -> AsyncGenerator[dict, None]:
    """
    Student doubt endpoint (Event Stream). Same validation as ask_doubt_student;
    streams AI response as SSE events: chunk, then done.
    """
    user = await db.get(User, student_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("Student not found", status.HTTP_404_NOT_FOUND)
    if user.user_type != "student":
        raise ServiceError("Only students can use this endpoint", status.HTTP_403_FORBIDDEN)
    lecture = await db.get(AILectureSession, payload.lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)
    plan = getattr(user, "subscription_plan", "BASIC")
    if plan not in ("BASIC", "PRO", "ULTRA"):
        plan = "BASIC"
    if plan == "BASIC":
        async for event in _stream_basic_doubt(
            db, tenant_id, student_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        ):
            yield event
        return
    if plan == "PRO":
        async for event in _stream_pro_doubt(
            db, tenant_id, student_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
            payload.message_type or "QUESTION",
        ):
            yield event
        return
    async for event in _stream_ultra_doubt(
        db, tenant_id, student_id, payload.lecture_id,
        payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        payload.session_stage or "START",
    ):
        yield event


async def ask_doubt_admin(
    db: AsyncSession,
    tenant_id: UUID,
    admin_id: UUID,
    payload: AdminDoubtRequest,
) -> Tuple[AIDoubtChat, AIDoubtMessage]:
    """
    Admin doubt endpoint. Admin explicitly passes tier in request body.
    """
    user = await db.get(User, admin_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("Admin user not found", status.HTTP_404_NOT_FOUND)
    is_admin = user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN") or user.user_type == "employee"
    if not is_admin:
        raise ServiceError("Only admins or employees can use this endpoint", status.HTTP_403_FORBIDDEN)
    lecture = await db.get(AILectureSession, payload.lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)
    logging.getLogger(__name__).info(
        "Admin %s using tier %s for lecture %s", admin_id, payload.tier, payload.lecture_id
    )
    tier = payload.tier
    if tier == "BASIC":
        return await _handle_basic_doubt(
            db, tenant_id, admin_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        )
    if tier == "PRO":
        return await _handle_pro_doubt(
            db, tenant_id, admin_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
            payload.message_type or "QUESTION",
        )
    return await _handle_ultra_doubt(
        db, tenant_id, admin_id, payload.lecture_id,
        payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        payload.session_stage or "START",
    )


async def ask_doubt_admin_stream(
    db: AsyncSession,
    tenant_id: UUID,
    admin_id: UUID,
    payload: AdminDoubtRequest,
) -> AsyncGenerator[dict, None]:
    """
    Admin doubt endpoint (Event Stream). Same validation as ask_doubt_admin;
    streams AI response as SSE events: chunk, then done.
    """
    user = await db.get(User, admin_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("Admin user not found", status.HTTP_404_NOT_FOUND)
    is_admin = user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN") or user.user_type == "employee"
    if not is_admin:
        raise ServiceError("Only admins or employees can use this endpoint", status.HTTP_403_FORBIDDEN)
    lecture = await db.get(AILectureSession, payload.lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)
    logging.getLogger(__name__).info(
        "Admin %s using tier %s for lecture %s (stream)", admin_id, payload.tier, payload.lecture_id
    )
    tier = payload.tier
    if tier == "BASIC":
        async for event in _stream_basic_doubt(
            db, tenant_id, admin_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        ):
            yield event
        return
    if tier == "PRO":
        async for event in _stream_pro_doubt(
            db, tenant_id, admin_id, payload.lecture_id,
            payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
            payload.message_type or "QUESTION",
        ):
            yield event
        return
    async for event in _stream_ultra_doubt(
        db, tenant_id, admin_id, payload.lecture_id,
        payload.subject_name, payload.topic_name, payload.message, payload.chat_id,
        payload.session_stage or "START",
    ):
        yield event


async def get_lecture(
    db: AsyncSession,
    tenant_id: UUID,
    lecture_id: UUID,
) -> Optional[AILectureSession]:
    """Get lecture by ID with tenant check."""
    stmt = (
        select(
            AILectureSession,
            SchoolClass.name.label("class_name"),
            SchoolSubject.name.label("subject_name"),
            Section.name.label("section_name"),
        )
        .join(SchoolClass, AILectureSession.class_id == SchoolClass.id, isouter=True)
        .join(SchoolSubject, AILectureSession.subject_id == SchoolSubject.id, isouter=True)
        .join(Section, AILectureSession.section_id == Section.id, isouter=True)
        .where(AILectureSession.id == lecture_id, AILectureSession.tenant_id == tenant_id)
    )
    
    result = await db.execute(stmt)
    row = result.first()
    
    if not row:
        return None
    
    lecture = row[0]
    lecture._class_name = row.class_name
    lecture._subject_name = row.subject_name
    lecture._section_name = row.section_name
    return lecture


async def list_lectures(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: Optional[UUID] = None,
    class_id: Optional[UUID] = None,
    subject_id: Optional[UUID] = None,
) -> List[AILectureSession]:
    """List lectures with optional filters."""
    stmt = (
        select(
            AILectureSession,
            SchoolClass.name.label("class_name"),
            SchoolSubject.name.label("subject_name"),
            Section.name.label("section_name"),
        )
        .join(SchoolClass, AILectureSession.class_id == SchoolClass.id, isouter=True)
        .join(SchoolSubject, AILectureSession.subject_id == SchoolSubject.id, isouter=True)
        .join(Section, AILectureSession.section_id == Section.id, isouter=True)
        .where(AILectureSession.tenant_id == tenant_id)
    )

    if teacher_id:
        stmt = stmt.where(AILectureSession.teacher_id == teacher_id)
    if class_id:
        stmt = stmt.where(AILectureSession.class_id == class_id)
    if subject_id:
        stmt = stmt.where(AILectureSession.subject_id == subject_id)

    stmt = stmt.order_by(AILectureSession.created_at.desc())

    result = await db.execute(stmt)
    rows = result.all()
    
    # Attach class_name, subject_name, and section_name to lecture objects
    lectures = []
    for row in rows:
        lecture = row[0]
        lecture._class_name = row.class_name
        lecture._subject_name = row.subject_name
        lecture._section_name = row.section_name
        lectures.append(lecture)
    
    return lectures


async def get_doubt_chat(
    db: AsyncSession,
    tenant_id: UUID,
    chat_id: UUID,
    student_id: Optional[UUID] = None,
) -> Optional[AIDoubtChat]:
    """Get doubt chat by ID with tenant check."""
    chat = await db.get(AIDoubtChat, chat_id)
    if not chat or chat.tenant_id != tenant_id:
        return None

    if student_id and chat.student_id != student_id:
        return None

    return chat


async def list_doubt_chats(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: Optional[UUID] = None,
    lecture_id: Optional[UUID] = None,
) -> List[AIDoubtChat]:
    """List doubt chats with optional filters."""
    stmt = select(AIDoubtChat).where(AIDoubtChat.tenant_id == tenant_id)

    if student_id:
        stmt = stmt.where(AIDoubtChat.student_id == student_id)
    if lecture_id:
        stmt = stmt.where(AIDoubtChat.lecture_id == lecture_id)

    stmt = stmt.order_by(AIDoubtChat.created_at.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def start_recording(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    payload: RecordingStartRequest,
) -> AILectureSession:
    """Start a new recording session."""
    user = await db.get(User, teacher_id)
    if not user or user.tenant_id != tenant_id:
        raise ServiceError("Teacher not found", status.HTTP_404_NOT_FOUND)

    if user.user_type != "employee" and user.role not in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN"):
        raise ServiceError("Only teachers can start recordings", status.HTTP_403_FORBIDDEN)

    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Academic year not found", status.HTTP_404_NOT_FOUND)

    cls = await db.get(SchoolClass, payload.class_id)
    if not cls or cls.tenant_id != tenant_id:
        raise ServiceError("Class not found", status.HTTP_404_NOT_FOUND)

    if payload.section_id:
        from app.core.models.section_model import Section

        sec = await db.get(Section, payload.section_id)
        if not sec or sec.tenant_id != tenant_id or sec.class_id != payload.class_id:
            raise ServiceError("Section not found", status.HTTP_404_NOT_FOUND)

    subj = await db.get(SchoolSubject, payload.subject_id)
    if not subj or subj.tenant_id != tenant_id:
        raise ServiceError("Subject not found", status.HTTP_404_NOT_FOUND)

    now = datetime.now(timezone.utc)

    session = AILectureSession(
        tenant_id=tenant_id,
        academic_year_id=payload.academic_year_id,
        class_id=payload.class_id,
        section_id=payload.section_id,
        subject_id=payload.subject_id,
        teacher_id=teacher_id,
        title=payload.title,
        transcript="",
        status="RECORDING",
        recording_started_at=now,
        is_active_recording=True,
        audio_buffer_size_bytes=0,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    import logging
    from app.api.v1.ai_classroom.audio_buffer_manager import buffer_manager

    logger = logging.getLogger(__name__)
    await buffer_manager.initialize(session.id)
    logger.info(f"Recording started for session {session.id}, teacher {teacher_id}")

    return session


async def pause_recording(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    session_id: UUID,
) -> AILectureSession:
    """Pause an active recording session."""
    import logging
    from app.api.v1.ai_classroom.audio_buffer_manager import buffer_manager

    logger = logging.getLogger(__name__)

    session = await db.get(AILectureSession, session_id)
    if not session or session.tenant_id != tenant_id:
        raise ServiceError("Session not found", status.HTTP_404_NOT_FOUND)

    if session.teacher_id != teacher_id:
        raise ServiceError("You do not own this session", status.HTTP_403_FORBIDDEN)

    if session.status != "RECORDING":
        raise ServiceError(f"Cannot pause session with status: {session.status}", status.HTTP_400_BAD_REQUEST)

    now = datetime.now(timezone.utc)
    
    if session.recording_started_at:
        elapsed = (now - session.recording_started_at).total_seconds()
        session.total_recording_seconds = int(session.total_recording_seconds + elapsed)
    
    buffer_size = await buffer_manager.get_size(session_id)
    session.audio_buffer_size_bytes = buffer_size
    
    session.status = "PAUSED"
    session.recording_paused_at = now
    session.is_active_recording = False

    await db.commit()
    await db.refresh(session)

    logger.info(f"Recording paused for session {session_id}, buffer size: {buffer_size} bytes")

    return session


async def resume_recording(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    session_id: UUID,
) -> AILectureSession:
    """Resume a paused recording session."""
    import logging

    logger = logging.getLogger(__name__)

    session = await db.get(AILectureSession, session_id)
    if not session or session.tenant_id != tenant_id:
        raise ServiceError("Session not found", status.HTTP_404_NOT_FOUND)

    if session.teacher_id != teacher_id:
        raise ServiceError("You do not own this session", status.HTTP_403_FORBIDDEN)

    if session.status != "PAUSED":
        raise ServiceError(f"Cannot resume session with status: {session.status}", status.HTTP_400_BAD_REQUEST)

    now = datetime.now(timezone.utc)
    session.status = "RECORDING"
    session.recording_started_at = now
    session.recording_paused_at = None
    session.is_active_recording = True

    await db.commit()
    await db.refresh(session)

    logger.info(f"Recording resumed for session {session_id}")

    return session


async def stop_recording(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    session_id: UUID,
) -> AILectureSession:
    """Stop recording; mark session as STOPPING and let WebSocket finalize audio and start background processing."""
    import logging

    logger = logging.getLogger(__name__)

    session = await db.get(AILectureSession, session_id)
    if not session or session.tenant_id != tenant_id:
        raise ServiceError("Session not found", status.HTTP_404_NOT_FOUND)

    if session.teacher_id != teacher_id:
        raise ServiceError("You do not own this session", status.HTTP_403_FORBIDDEN)

    if session.status not in ("RECORDING", "PAUSED"):
        raise ServiceError(f"Cannot stop session with status: {session.status}", status.HTTP_400_BAD_REQUEST)

    now = datetime.now(timezone.utc)
    if session.recording_started_at:
        if session.recording_paused_at:
            elapsed = (session.recording_paused_at - session.recording_started_at).total_seconds()
            session.total_recording_seconds = int(session.total_recording_seconds + elapsed)
        else:
            elapsed = (now - session.recording_started_at).total_seconds()
            session.total_recording_seconds = int(session.total_recording_seconds + elapsed)

    # Mark as no longer actively recording; WebSocket will flush remaining audio and start processing on disconnect.
    session.is_active_recording = False
    session.status = "STOPPING"

    await db.commit()
    await db.refresh(session)

    logger.info(f"Recording stopped for session {session_id}, status=STOPPING")
    return session




async def get_recording_session(
    db: AsyncSession,
    tenant_id: UUID,
    session_id: UUID,
    teacher_id: Optional[UUID] = None,
) -> Optional[AILectureSession]:
    """Get recording session with tenant and ownership validation."""
    session = await db.get(AILectureSession, session_id)
    if not session or session.tenant_id != tenant_id:
        return None

    if teacher_id and session.teacher_id != teacher_id:
        return None

    return session


async def process_lecture_background(session_id: UUID) -> None:
    """
    Background task: load session, transcribe audio, chunk, embed, then set COMPLETED
    and notify WebSocket. On error set FAILED and notify. Do not block; uses own DB session.
    """
    import os

    from app.core.websocket import connection_manager
    from app.db.session import AsyncSessionLocal

    logger = logging.getLogger(__name__)
    logger.info("Background processing started for session %s", session_id)
    audio_path: Optional[str] = None

    async with AsyncSessionLocal() as db:
        try:
            session = await db.get(AILectureSession, session_id)
            if not session or session.status != "PROCESSING":
                logger.warning("Session %s not found or not PROCESSING, skip background", session_id)
                return

            tenant_id = session.tenant_id
            audio_path = session.audio_file_path
            if not audio_path or not os.path.isfile(audio_path):
                session.status = "FAILED"
                session.processing_stage = "ERROR"
                await db.commit()
                await connection_manager.send_to_channel(
                    connection_manager.channel_for_session(str(session_id)),
                    {
                        "status": "failed",
                        "error": "Audio file not found",
                        "upload_completed": bool(getattr(session, "upload_completed", False)),
                        "processing_stage": "ERROR",
                        "progress": getattr(session, "upload_progress_percent", 0),
                    },
                )
                return

            # At this point we have a valid audio file; notify UI that processing has really started.
            session.processing_stage = "TRANSCRIBING"
            session.upload_progress_percent = max(session.upload_progress_percent or 0, 10)
            await db.commit()
            await connection_manager.send_to_channel(
                connection_manager.channel_for_session(str(session_id)),
                {
                    "status": "processing",
                    "processing_stage": session.processing_stage,
                    "upload_completed": bool(getattr(session, "upload_completed", False)),
                    "progress": session.upload_progress_percent,
                },
            )

            with open(audio_path, "rb") as f:
                audio_file = io.BytesIO(f.read())
            audio_file.name = "lecture.webm"

            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json"
            )
            transcript = transcription if isinstance(transcription, str) else transcription.text
            session.transcript = transcript
            session.processing_stage = "CHUNKING"
            session.upload_progress_percent = max(session.upload_progress_percent or 0, 40)
            await db.commit()
            await connection_manager.send_to_channel(
                connection_manager.channel_for_session(str(session_id)),
                {
                    "status": "processing",
                    "processing_stage": session.processing_stage,
                    "upload_completed": bool(getattr(session, "upload_completed", False)),
                    "progress": session.upload_progress_percent,
                },
            )

            chunks = chunk_text(transcript)
            session.processing_stage = "EMBEDDING"
            session.upload_progress_percent = max(session.upload_progress_percent or 0, 60)
            await db.commit()
            await connection_manager.send_to_channel(
                connection_manager.channel_for_session(str(session_id)),
                {
                    "status": "processing",
                    "processing_stage": session.processing_stage,
                    "upload_completed": bool(getattr(session, "upload_completed", False)),
                    "progress": session.upload_progress_percent,
                },
            )

            total_chunks = len(chunks) or 1
            for idx, chunk_content in enumerate(chunks, start=1):
                embedding = await generate_embedding(chunk_content)
                chunk = AILectureChunk(
                    tenant_id=tenant_id,
                    lecture_id=session.id,
                    content=chunk_content,
                    embedding=embedding,
                )
                db.add(chunk)

                # Gradually increase progress from 60 → 95 during embedding
                progress = 60 + int(35 * idx / total_chunks)
                if progress > session.upload_progress_percent:
                    session.upload_progress_percent = progress
                    await db.commit()
                    # Avoid spamming the channel on every tiny update; only send for meaningful changes
                    if idx == 1 or idx == total_chunks or idx % 5 == 0:
                        await connection_manager.send_to_channel(
                            connection_manager.channel_for_session(str(session_id)),
                            {
                                "status": "processing",
                                "processing_stage": session.processing_stage,
                                "upload_completed": bool(getattr(session, "upload_completed", False)),
                                "progress": session.upload_progress_percent,
                            },
                        )

            session.status = "COMPLETED"
            session.processing_stage = "DONE"
            session.upload_progress_percent = 100
            await db.commit()

            await connection_manager.send_to_channel(
                connection_manager.channel_for_session(str(session_id)),
                {
                    "status": "completed",
                    "processing_stage": session.processing_stage,
                    "upload_completed": bool(getattr(session, "upload_completed", False)),
                    "progress": session.upload_progress_percent,
                },
            )
        except openai.APIError as e:
            logger.exception("OpenAI API error in process_lecture_background")
            try:
                session = await db.get(AILectureSession, session_id)
                if session:
                    session.status = "FAILED"
                    session.processing_stage = "ERROR"
                    await db.commit()
                await connection_manager.send_to_channel(
                    connection_manager.channel_for_session(str(session_id)),
                    {
                        "status": "failed",
                        "error": str(e),
                        "processing_stage": "ERROR",
                        "upload_completed": bool(getattr(session, "upload_completed", False)) if session else False,
                        "progress": getattr(session, "upload_progress_percent", 0) if session else 0,
                    },
                )
            except Exception:
                pass
        except Exception as e:
            logger.exception("Error in process_lecture_background")
            try:
                session = await db.get(AILectureSession, session_id)
                if session:
                    session.status = "FAILED"
                    session.processing_stage = "ERROR"
                    await db.commit()
                await connection_manager.send_to_channel(
                    connection_manager.channel_for_session(str(session_id)),
                    {
                        "status": "failed",
                        "error": str(e),
                        "processing_stage": "ERROR",
                        "upload_completed": bool(getattr(session, "upload_completed", False)) if session else False,
                        "progress": getattr(session, "upload_progress_percent", 0) if session else 0,
                    },
                )
            except Exception:
                pass
        finally:
            if audio_path and os.path.isfile(audio_path):
                try:
                    os.remove(audio_path)
                except OSError as err:
                    logger.warning("Could not remove temp file %s: %s", audio_path, err)


async def update_transcript(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: UUID,
    lecture_id: UUID,
    new_transcript: str,
) -> AILectureSession:
    """Update transcript and regenerate embeddings."""
    import logging

    logger = logging.getLogger(__name__)

    lecture = await db.get(AILectureSession, lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)

    if lecture.teacher_id != teacher_id:
        raise ServiceError("You do not own this lecture", status.HTTP_403_FORBIDDEN)

    if lecture.status != "COMPLETED":
        raise ServiceError(
            f"Cannot edit transcript. Lecture status must be COMPLETED. Current status: {lecture.status}",
            status.HTTP_400_BAD_REQUEST,
        )

    logger.info(f"Updating transcript for lecture {lecture_id}")

    # Delete old chunks
    delete_stmt = delete(AILectureChunk).where(
        AILectureChunk.tenant_id == tenant_id,
        AILectureChunk.lecture_id == lecture_id,
    )
    await db.execute(delete_stmt)
    logger.info(f"Deleted old chunks for lecture {lecture_id}")

    # Update transcript
    lecture.transcript = new_transcript
    await db.flush()

    # Regenerate chunks and embeddings
    if new_transcript:
        logger.info(f"Regenerating chunks and embeddings for lecture {lecture_id}")
        chunks = chunk_text(new_transcript)
        logger.info(f"Generated {len(chunks)} chunks for lecture {lecture_id}")

        for chunk_content in chunks:
            embedding = await generate_embedding(chunk_content)
            chunk = AILectureChunk(
                tenant_id=tenant_id,
                lecture_id=lecture.id,
                content=chunk_content,
                embedding=embedding,
            )
            db.add(chunk)

    await db.commit()
    await db.refresh(lecture)

    logger.info(f"Transcript updated and embeddings regenerated for lecture {lecture_id}")

    return lecture


async def delete_lecture(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    is_admin: bool = False,
) -> bool:
    """Permanently delete a lecture (and its chunks/chats via cascades)."""
    lecture = await db.get(AILectureSession, lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        return False

    if not is_admin and lecture.teacher_id != user_id:
        raise ServiceError("You do not own this lecture", status.HTTP_403_FORBIDDEN)

    await db.delete(lecture)
    await db.commit()
    return True

