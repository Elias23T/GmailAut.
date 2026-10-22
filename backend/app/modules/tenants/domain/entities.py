from dataclasses import dataclass

from app.shared.domain.entities import TimestampedEntity


@dataclass(kw_only=True)
class Tenant(TimestampedEntity):
    name: str
    slug: str
    status: str = "active"
