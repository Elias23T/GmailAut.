from dataclasses import dataclass
from uuid import UUID

from app.shared.domain.entities import TimestampedEntity


@dataclass(kw_only=True)
class Membership(TimestampedEntity):
    tenant_id: UUID
    user_id: UUID
    role: str = "member"
    status: str = "active"
