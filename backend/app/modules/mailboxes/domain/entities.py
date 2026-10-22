from dataclasses import dataclass
from uuid import UUID

from app.shared.domain.entities import TimestampedEntity


@dataclass(kw_only=True)
class Mailbox(TimestampedEntity):
    tenant_id: UUID
    email: str
    display_name: str
    imap_host: str
    imap_port: int = 993
    status: str = "pending"


@dataclass(kw_only=True)
class MailboxCredential(TimestampedEntity):
    mailbox_id: UUID
    username: str
    encrypted_secret: bytes
    key_version: int
