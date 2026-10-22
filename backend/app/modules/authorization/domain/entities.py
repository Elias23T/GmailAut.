from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.shared.domain.entities import Entity, utcnow


@dataclass(kw_only=True)
class MailboxGrant(Entity):
    tenant_id: UUID
    membership_id: UUID
    mailbox_id: UUID
    granted_by_membership_id: UUID | None = None
    created_at: datetime = field(default_factory=utcnow)
