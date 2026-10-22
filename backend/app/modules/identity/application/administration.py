from uuid import UUID
from app.modules.identity.domain.entities import User
from app.modules.memberships.domain.entities import Membership
from app.modules.audit.application.service import record
from app.modules.authorization.application.service import AuthorizationService
from app.shared.domain.errors import Conflict, NotFound, Forbidden
from app.shared.domain.entities import utcnow


class ClientAdministration:
    def __init__(self, uow, passwords, oauth):
        self.uow, self.passwords, self.oauth = uow, passwords, oauth

    def list(self, actor, tenant_id):
        AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
        clients = []
        for membership in self.uow.memberships.list(tenant_id):
            user = self.uow.users.get(membership.user_id)
            if not user.is_platform_admin:
                clients.append({'id': user.id, 'name': user.name, 'email': user.email,
                                'status': user.status, 'membership_id': membership.id})
        return clients

    def create(self, actor, tenant_id, name, email, password):
        AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
        if self.uow.users.by_email(email):
            raise Conflict('Ya existe una cuenta con ese correo.')
        user = User(name=name, email=email.lower(), password_hash=self.passwords.hash(password))
        self.uow.users.add(user)
        self.uow.flush()
        membership = Membership(tenant_id=tenant_id, user_id=user.id, role='member')
        self.uow.memberships.add(membership)
        record(self.uow, actor, 'client.create', tenant_id=tenant_id)
        self.uow.commit()
        return next(client for client in self.list(actor, tenant_id) if client['id'] == user.id)

    def status(self, actor, tenant_id: UUID, user_id: UUID, status: str):
        AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
        user = self.uow.users.get(user_id)
        membership = self.uow.memberships.for_user(tenant_id, user_id)
        if not user or not membership:
            raise NotFound('Cliente no disponible en esta empresa.')
        if user.is_platform_admin:
            raise Forbidden('La cuenta del administrador no se modifica desde clientes.')
        user.status = status
        # Suspender una cuenta revoca todas sus conexiones, incluso en otras empresas.
        if status == 'disabled':
            for member in self.uow.memberships.all_for_user(user_id):
                self.oauth.revoke_member(member.id, utcnow())
        record(self.uow, actor, 'client.' + ('suspend' if status == 'disabled' else 'activate'), tenant_id=tenant_id)
        self.uow.commit()

    def link(self, actor, tenant_id, email):
        AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
        user = self.uow.users.by_email(email)
        if not user or user.is_platform_admin:
            raise NotFound('No existe un cliente con ese correo.')
        if not self.uow.memberships.for_user(tenant_id, user.id):
            self.uow.memberships.add(Membership(tenant_id=tenant_id, user_id=user.id, role='member'))
            record(self.uow, actor, 'client.link', tenant_id=tenant_id)
            self.uow.commit()
        return next(client for client in self.list(actor, tenant_id) if client['id'] == user.id)
