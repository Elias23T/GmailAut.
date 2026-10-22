from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.shared.domain.entities import Entity, TimestampedEntity, utcnow


@dataclass(kw_only=True)
class OAuthClient(TimestampedEntity):
    client_id: str
    name: str
    redirect_uris: list[str]
    client_secret_hash: str | None = None
    token_endpoint_auth_method: str = 'none'
    status: str = 'active'


@dataclass(kw_only=True)
class AuthorizationCode(Entity):
    code_hash: str
    client_id: UUID
    tenant_id: UUID
    membership_id: UUID
    redirect_uri: str
    resource_uri: str
    code_challenge: str
    expires_at: datetime
    scopes: list[str] = field(default_factory=lambda: ['mail:read'])
    code_challenge_method: str = 'S256'
    created_at: datetime = field(default_factory=utcnow)
    consumed_at: datetime | None = None


@dataclass(kw_only=True)
class OAuthToken(Entity):
    token_hash: str
    token_type: str
    grant_id: UUID
    client_id: UUID
    tenant_id: UUID
    membership_id: UUID
    resource_uri: str
    expires_at: datetime
    scopes: list[str] = field(default_factory=lambda: ['mail:read'])
    created_at: datetime = field(default_factory=utcnow)
    revoked_at: datetime | None = None
