from dataclasses import dataclass
from datetime import datetime

from app.shared.domain.entities import TimestampedEntity


@dataclass(kw_only=True)
class User(TimestampedEntity):
    email: str | None = None
    username: str | None = None
    password_hash: str
    name: str
    status: str = "active"
    is_platform_admin: bool = False
    auth_version: int = 1
    deleted_at: datetime | None = None

    @property
    def credential_stamp(self) -> str:
        return self.password_hash + ':' + (self.username or '') + ':' + str(self.auth_version)
