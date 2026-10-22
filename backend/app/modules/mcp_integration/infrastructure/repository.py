from datetime import datetime
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.modules.mcp_integration.domain.entities import OAuthClient, AuthorizationCode, OAuthToken
from app.modules.memberships.domain.entities import Membership


class SQLOAuthRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, entity):
        self.session.add(entity)

    def client(self, client_id: str):
        return self.session.scalar(select(OAuthClient).where(OAuthClient.client_id == client_id).execution_options(populate_existing=True))

    def client_by_id(self, identifier: UUID):
        return self.session.get(OAuthClient, identifier, populate_existing=True)

    def lock_member(self, membership_id: UUID):
        self.session.execute(select(Membership.id).where(Membership.id == membership_id).with_for_update())

    def code(self, digest: str, *, lock=False):
        query = select(AuthorizationCode).where(AuthorizationCode.code_hash == digest).execution_options(populate_existing=True)
        return self.session.scalar(query.with_for_update() if lock else query)

    def token(self, digest: str, *, lock=False):
        query = select(OAuthToken).where(OAuthToken.token_hash == digest).execution_options(populate_existing=True)
        return self.session.scalar(query.with_for_update() if lock else query)

    def revoke_grant(self, grant_id: UUID, now: datetime):
        self.session.execute(update(OAuthToken).where(OAuthToken.grant_id == grant_id, OAuthToken.revoked_at.is_(None)).values(revoked_at=now))

    def revoke_member(self, membership_id: UUID, now: datetime):
        self.lock_member(membership_id)
        self.session.execute(update(OAuthToken).where(OAuthToken.membership_id == membership_id, OAuthToken.revoked_at.is_(None)).values(revoked_at=now))
        self.session.execute(update(AuthorizationCode).where(AuthorizationCode.membership_id == membership_id, AuthorizationCode.consumed_at.is_(None)).values(consumed_at=now))

    def revoke_tenant(self, tenant_id: UUID, now: datetime):
        members = self.session.scalars(select(Membership.id).where(Membership.tenant_id == tenant_id).order_by(Membership.id)).all()
        for membership_id in members:
            self.lock_member(membership_id)
        self.session.execute(update(OAuthToken).where(OAuthToken.tenant_id == tenant_id, OAuthToken.revoked_at.is_(None)).values(revoked_at=now))
        self.session.execute(update(AuthorizationCode).where(AuthorizationCode.tenant_id == tenant_id, AuthorizationCode.consumed_at.is_(None)).values(consumed_at=now))

    def list_tokens(self, tenant_id: UUID):
        return list(self.session.scalars(select(OAuthToken).where(OAuthToken.tenant_id == tenant_id).order_by(OAuthToken.created_at.desc()).limit(1000)))
