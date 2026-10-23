from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.tenants.domain.entities import Tenant
from app.modules.memberships.domain.entities import Membership


class SQLTenantRepository:
    def __init__(self, session: Session):
        self.session = session

    def all(self) -> list[Tenant]:
        return list(self.session.scalars(select(Tenant).order_by(Tenant.id)))

    def get(self, tenant_id: UUID) -> Tenant | None:
        return self.session.get(Tenant, tenant_id, populate_existing=True)

    def lock(self, tenant_id: UUID) -> None:
        # FOR NO KEY UPDATE serializa cambios de estado sin bloquear las
        # comprobaciones FK de operaciones OAuth que terminan en otra sesion.
        self.session.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update(key_share=True))

    def by_slug(self, slug: str) -> Tenant | None:
        return self.session.scalar(select(Tenant).where(Tenant.slug == slug))

    def for_user(self, user_id: UUID, *, include_inactive: bool = False) -> list[Tenant]:
        query = select(Tenant).join(Membership, Membership.tenant_id == Tenant.id).where(
            Membership.user_id == user_id, Membership.status == 'active')
        if not include_inactive:
            query = query.where(Tenant.status == 'active')
        return list(self.session.scalars(query.order_by(Tenant.created_at).execution_options(populate_existing=True)))

    def add(self, tenant: Tenant) -> None:
        self.session.add(tenant)

    def remove(self, tenant: Tenant) -> None:
        self.session.delete(tenant)
