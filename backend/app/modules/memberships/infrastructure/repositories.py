from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.memberships.domain.entities import Membership


class SQLMembershipRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, tenant_id: UUID, membership_id: UUID) -> Membership | None:
        return self.session.scalar(select(Membership).where(Membership.id == membership_id, Membership.tenant_id == tenant_id).execution_options(populate_existing=True))

    def for_user(self, tenant_id: UUID, user_id: UUID) -> Membership | None:
        return self.session.scalar(select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id).execution_options(populate_existing=True))

    def list(self, tenant_id: UUID) -> list[Membership]:
        return list(self.session.scalars(select(Membership).where(Membership.tenant_id == tenant_id).order_by(Membership.created_at).execution_options(populate_existing=True)))

    def add(self, membership: Membership) -> None:
        self.session.add(membership)

    def all_for_user(self, user_id: UUID) -> list[Membership]:
        return list(self.session.scalars(select(Membership).where(Membership.user_id == user_id).order_by(Membership.id)))
