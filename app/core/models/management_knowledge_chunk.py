"""Management Knowledge Chunk models for organization-wide RAG."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class ManagementKnowledgeChunk(Base):
    """Chunk of structured management data (students, employees, fees, etc.) with embedding."""

    __tablename__ = "management_knowledge_chunks"
    __table_args__ = (
        Index("idx_mgmt_chunks_tenant_id", "tenant_id"),
        Index("idx_mgmt_chunks_entity_type", "entity_type"),
        {"schema": "school"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # High-level domain type, e.g. STUDENT, EMPLOYEE, FEE, GENERAL
    entity_type = Column(String(50), nullable=False, index=True)

    # Optional source entity identifier (from various tables; no direct FK)
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Natural-language representation of the entity / facts
    content = Column(Text, nullable=False)

    # Embedding for vector search
    embedding = Column(Vector(1536), nullable=False)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

