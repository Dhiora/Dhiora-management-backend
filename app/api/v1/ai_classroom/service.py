"""AI Classroom service with transcription, embedding, RAG, and management chat."""
import asyncio
import io
import json
import logging
import os
import subprocess
import tempfile
from datetime import date, datetime, timezone
from typing import AsyncGenerator, Iterable, List, Optional, Tuple
from uuid import UUID
import openai
from fastapi import HTTPException, UploadFile, status
from openai import AsyncOpenAI
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.auth.models import User
from app.auth.schemas import CurrentUser
from app.core.config import settings
from app.core.exceptions import ServiceError
from app.core.models import (
    AIDoubtChat,
    AIDoubtMessage,
    AIImageRegion,
    AILectureChunk,
    AILectureImage,
    AILectureSession,
    AITokenUsage,
    AIWhisperUsage,
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
logger = logging.getLogger(__name__)

# ── Model strategy ────────────────────────────────────────────────────────────
MODEL_BASIC   = "gpt-4o-mini"   # cheap, fast — sufficient for simple Q&A
MODEL_PRO     = "gpt-4o"        # full power for interactive teaching
MODEL_ULTRA   = "gpt-4o"        # full power for IIT-level mentoring
MODEL_MGMT    = "gpt-4o-mini"   # management chat — factual retrieval, no deep reasoning needed
MODEL_VISION  = "gpt-4o"        # vision model for board image region extraction

_REGION_COLORS = ["#EF9F27", "#378ADD", "#1D9E75", "#D4537E", "#7F77DD", "#D85A30"]


async def _log_token_usage(
    db: AsyncSession,
    tenant_id: UUID,
    student_id: Optional[UUID],
    chat_id: Optional[UUID],
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Persist token usage record for super admin reporting. Non-critical: swallows errors."""
    try:
        record = AITokenUsage(
            tenant_id=tenant_id,
            student_id=student_id,
            chat_id=chat_id,
            usage_date=date.today(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model_used=model,
        )
        db.add(record)
        # Committed by caller alongside the message; no extra commit needed.
    except Exception as exc:
        logger.warning("_log_token_usage failed (non-critical): %s", exc)

async def _log_whisper_usage(
    db: AsyncSession,
    tenant_id: UUID,
    teacher_id: Optional[UUID],
    lecture_session_id: Optional[UUID],
    duration_seconds: float,
) -> None:
    """Persist Whisper audio duration record for super admin reporting. Non-critical."""
    try:
        if duration_seconds <= 0:
            return
        record = AIWhisperUsage(
            tenant_id=tenant_id,
            teacher_id=teacher_id,
            lecture_session_id=lecture_session_id,
            usage_date=date.today(),
            audio_duration_seconds=duration_seconds,
        )
        db.add(record)
    except Exception as exc:
        logger.warning("_log_whisper_usage failed (non-critical): %s", exc)


_CONTEXT_MAX_CHARS = 2000  # ~500 tokens — covers 3-4 relevant chunks comfortably


def limit_context(chunks: List[str], max_chars: int = _CONTEXT_MAX_CHARS) -> str:
    """Join chunks up to max_chars. Keeps the most relevant (top-ranked) chunks first."""
    result, total = [], 0
    for chunk in chunks:
        if total + len(chunk) > max_chars:
            break
        result.append(chunk)
        total += len(chunk)
    return "\n\n".join(result)


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


def clean_audio(input_path: str) -> str:
    """
    Preprocess audio with FFmpeg: highpass/lowpass/afftdn, then convert to mono 16kHz WAV.
    Returns path to the cleaned .wav file (caller must delete it).
    """
    fd, output_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-af", "highpass=f=200,lowpass=f=3500,afftdn=nf=-25",
            "-ar", "16000",
            "-ac", "1",
            output_path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise ServiceError(
                f"FFmpeg failed: {result.stderr or result.stdout or 'unknown error'}",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return output_path
    except subprocess.TimeoutExpired:
        if os.path.exists(output_path):
            try:
                os.unlink(output_path)
            except OSError:
                pass
        raise ServiceError("FFmpeg timed out", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except FileNotFoundError:
        if os.path.exists(output_path):
            try:
                os.unlink(output_path)
            except OSError:
                pass
        raise ServiceError("FFmpeg not found; install FFmpeg and ensure it is in PATH", status.HTTP_500_INTERNAL_SERVER_ERROR)


MULTILINGUAL_PROMPT = (
    "Transcribe exactly what is spoken. Do not translate to English. "
    "Write the words as they are spoken in the original language."
)

import json as _json
import re
from collections import OrderedDict

_INDIAN_WORD_RE = re.compile(r"[\u0900-\u0D7F]+")  # matches contiguous Indian script sequences

# In-memory LRU cache: word → romanized form
# Grows up to 10,000 entries then evicts oldest — covers virtually all classroom vocabulary
_TRANSLITERATION_CACHE: OrderedDict[str, str] = OrderedDict()
_CACHE_MAX_SIZE = 10_000


def _cache_get(word: str) -> Optional[str]:
    val = _TRANSLITERATION_CACHE.get(word)
    if val is not None:
        _TRANSLITERATION_CACHE.move_to_end(word)  # mark as recently used
    return val


def _cache_set(word: str, romanized: str) -> None:
    if word in _TRANSLITERATION_CACHE:
        _TRANSLITERATION_CACHE.move_to_end(word)
    else:
        if len(_TRANSLITERATION_CACHE) >= _CACHE_MAX_SIZE:
            _TRANSLITERATION_CACHE.popitem(last=False)  # evict oldest
        _TRANSLITERATION_CACHE[word] = romanized


async def romanize_indian_script(text: str) -> str:
    """
    Efficiently romanize only the Indian script words in a transcript.

    Steps:
      1. Extract unique Indian script word sequences (e.g. చేస్తే, వెళుతుంది).
      2. If none found → return text unchanged (zero API cost).
      3. Send ONLY those words to GPT-4o-mini and get a JSON mapping.
      4. Replace each Indian word in the original text with its Roman form.

    Example:
      Input : "Bike sudden ga stop చేస్తే, body forward కి వెళుతుంది"
      Sends : "చేస్తే, కి, వెళుతుంది"  ← only these ~3 words to GPT
      Output: "Bike sudden ga stop chesthe, body forward ki velthundi"
    """
    if not text:
        return text

    # Step 1: find unique Indian script words
    all_matches = _INDIAN_WORD_RE.findall(text)
    if not all_matches:
        return text  # no Indian script — zero API cost

    unique_words = list(dict.fromkeys(all_matches))

    # Step 2: split into cached vs uncached
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for word in unique_words:
        cached = _cache_get(word)
        if cached is not None:
            mapping[word] = cached  # cache hit — free
        else:
            missing.append(word)  # needs GPT

    # Step 3: call GPT-4o-mini ONLY for words not in cache
    if missing:
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a transliterator for Indian languages. "
                            "I will give you a comma-separated list of Indian script words. "
                            "Return a JSON object mapping each word to its phonetic Roman transliteration "
                            "exactly as it sounds (colloquial style, not IAST). "
                            'Example: {"చేస్తే": "chesthe", "కి": "ki", "వెళుతుంది": "velthundi"}'
                        ),
                    },
                    {"role": "user", "content": ", ".join(missing)},
                ],
                temperature=0,
                max_tokens=len(missing) * 15,
                response_format={"type": "json_object"},
            )
            new_mappings: dict = _json.loads(response.choices[0].message.content)
            for original, romanized in new_mappings.items():
                if romanized:
                    _cache_set(original, romanized)   # store in cache for next time
                    mapping[original] = romanized
        except Exception as e:
            logger.warning("Romanization step failed, keeping original transcript: %s", e)

    # Step 4: replace all Indian words (cached + newly fetched)
    result = text
    for original, romanized in mapping.items():
        result = result.replace(original, romanized)
    return result


async def _transcribe_file_path(audio_path: str, filename: str = "audio.webm") -> Tuple[str, float]:
    """Transcribe a single file path. Returns (romanized_text, duration_seconds)."""
    audio_bytes = await asyncio.to_thread(lambda: open(audio_path, "rb").read())
    if not audio_bytes:
        return "", 0.0
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    result = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="verbose_json",
        temperature=0.2,
        prompt=MULTILINGUAL_PROMPT,
    )
    raw = result if isinstance(result, str) else result.text
    duration_seconds = float(getattr(result, "duration", 0.0) or 0.0)
    text = await romanize_indian_script(raw)
    return text, duration_seconds


async def transcribe_in_chunks(audio_path: str, chunk_duration_s: int = 30) -> Tuple[str, float]:
    """
    Split audio into N-second chunks via ffmpeg, transcribe each with Whisper,
    then concatenate. Each chunk uses the tail of the previous transcript as prompt
    for context continuity (especially important for mixed-language content).

    Returns (transcript_text, total_audio_duration_seconds).
    Falls back to single-file transcription if ffmpeg splitting fails.
    """
    import glob
    import shutil

    tmpdir = tempfile.mkdtemp(prefix="lecture_chunks_")
    chunk_pattern = os.path.join(tmpdir, "chunk_%04d.webm")

    try:
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-f", "segment",
            "-segment_time", str(chunk_duration_s),
            "-reset_timestamps", "1",
            "-c", "copy",
            chunk_pattern,
        ]
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=300
        )

        chunk_files = sorted(glob.glob(os.path.join(tmpdir, "chunk_*.webm")))
        if not chunk_files:
            logger.warning("ffmpeg produced no chunks, falling back to full-file transcription")
            return await _transcribe_file_path(audio_path)

        transcript_parts: List[str] = []
        total_duration_seconds: float = 0.0
        for chunk_path in chunk_files:
            chunk_bytes = await asyncio.to_thread(lambda p=chunk_path: open(p, "rb").read())
            if not chunk_bytes:
                continue

            # Use tail of previous text as context prompt for continuity
            prev_tail = " ".join(" ".join(transcript_parts).split()[-50:]) if transcript_parts else ""
            contextual_prompt = (MULTILINGUAL_PROMPT + " " + prev_tail).strip()

            audio_file = io.BytesIO(chunk_bytes)
            audio_file.name = "chunk.webm"
            try:
                result = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    temperature=0.2,
                    prompt=contextual_prompt,
                )
                raw = result if isinstance(result, str) else result.text
                chunk_duration = float(getattr(result, "duration", 0.0) or 0.0)
                total_duration_seconds += chunk_duration
                if raw:
                    romanized = await romanize_indian_script(raw)
                    transcript_parts.append(romanized)
                    logger.info("Chunk %s transcribed: %d chars", os.path.basename(chunk_path), len(romanized))
            except Exception as e:
                logger.warning("Chunk %s transcription failed: %s", chunk_path, e)

        return " ".join(transcript_parts), total_duration_seconds

    except Exception as e:
        logger.warning("Chunked transcription failed (%s), falling back to full-file", e)
        return await _transcribe_file_path(audio_path)
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass


async def transcribe_audio(file: UploadFile) -> Tuple[str, float]:
    """Transcribe audio: save to temp file → send audio directly to Whisper.
    Returns (transcript_text, audio_duration_seconds)."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise ServiceError("Invalid file type. Expected audio file.", status.HTTP_400_BAD_REQUEST)

    content_type_map = {
        "audio/webm": ".webm",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mp4": ".m4a",
        "audio/m4a": ".m4a",
    }
    suffix = content_type_map.get(file.content_type, ".webm")
    if file.filename and "." in file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower()

    temp_input_path = None

    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            temp_input_path = tmp.name

        # Do not call clean_audio(); send original audio to Whisper as-is.
        with open(temp_input_path, "rb") as f:
            audio_file = io.BytesIO(f.read())
        audio_file.name = file.filename or f"audio{suffix}"

        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            temperature=0.2,
            response_format="verbose_json",
            prompt=MULTILINGUAL_PROMPT,
        )
        raw_transcript = transcription if isinstance(transcription, str) else transcription.text
        duration_seconds = float(getattr(transcription, "duration", 0.0) or 0.0)
        logger.info("Whisper raw transcript (upload endpoint): %s", raw_transcript)
        text = await romanize_indian_script(raw_transcript)
        return text, duration_seconds
    except ServiceError:
        raise
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Transcription error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            try:
                os.unlink(temp_input_path)
            except OSError:
                pass


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


async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts in a single API call (much faster than sequential calls)."""
    if not texts:
        return []
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        # API guarantees ordering by index
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Embedding generation error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)

async def analyze_board_image(image_url: str) -> List[dict]:
    """
    Send a board/whiteboard image to GPT-4o vision.
    Returns a list of named regions with normalized coordinates (0.0 to 1.0).
    Never raises — returns [] on any error.
    """
    try:
        response = await client.chat.completions.create(
            model=MODEL_VISION,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert at analyzing educational diagrams, machine drawings, "
                        "math problems, and whiteboard photos. Your job is to identify and locate "
                        "every distinct labeled component or region in the image."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Analyze this image carefully. Identify every labeled part, component, "
                                "symbol, or region visible. For each one return a JSON array with objects: "
                                '{ "label": string, "x": float, "y": float, "w": float, "h": float, "description": string } '
                                "where x, y, w, h are fractions of the total image size (0.0 to 1.0). "
                                "x and y are the TOP-LEFT corner. w and h are width and height. "
                                "Keep labels short (1-3 words). Return ONLY the JSON array, no other text."
                            ),
                        },
                    ],
                },
            ],
            max_tokens=1000,
        )
        raw = response.choices[0].message.content or "[]"
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]
        regions = json.loads(raw)
        if not isinstance(regions, list):
            return []
        cleaned = []
        for item in regions:
            if not isinstance(item, dict):
                continue
            if not all(k in item for k in ("label", "x", "y", "w", "h")):
                continue
            cleaned.append({
                "label": str(item["label"]),
                "x": max(0.0, min(1.0, float(item["x"]))),
                "y": max(0.0, min(1.0, float(item["y"]))),
                "w": max(0.0, min(1.0, float(item["w"]))),
                "h": max(0.0, min(1.0, float(item["h"]))),
                "description": str(item.get("description", "")),
            })
        return cleaned
    except Exception as e:
        logger.warning("analyze_board_image failed: %s", e)
        return []


async def pick_best_region_for_doubt(question: str, regions: List[dict]) -> Optional[dict]:
    """
    Given a student's doubt question and a list of regions, ask GPT-4o-mini to pick
    the single region most relevant to the question.
    Returns None if no match or on error.
    """
    if not regions:
        return None
    try:
        response = await client.chat.completions.create(
            model=MODEL_BASIC,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant for students. Given a question and a list "
                        "of labeled diagram regions, pick the ONE region that best answers or "
                        "is most relevant to the question."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\nRegions: {json.dumps(regions)}\n\n"
                        "Return ONLY the JSON object of the single best matching region. "
                        "If no region is relevant, return null."
                    ),
                },
            ],
            max_tokens=300,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.lower() == "null" or not raw:
            return None
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]
        result = json.loads(raw)
        if isinstance(result, dict) and "label" in result:
            return result
        return None
    except Exception as e:
        logger.warning("pick_best_region_for_doubt failed: %s", e)
        return None


async def upload_and_analyze_images_bulk(
    db: AsyncSession,
    lecture_id: UUID,
    image_files: List[UploadFile],
    tenant_id: UUID,
    user_id: UUID,
) -> List["AILectureImage"]:
    """
    Bulk-upload board images and analyze all with GPT-4o vision in parallel.
    S3 uploads and vision calls run concurrently; DB writes are sequential.
    Returns list of AILectureImage ordered by sequence_order.
    """
    from app.core.s3 import upload_image_to_s3

    if not image_files:
        raise ServiceError("No image files provided", status.HTTP_400_BAD_REQUEST)

    lecture = await db.get(AILectureSession, lecture_id)
    if not lecture or lecture.tenant_id != tenant_id:
        raise ServiceError("Lecture not found", status.HTTP_404_NOT_FOUND)

    active_statuses = {"RECORDING", "PAUSED", "PROCESSING", "STOPPING"}
    if lecture.status in active_statuses:
        raise ServiceError(
            f"Cannot upload images while lecture is in {lecture.status} state",
            status.HTTP_400_BAD_REQUEST,
        )

    # Find current max sequence_order so new images continue from there
    existing_count_result = await db.execute(
        select(AILectureImage.sequence_order)
        .where(
            AILectureImage.lecture_id == lecture_id,
            AILectureImage.tenant_id == tenant_id,
        )
        .order_by(AILectureImage.sequence_order.desc())
        .limit(1)
    )
    row = existing_count_result.scalar_one_or_none()
    base_order = (row + 1) if row is not None else 0

    # Step 1: read all file contents into memory
    file_data = []
    for f in image_files:
        contents = await f.read()
        file_data.append((f.filename or "image.jpg", contents))

    # Step 2: upload all files to S3 in parallel
    s3_tasks = [
        upload_image_to_s3(
            content=contents,
            filename=filename,
            tenant_id=str(tenant_id),
            lecture_id=str(lecture_id),
        )
        for filename, contents in file_data
    ]
    image_urls = await asyncio.gather(*s3_tasks)

    # Step 3: run GPT-4o vision on all images in parallel
    vision_tasks = [analyze_board_image(url) for url in image_urls]
    all_regions_data = await asyncio.gather(*vision_tasks)

    # Step 4: write all DB records sequentially (single session)
    created_images = []
    for idx, (image_url, regions_data) in enumerate(zip(image_urls, all_regions_data)):
        lecture_image = AILectureImage(
            tenant_id=tenant_id,
            lecture_id=lecture_id,
            chunk_id=None,
            image_url=image_url,
            sequence_order=base_order + idx,
            topic_label=None,
        )
        db.add(lecture_image)
        await db.flush()

        for r_idx, region in enumerate(regions_data):
            color = _REGION_COLORS[r_idx % len(_REGION_COLORS)]
            db.add(AIImageRegion(
                lecture_image_id=lecture_image.id,
                label=region["label"],
                x=region["x"],
                y=region["y"],
                w=region["w"],
                h=region["h"],
                color_hex=color,
                description=region.get("description"),
            ))

        created_images.append(lecture_image)

    await db.commit()

    # Reload all with regions eagerly
    ids = [img.id for img in created_images]
    result = await db.execute(
        select(AILectureImage)
        .where(AILectureImage.id.in_(ids))
        .options(selectinload(AILectureImage.regions))
        .order_by(AILectureImage.sequence_order)
    )
    return list(result.scalars().all())


async def _get_lecture_image_for_doubt(
    db: AsyncSession,
    tenant_id: UUID,
    lecture_id: UUID,
    chunk_ids: Optional[List[UUID]] = None,
) -> Optional["AILectureImage"]:
    """
    Find the best image for a doubt query.
    First tries images linked to specific chunks, then falls back to any lecture image.
    """
    if chunk_ids:
        result = await db.execute(
            select(AILectureImage)
            .where(
                AILectureImage.lecture_id == lecture_id,
                AILectureImage.tenant_id == tenant_id,
                AILectureImage.chunk_id.in_(chunk_ids),
            )
            .options(selectinload(AILectureImage.regions))
            .order_by(AILectureImage.sequence_order)
            .limit(1)
        )
        img = result.scalar_one_or_none()
        if img:
            return img

    result = await db.execute(
        select(AILectureImage)
        .where(
            AILectureImage.lecture_id == lecture_id,
            AILectureImage.tenant_id == tenant_id,
        )
        .options(selectinload(AILectureImage.regions))
        .order_by(AILectureImage.sequence_order)
        .limit(1)
    )
    return result.scalar_one_or_none()


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
            model=MODEL_MGMT,
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

    transcript, whisper_duration_s = await transcribe_audio(audio_file)

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

    # Log Whisper usage for this upload transcription
    await _log_whisper_usage(db, tenant_id, teacher_id, lecture.id, whisper_duration_s)

    chunks = chunk_text(transcript)
    if chunks:
        embeddings = await generate_embeddings_batch(chunks)
        for chunk_content, embedding in zip(chunks, embeddings):
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
) -> Tuple[AIDoubtChat, AIDoubtMessage, dict]:
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
            model=MODEL_BASIC,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context from lecture:\n\n{context}\n\n\nStudent question: {payload.question}"},
            ],
            temperature=0.7,
        )

        ai_answer = response.choices[0].message.content
        _usage = response.usage
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

    if _usage:
        await _log_token_usage(
            db, tenant_id, student_id, chat_obj.id,
            MODEL_BASIC, _usage.prompt_tokens, _usage.completion_tokens,
        )

    await db.commit()
    await db.refresh(chat_obj)
    await db.refresh(ai_message)

    # --- Image annotation lookup (non-critical) ---
    image_url = None
    highlight_region = None
    all_regions = None
    try:
        # Fetch chunk IDs for same query (reuse computed embedding_str)
        chunk_id_result = await db.execute(
            text("""
                SELECT id FROM school.ai_lecture_chunks
                WHERE tenant_id = :tenant_id AND lecture_id = :lecture_id
                ORDER BY embedding <-> (:question_embedding)::vector
                LIMIT 5
            """),
            {
                "tenant_id": str(tenant_id),
                "lecture_id": str(payload.lecture_id),
                "question_embedding": embedding_str,
            },
        )
        chunk_ids = [row[0] for row in chunk_id_result.fetchall()]
        lecture_image = await _get_lecture_image_for_doubt(
            db, tenant_id, payload.lecture_id, chunk_ids=chunk_ids
        )
        if lecture_image and lecture_image.regions:
            image_url = lecture_image.image_url
            regions_list = [
                {
                    "id": str(r.id),
                    "label": r.label,
                    "x": r.x, "y": r.y, "w": r.w, "h": r.h,
                    "color_hex": r.color_hex or "#EF9F27",
                    "description": r.description,
                }
                for r in lecture_image.regions
            ]
            all_regions = lecture_image.regions
            best = await pick_best_region_for_doubt(
                question=payload.question, regions=regions_list
            )
            if best:
                highlight_region = next(
                    (r for r in lecture_image.regions if r.label.lower() == best.get("label", "").lower()),
                    lecture_image.regions[0],
                )
    except Exception as e:
        logger.warning("Image annotation lookup failed in ask_doubt: %s", e)

    return chat_obj, ai_message, {"image_url": image_url, "highlight_region": highlight_region, "all_regions": all_regions}


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


_INDIAN_LANGUAGE_SUBJECTS = {
    "telugu": "Telugu",
    "hindi": "Hindi",
    "kannada": "Kannada",
    "tamil": "Tamil",
    "malayalam": "Malayalam",
    "marathi": "Marathi",
    "bengali": "Bengali",
    "urdu": "Urdu",
    "sanskrit": "Sanskrit",
    "punjabi": "Punjabi",
}


def _language_instruction(subject_name: str) -> str:
    """Return a reply-language instruction based on subject name."""
    subject_lower = subject_name.lower()
    for key, lang in _INDIAN_LANGUAGE_SUBJECTS.items():
        if key in subject_lower:
            return (
                f"IMPORTANT: This is a {lang} language subject. "
                f"Reply entirely in {lang} using Roman/phonetic script only (no native script). "
                f"Write {lang} words as they sound in Roman letters, exactly like the lecture content style."
            )
    return ""  # English or other subjects — no special instruction


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
    context = limit_context(chunks)
    lang_instruction = _language_instruction(subject_name)
    system_prompt = (
        f"You are a helpful teacher assistant for {subject_name}, topic: {topic_name}. "
        "Answer the student's question ONLY using the lecture content provided below. "
        f"If the answer is not in the lecture content, respond with: "
        f"'This was not covered in today's lecture on {topic_name}.' "
        "Keep answers clear, simple, and encouraging. Do not go beyond the lecture content. "
        + (lang_instruction if lang_instruction else "")
    )
    try:
        response = await client.chat.completions.create(
            model=MODEL_BASIC,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Lecture content:\n\n{context}\n\n\nStudent question: {message}"},
            ],
            temperature=0.5,
        )
        ai_answer = response.choices[0].message.content
        _usage = response.usage
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    if _usage:
        await _log_token_usage(
            db, tenant_id, user_id, chat_obj.id,
            MODEL_BASIC, _usage.prompt_tokens, _usage.completion_tokens,
        )
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
    context = limit_context(chunks)
    history = await get_chat_history(db, chat_id) if chat_id else []
    lang_instruction = _language_instruction(subject_name)
    if message_type == "QUESTION":
        system_prompt = (
            f"You are an expert teacher for {subject_name}, topic: {topic_name}. "
            "STEP 1: Answer the student's question clearly using only the lecture content below. "
            "STEP 2: After your answer, always end with ONE comprehension check question. "
            "Format it exactly as: 'Quick check: [your question]' "
            f"Lecture content:\n{context}\n\nRules: "
            "Answer only from lecture content. "
            "Comprehension question must be about what you just explained. Be encouraging and clear. "
            + (lang_instruction if lang_instruction else "")
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
            f"Lecture content:\n{context} "
            + (lang_instruction if lang_instruction else "")
        )
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    try:
        response = await client.chat.completions.create(
            model=MODEL_PRO,
            messages=messages,
            temperature=0.7,
        )
        ai_answer = response.choices[0].message.content
        _usage = response.usage
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    if _usage:
        await _log_token_usage(
            db, tenant_id, user_id, chat_obj.id,
            MODEL_PRO, _usage.prompt_tokens, _usage.completion_tokens,
        )
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
    context = limit_context(chunks)
    history_raw = await get_chat_history(db, chat_id) if chat_id else []
    history = history_raw[-10:]  # last 10 messages
    lang_instruction = _language_instruction(subject_name)
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
    if lang_instruction:
        system_prompt += " " + lang_instruction
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    if message:
        messages.append({"role": "user", "content": message})
    try:
        response = await client.chat.completions.create(
            model=MODEL_ULTRA,
            messages=messages,
            temperature=0.8,
        )
        ai_answer = response.choices[0].message.content
        _usage = response.usage
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
    if _usage:
        await _log_token_usage(
            db, tenant_id, user_id, chat_obj.id,
            MODEL_ULTRA, _usage.prompt_tokens, _usage.completion_tokens,
        )
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
    context = limit_context(chunks)

    # Emit image annotation event before text streaming (non-critical)
    try:
        lecture_image = await _get_lecture_image_for_doubt(db, tenant_id, lecture_id)
        if lecture_image and lecture_image.regions:
            regions_list = [
                {"id": str(r.id), "label": r.label, "x": r.x, "y": r.y,
                 "w": r.w, "h": r.h, "color_hex": r.color_hex or "#EF9F27", "description": r.description}
                for r in lecture_image.regions
            ]
            best = await pick_best_region_for_doubt(question=message, regions=regions_list)
            yield {
                "type": "image_annotation",
                "image_url": lecture_image.image_url,
                "highlight_region": best,
                "all_regions": regions_list,
            }
    except Exception as e:
        logger.warning("Image annotation SSE lookup failed (basic): %s", e)
    lang_instruction = _language_instruction(subject_name)
    system_prompt = (
        f"You are a helpful teacher assistant for {subject_name}, topic: {topic_name}. "
        "Answer the student's question ONLY using the lecture content provided below. "
        f"If the answer is not in the lecture content, respond with: "
        f"'This was not covered in today's lecture on {topic_name}.' "
        "Keep answers clear, simple, and encouraging. Do not go beyond the lecture content. "
        + (lang_instruction if lang_instruction else "")
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Lecture content:\n\n{context}\n\n\nStudent question: {message}"},
    ]
    try:
        stream = await client.chat.completions.create(
            model=MODEL_BASIC,
            messages=messages,
            temperature=0.5,
            stream=True,
            stream_options={"include_usage": True},
        )
        full_content = []
        _stream_usage = None
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content.append(content)
                yield {"type": "chunk", "content": content}
            if getattr(chunk, "usage", None):
                _stream_usage = chunk.usage
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
    if _stream_usage:
        await _log_token_usage(
            db, tenant_id, user_id, chat_obj.id,
            MODEL_BASIC, _stream_usage.prompt_tokens, _stream_usage.completion_tokens,
        )
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
    context = limit_context(chunks)

    # Emit image annotation event before text streaming (non-critical)
    try:
        lecture_image = await _get_lecture_image_for_doubt(db, tenant_id, lecture_id)
        if lecture_image and lecture_image.regions:
            regions_list = [
                {"id": str(r.id), "label": r.label, "x": r.x, "y": r.y,
                 "w": r.w, "h": r.h, "color_hex": r.color_hex or "#EF9F27", "description": r.description}
                for r in lecture_image.regions
            ]
            best = await pick_best_region_for_doubt(question=message, regions=regions_list)
            yield {
                "type": "image_annotation",
                "image_url": lecture_image.image_url,
                "highlight_region": best,
                "all_regions": regions_list,
            }
    except Exception as e:
        logger.warning("Image annotation SSE lookup failed (pro): %s", e)

    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    history = await get_chat_history(db, chat_obj.id)
    lang_instruction = _language_instruction(subject_name)
    if message_type == "QUESTION":
        system_prompt = (
            f"You are an expert teacher for {subject_name}, topic: {topic_name}. "
            "STEP 1: Answer the student's question clearly using only the lecture content below. "
            "STEP 2: After your answer, always end with ONE comprehension check question. "
            "Format it exactly as: 'Quick check: [your question]' "
            f"Lecture content:\n{context}\n\nRules: "
            "Answer only from lecture content. "
            "Comprehension question must be about what you just explained. Be encouraging and clear. "
            + (lang_instruction if lang_instruction else "")
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
            f"Lecture content:\n{context} "
            + (lang_instruction if lang_instruction else "")
        )
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    try:
        stream = await client.chat.completions.create(
            model=MODEL_PRO,
            messages=messages,
            temperature=0.7,
            stream=True,
            stream_options={"include_usage": True},
        )
        full_content = []
        _stream_usage = None
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content.append(content)
                yield {"type": "chunk", "content": content}
            if getattr(chunk, "usage", None):
                _stream_usage = chunk.usage
        ai_answer = "".join(full_content)
    except openai.APIError as e:
        raise ServiceError(f"OpenAI API error: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        raise ServiceError(f"Error generating answer: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
    student_message = AIDoubtMessage(chat_id=chat_obj.id, role="STUDENT", message=message)
    db.add(student_message)
    ai_message = AIDoubtMessage(chat_id=chat_obj.id, role="AI", message=ai_answer)
    db.add(ai_message)
    if _stream_usage:
        await _log_token_usage(
            db, tenant_id, user_id, chat_obj.id,
            MODEL_PRO, _stream_usage.prompt_tokens, _stream_usage.completion_tokens,
        )
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
    context = limit_context(chunks)

    # Emit image annotation event before text streaming (non-critical)
    try:
        lecture_image = await _get_lecture_image_for_doubt(db, tenant_id, lecture_id)
        if lecture_image and lecture_image.regions:
            regions_list = [
                {"id": str(r.id), "label": r.label, "x": r.x, "y": r.y,
                 "w": r.w, "h": r.h, "color_hex": r.color_hex or "#EF9F27", "description": r.description}
                for r in lecture_image.regions
            ]
            best = await pick_best_region_for_doubt(question=message, regions=regions_list)
            yield {
                "type": "image_annotation",
                "image_url": lecture_image.image_url,
                "highlight_region": best,
                "all_regions": regions_list,
            }
    except Exception as e:
        logger.warning("Image annotation SSE lookup failed (ultra): %s", e)

    chat_obj = await _get_or_create_doubt_chat(db, tenant_id, user_id, lecture_id, chat_id)
    history_raw = await get_chat_history(db, chat_obj.id)
    history = history_raw[-10:]
    lang_instruction = _language_instruction(subject_name)
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
    if lang_instruction:
        system_prompt += " " + lang_instruction
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    if message:
        messages.append({"role": "user", "content": message})
    try:
        stream = await client.chat.completions.create(
            model=MODEL_ULTRA,
            messages=messages,
            temperature=0.8,
            stream=True,
            stream_options={"include_usage": True},
        )
        full_content = []
        _stream_usage = None
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content.append(content)
                yield {"type": "chunk", "content": content}
            if getattr(chunk, "usage", None):
                _stream_usage = chunk.usage
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
    if _stream_usage:
        await _log_token_usage(
            db, tenant_id, user_id, chat_obj.id,
            MODEL_ULTRA, _stream_usage.prompt_tokens, _stream_usage.completion_tokens,
        )
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


async def list_lecture_images(
    db: AsyncSession,
    tenant_id: UUID,
    lecture_id: UUID,
) -> List["AILectureImage"]:
    """Return all board images for a lecture ordered by sequence_order."""
    result = await db.execute(
        select(AILectureImage)
        .where(
            AILectureImage.lecture_id == lecture_id,
            AILectureImage.tenant_id == tenant_id,
        )
        .options(selectinload(AILectureImage.regions))
        .order_by(AILectureImage.sequence_order)
    )
    return list(result.scalars().all())


async def get_lecture_image(
    db: AsyncSession,
    tenant_id: UUID,
    lecture_id: UUID,
    image_id: UUID,
) -> Optional["AILectureImage"]:
    """Return a single lecture image with regions, or None if not found / tenant mismatch."""
    result = await db.execute(
        select(AILectureImage)
        .where(
            AILectureImage.id == image_id,
            AILectureImage.lecture_id == lecture_id,
            AILectureImage.tenant_id == tenant_id,
        )
        .options(selectinload(AILectureImage.regions))
    )
    return result.scalar_one_or_none()


async def delete_lecture_image(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    lecture_id: UUID,
    image_id: UUID,
    is_admin: bool = False,
) -> bool:
    """Delete a lecture image (and cascade its regions). Returns True if deleted, False if not found."""
    result = await db.execute(
        select(AILectureImage).where(
            AILectureImage.id == image_id,
            AILectureImage.lecture_id == lecture_id,
            AILectureImage.tenant_id == tenant_id,
        )
    )
    img = result.scalar_one_or_none()
    if not img:
        return False

    lecture = await db.get(AILectureSession, lecture_id)
    if not is_admin and lecture and lecture.teacher_id != user_id:
        raise ServiceError("Permission denied", status.HTTP_403_FORBIDDEN)

    # Delete from S3 (non-blocking, errors are logged not raised)
    from app.core.s3 import delete_image_from_s3
    await delete_image_from_s3(img.image_url)

    await db.delete(img)
    await db.commit()
    return True


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
    await buffer_manager.initialize(
        session.id,
        target_chunk_bytes=5 * 1024 * 1024,  # 5MB default; overridden by WebSocket handler
        overlap_bytes=0,
        max_buffer_size_bytes=5 * 1024 * 1024,
    )
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
    """Stop recording; mark session as STOPPING and let WebSocket finalize audio and start background processing.
    Idempotent: if already STOPPING, PROCESSING, COMPLETED, or FAILED, return current session without error.
    """
    import logging

    logger = logging.getLogger(__name__)

    session = await db.get(AILectureSession, session_id)
    if not session or session.tenant_id != tenant_id:
        raise ServiceError("Session not found", status.HTTP_404_NOT_FOUND)

    if session.teacher_id != teacher_id:
        raise ServiceError("You do not own this session", status.HTTP_403_FORBIDDEN)

    # If stop is called when the session is already stopping/processing/completed/failed,
    # just return the current state instead of raising. This makes the endpoint idempotent
    # and avoids errors on double-click or late stop calls.
    if session.status in ("STOPPING", "PROCESSING", "COMPLETED", "FAILED"):
        logger.info(
            "Stop called for session %s with status %s; returning current state",
            session_id,
            session.status,
        )
        return session

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

            if not os.path.isfile(audio_path) or os.path.getsize(audio_path) == 0:
                session.status = "FAILED"
                session.processing_stage = "ERROR"
                await db.commit()
                await connection_manager.send_to_channel(
                    connection_manager.channel_for_session(str(session_id)),
                    {"status": "failed", "error": "Audio file is empty — no audio was recorded.", "processing_stage": "ERROR", "progress": 0},
                )
                return

            # Chunked transcription: 30s slices → faster + cheaper + real-time feel
            transcript, whisper_duration_s = await transcribe_in_chunks(audio_path, chunk_duration_s=30)
            logger.info("Chunked transcript (recording pipeline): %d chars, %.1fs audio", len(transcript), whisper_duration_s)
            # Log Whisper usage for this recording transcription
            await _log_whisper_usage(db, tenant_id, session.teacher_id, session_id, whisper_duration_s)
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

            # Generate all embeddings in a single batch API call instead of one-per-chunk
            chunk_embeddings = await generate_embeddings_batch(chunks)
            for chunk_content, embedding in zip(chunks, chunk_embeddings):
                chunk = AILectureChunk(
                    tenant_id=tenant_id,
                    lecture_id=session.id,
                    content=chunk_content,
                    embedding=embedding,
                )
                db.add(chunk)

            session.upload_progress_percent = 95
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

        embeddings = await generate_embeddings_batch(chunks)
        for chunk_content, embedding in zip(chunks, embeddings):
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

