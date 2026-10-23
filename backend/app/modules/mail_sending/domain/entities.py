from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.shared.domain.entities import TimestampedEntity


@dataclass(kw_only=True)
class OutgoingMessage(TimestampedEntity):
    tenant_id: UUID
    mailbox_id: UUID
    membership_id: UUID
    encrypted_payload: bytes | None
    key_version: int
    payload_hash: str
    message_id: str
    expires_at: datetime
    status: str = 'prepared'
    sent_at: datetime | None = None


class DeliveryFailure(Exception):
    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain
