"""Tests for AI Classroom board image annotation feature."""

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.ai_classroom import service
from app.core.models import AIImageRegion, AILectureImage, AILectureSession, AILectureChunk
from app.auth.models import User


def _make_tenant_and_lecture(db_session, status="COMPLETED"):
    """Helper: return (tenant_id, lecture_id) — creates rows in DB."""
    tenant_id = uuid.uuid4()
    teacher_id = uuid.uuid4()
    lecture_id = uuid.uuid4()
    return tenant_id, teacher_id, lecture_id


async def _create_lecture(db_session: AsyncSession, status: str = "COMPLETED"):
    """Create a minimal AILectureSession and return it."""
    tenant_id = uuid.uuid4()
    teacher_id = uuid.uuid4()
    lecture = AILectureSession(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        academic_year_id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        section_id=None,
        subject_id=uuid.uuid4(),
        teacher_id=teacher_id,
        title="Test Lecture",
        transcript="Some content",
        status=status,
    )
    db_session.add(lecture)
    await db_session.flush()
    return lecture


async def _create_image_with_regions(
    db_session: AsyncSession,
    lecture: AILectureSession,
    chunk_id=None,
):
    """Create an AILectureImage with two regions and return it."""
    img = AILectureImage(
        id=uuid.uuid4(),
        tenant_id=lecture.tenant_id,
        lecture_id=lecture.id,
        chunk_id=chunk_id,
        image_url="/tmp/test_board.jpg",
        sequence_order=0,
        topic_label="shaft diagram",
    )
    db_session.add(img)
    await db_session.flush()

    for label, color in [("shaft", "#EF9F27"), ("bearing", "#378ADD")]:
        region = AIImageRegion(
            id=uuid.uuid4(),
            lecture_image_id=img.id,
            label=label,
            x=0.1,
            y=0.1,
            w=0.3,
            h=0.2,
            color_hex=color,
            description=f"A {label} component",
        )
        db_session.add(region)
    await db_session.commit()
    return img


# ---------------------------------------------------------------------------
# Test 1 — upload succeeds for COMPLETED lecture, regions extracted
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upload_lecture_image_success(db_session: AsyncSession):
    lecture = await _create_lecture(db_session, status="COMPLETED")

    mock_regions = [
        {"label": "shaft", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2, "description": "shaft part"},
        {"label": "bearing", "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.15, "description": "bearing"},
    ]

    dummy_file_content = b"fake image bytes"

    class FakeUploadFile:
        filename = "board.jpg"

        async def read(self):
            return dummy_file_content

    with patch.object(service, "analyze_board_image", new=AsyncMock(return_value=mock_regions)):
        img = await service.upload_and_analyze_image(
            db=db_session,
            lecture_id=lecture.id,
            image_file=FakeUploadFile(),
            topic_label="shaft diagram",
            chunk_id=None,
            sequence_order=0,
            tenant_id=lecture.tenant_id,
            user_id=lecture.teacher_id,
        )

    assert img is not None
    assert img.lecture_id == lecture.id
    assert img.image_url is not None
    assert len(img.regions) == 2
    labels = {r.label for r in img.regions}
    assert "shaft" in labels
    assert "bearing" in labels


# ---------------------------------------------------------------------------
# Test 2 — upload rejects RECORDING lecture
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upload_image_rejects_active_recording(db_session: AsyncSession):
    from app.core.exceptions import ServiceError

    lecture = await _create_lecture(db_session, status="RECORDING")

    class FakeUploadFile:
        filename = "board.jpg"

        async def read(self):
            return b"fake"

    with pytest.raises(ServiceError) as exc_info:
        await service.upload_and_analyze_image(
            db=db_session,
            lecture_id=lecture.id,
            image_file=FakeUploadFile(),
            topic_label=None,
            chunk_id=None,
            sequence_order=0,
            tenant_id=lecture.tenant_id,
            user_id=lecture.teacher_id,
        )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Test 3 — ask_doubt returns image annotation when image linked to chunk
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_doubt_returns_image_annotation(db_session: AsyncSession):
    from app.core.exceptions import ServiceError
    from app.api.v1.ai_classroom.schemas import DoubtAskRequest

    lecture = await _create_lecture(db_session, status="COMPLETED")

    # Create a chunk
    chunk = AILectureChunk(
        id=uuid.uuid4(),
        tenant_id=lecture.tenant_id,
        lecture_id=lecture.id,
        content="The shaft connects gear A to gear B",
        embedding=[0.0] * 1536,
    )
    db_session.add(chunk)
    await db_session.flush()

    # Create image linked to that chunk
    await _create_image_with_regions(db_session, lecture, chunk_id=chunk.id)

    mock_shaft_region = {"label": "shaft", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2, "description": "shaft part"}

    with (
        patch.object(service, "generate_embedding", new=AsyncMock(return_value=[0.0] * 1536)),
        patch.object(service, "pick_best_region_for_doubt", new=AsyncMock(return_value=mock_shaft_region)),
        patch.object(
            service.client.chat.completions,
            "create",
            new=AsyncMock(
                return_value=type("R", (), {
                    "choices": [type("C", (), {"message": type("M", (), {"content": "The shaft is the rotating rod."})()})()]
                })()
            ),
        ),
    ):
        # Create a fake student user
        student = User(
            id=uuid.uuid4(),
            tenant_id=lecture.tenant_id,
            email="student@test.com",
            hashed_password="x",
            full_name="Student",
            role="STUDENT",
            user_type="student",
            status="ACTIVE",
        )
        db_session.add(student)
        await db_session.flush()

        payload = DoubtAskRequest(lecture_id=lecture.id, question="where is the shaft?")
        chat, ai_message, img_data = await service.ask_doubt(
            db=db_session,
            tenant_id=lecture.tenant_id,
            student_id=student.id,
            payload=payload,
        )

    assert img_data["image_url"] is not None
    assert img_data["highlight_region"] is not None
    assert img_data["highlight_region"].label == "shaft"


# ---------------------------------------------------------------------------
# Test 4 — ask_doubt works fine when no image uploaded
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_doubt_works_without_image(db_session: AsyncSession):
    from app.api.v1.ai_classroom.schemas import DoubtAskRequest

    lecture = await _create_lecture(db_session, status="COMPLETED")

    with (
        patch.object(service, "generate_embedding", new=AsyncMock(return_value=[0.0] * 1536)),
        patch.object(
            service.client.chat.completions,
            "create",
            new=AsyncMock(
                return_value=type("R", (), {
                    "choices": [type("C", (), {"message": type("M", (), {"content": "I don't know."})()})()]
                })()
            ),
        ),
    ):
        student = User(
            id=uuid.uuid4(),
            tenant_id=lecture.tenant_id,
            email="student2@test.com",
            hashed_password="x",
            full_name="Student2",
            role="STUDENT",
            user_type="student",
            status="ACTIVE",
        )
        db_session.add(student)
        await db_session.flush()

        payload = DoubtAskRequest(lecture_id=lecture.id, question="What is Newton's law?")
        chat, ai_message, img_data = await service.ask_doubt(
            db=db_session,
            tenant_id=lecture.tenant_id,
            student_id=student.id,
            payload=payload,
        )

    assert chat is not None
    assert ai_message is not None
    assert img_data["image_url"] is None
    assert img_data["highlight_region"] is None
    assert img_data["all_regions"] is None
