from uuid import UUID, uuid4
from app.modules.tenants.domain.entities import Tenant
from app.modules.memberships.domain.entities import Membership
from app.modules.authorization.application.service import AuthorizationService
from app.modules.audit.application.service import record
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor, utcnow
from app.shared.domain.errors import Conflict, NotFound


class TenantService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.authorization = AuthorizationService(uow)

    def create(self, actor: Actor, name: str, slug: str | None = None) -> Tenant:
        self.authorization.administrator(actor)
        if slug is not None and self.uow.tenants.by_slug(slug):
            raise Conflict('Ese identificador de empresa ya está en uso.')
        tenant_id = uuid4()
        tenant = Tenant(id=tenant_id, name=name.strip(), slug=slug or f'empresa-{tenant_id.hex}')
        self.uow.tenants.add(tenant)
        self.uow.flush()
        self.uow.memberships.add(Membership(tenant_id=tenant.id, user_id=actor.user_id, role='owner'))
        record(self.uow, actor, 'tenant.create', tenant_id=tenant.id)
        self.uow.commit()
        return tenant

    def list(self, actor: Actor) -> list[dict]:
        self.authorization.administrator(actor)
        return [self.view(actor, tenant) for tenant in self.uow.tenants.for_user(actor.user_id, include_inactive=True)]

    def view(self, actor: Actor, tenant: Tenant) -> dict:
        member = self.uow.memberships.for_user(tenant.id, actor.user_id)
        return {'id': tenant.id, 'name': tenant.name, 'slug': tenant.slug, 'status': tenant.status,
                'created_at': tenant.created_at, 'membership_id': member.id}

    def _manage(self, actor: Actor, tenant_id: UUID) -> Tenant:
        self.authorization.administrator(actor)
        self.uow.tenants.lock(tenant_id)
        tenant = self.uow.tenants.get(tenant_id)
        membership = self.uow.memberships.for_user(tenant_id, actor.user_id)
        if not tenant or not membership or membership.status != 'active':
            raise NotFound('No se encontró la empresa o no tienes acceso para administrarla.')
        return tenant

    def update(self, actor: Actor, tenant_id: UUID, changes: dict) -> Tenant:
        tenant = self._manage(actor, tenant_id)
        if 'slug' in changes:
            duplicate = self.uow.tenants.by_slug(changes['slug'])
            if duplicate and duplicate.id != tenant.id:
                raise Conflict('No se puede guardar: otra empresa ya utiliza ese identificador. Elige uno diferente.')
            tenant.slug = changes['slug']
        if 'name' in changes:
            tenant.name = changes['name'].strip()
        record(self.uow, actor, 'tenant.update', tenant_id=tenant_id)
        self.uow.commit()
        return tenant

    def change_status(self, actor: Actor, tenant_id: UUID, status: str) -> Tenant:
        tenant = self._manage(actor, tenant_id)
        if tenant.status != status:
            tenant.status = status
            if status == 'disabled':
                self.uow.oauth.revoke_tenant(tenant_id, utcnow())
            record(self.uow, actor, 'tenant.activate' if status == 'active' else 'tenant.deactivate', tenant_id=tenant_id)
            self.uow.commit()
        return tenant

    def delete(self, actor: Actor, tenant_id: UUID) -> None:
        tenant = self._manage(actor, tenant_id)
        if tenant.status != 'disabled':
            state = 'activa' if tenant.status == 'active' else 'suspendida'
            record(self.uow, actor, 'tenant.delete', tenant_id=tenant_id, outcome='denied')
            self.uow.commit()
            raise Conflict(f'No se puede eliminar la empresa «{tenant.name}» porque está {state}. Primero desactívala y vuelve a intentar la eliminación.')
        self.uow.tenants.remove(tenant)
        self.uow.flush()  # PostgreSQL elimina los datos dependientes en la misma transaccion.
        record(self.uow, actor, 'tenant.delete')  # Evento global: la empresa ya no existe.
        self.uow.commit()
