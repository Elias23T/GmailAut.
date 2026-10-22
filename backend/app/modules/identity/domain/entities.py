from dataclasses import dataclass

from app.shared.domain.entities import TimestampedEntity


@dataclass(kw_only=True)
class User(TimestampedEntity):
    email: str | None = None
    username: str | None = None
    password_hash: str
    name: str
    status: str = "active"
    is_platform_admin: bool = False
