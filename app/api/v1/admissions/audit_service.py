"""
Audit logging for admission and student state changes. Call on every state change.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AuditLog


async def log_audit(
    db: AsyncSession,
    tenant_id: UUID,
    entity_type: str,
    entity_id: UUID,
    action: str,
    *,
    track: Optional[str] = None,
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    performed_by: Optional[UUID] = None,
    performed_by_role: Optional[str] = None,
    remarks: Optional[str] = None,
) -> None:
    """Append one audit log entry. Caller must commit."""
    entry = AuditLog(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        track=track,
        from_status=from_status,
        to_status=to_status,
        action=action,
        performed_by=performed_by,
        performed_by_role=performed_by_role,
        remarks=remarks,
        timestamp=datetime.utcnow(),
    )
    db.add(entry)
