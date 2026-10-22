from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.shared.domain.entities import Entity, utcnow


@dataclass(kw_only=True)
class AuditEvent(Entity):
    action: str
    outcome: str
    request_id: UUID
    source: str
    tenant_id: UUID | None = None
    actor_user_id: UUID | None = None
    mailbox_id: UUID | None = None
    created_at: datetime = field(default_factory=utcnow)
