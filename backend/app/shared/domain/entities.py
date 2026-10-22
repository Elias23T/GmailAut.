from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(kw_only=True)
class Entity:
    id: UUID = field(default_factory=uuid4)


@dataclass(kw_only=True)
class TimestampedEntity(Entity):
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    request_id: UUID
    source: str = "rest"
