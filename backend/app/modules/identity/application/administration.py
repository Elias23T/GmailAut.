from uuid import UUID
from app.modules.identity.domain.entities import User
from app.modules.identity.application.account_retirement import retire_account
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
            if not user.is_platform_admin and user.deleted_at is None:
                clients.append({'id': user.id, 'name': user.name, 'email': user.email, 'username': user.username,
                                'status': user.status, 'membership_id': membership.id})
        return clients

    def create(self, actor, tenant_id, name, email, password, username=None):
        AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
        existing = self.uow.users.by_email(email)
        if existing:
            if existing.is_platform_admin:
                raise Conflict('Ese correo pertenece al administrador y no puede agregarse como cliente.')
            if self.uow.memberships.for_user(tenant_id, existing.id):
                raise Conflict('Este cliente ya está vinculado a esta empresa. Cierra el formulario y pulsa Actualizar para verlo en la lista.')
            raise Conflict('Ya existe una cuenta con ese correo. Usa Vincular cliente existente para agregarla a esta empresa conservando su contraseña.')
        if username and (existing := self.uow.users.by_login(username)):
            if existing.is_platform_admin:
                raise Conflict('Ese nombre de usuario pertenece a un administrador. Elige otro para el cliente.')
            memberships = self.uow.memberships.all_for_user(existing.id)
            location = 'sin empresa' if not memberships else 'vinculada a una empresa'
            raise Conflict(f'El usuario «{username}» ya pertenece a una cuenta {location}. Búscalo en el listado de Clientes para vincularla o, si está suspendida, eliminarla.')
        user = User(name=name, email=email.lower(), username=username, password_hash=self.passwords.hash(password))
        self.uow.users.add(user)
        self.uow.flush()
        membership = Membership(tenant_id=tenant_id, user_id=user.id, role='member')
        self.uow.memberships.add(membership)
        record(self.uow, actor, 'client.create', tenant_id=tenant_id)
        self.uow.commit()
        return next(client for client in self.list(actor, tenant_id) if client['id'] == user.id)

    def available(self, actor, tenant_id):
        AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
        return [{'id': user.id, 'name': user.name, 'email': user.email, 'username': user.username, 'status': user.status}
                for user in self.uow.users.available_clients(tenant_id)]

    def all(self, actor):
        AuthorizationService(self.uow).administrator(actor)
        companies = {tenant.id: tenant for tenant in self.uow.tenants.all()}
        return [{'id': user.id, 'name': user.name, 'username': user.username, 'email': user.email,
            'status': user.status, 'companies': [
                {'id': member.tenant_id, 'name': companies[member.tenant_id].name,
                 'status': companies[member.tenant_id].status}
                for member in self.uow.memberships.all_for_user(user.id) if member.tenant_id in companies
            ]} for user in self.uow.users.all_clients()]

    def _client(self, user_id):
        user = self.uow.users.get(user_id)
        if not user or user.deleted_at is not None:
            raise NotFound('Cliente no disponible.')
        if user.is_platform_admin:
            raise Forbidden('La cuenta del administrador no se modifica desde clientes.')
        return user

    def delete(self, actor, user_id):
        self.uow.users.lock_administration()
        AuthorizationService(self.uow).administrator(actor)
        user = self._client(user_id)
        if user.status != 'disabled':
            raise Conflict('No se puede eliminar un cliente habilitado. Primero suspende su acceso y vuelve a intentar.')
        retire_account(self.uow, self.passwords, self.oauth, user)
        record(self.uow, actor, 'client.delete')
        self.uow.commit()

    def delete_disabled(self, actor, user_ids):
        self.uow.users.lock_administration()
        AuthorizationService(self.uow).administrator(actor)
        requested = set(user_ids)
        clients = [user for user in self.uow.users.all_clients() if user.id in requested]
        # Validar toda la selección antes de retirar ninguna cuenta.
        if not requested or len(clients) != len(requested) or any(user.status != 'disabled' for user in clients):
            raise Conflict('El listado cambió: algún cliente fue activado o eliminado. No se eliminó ninguna cuenta. Actualiza el listado y vuelve a confirmar los clientes suspendidos.')
        for user in clients:
            retire_account(self.uow, self.passwords, self.oauth, user)
            record(self.uow, actor, 'client.delete')
        self.uow.commit()
        return {'deleted_count': len(clients)}

    def credentials(self, actor, tenant_id, user_id, username, password=None):
        self.uow.users.lock_administration()
        if tenant_id is None:
            AuthorizationService(self.uow).administrator(actor)
        else:
            AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
            if not self.uow.memberships.for_user(tenant_id, user_id):
                raise NotFound('Cliente no disponible en esta empresa.')
        user = self._client(user_id)
        existing = self.uow.users.by_login(username)
        if existing and existing.id != user.id:
            raise Conflict('Ese nombre de usuario ya está en uso. Elige otro para el cliente.')
        if user.username != username or password is not None:
            user.username = username
            if password is not None:
                user.password_hash = self.passwords.hash(password)
            # La cuenta es compartida entre empresas; exige autorizar de nuevo en todas.
            for member in sorted(self.uow.memberships.all_for_user(user.id), key=lambda member: str(member.id)):
                self.oauth.revoke_member(member.id, utcnow())
            record(self.uow, actor, 'client.credentials', tenant_id=tenant_id)
            self.uow.commit()
        if tenant_id is not None:
            return next(client for client in self.list(actor, tenant_id) if client['id'] == user.id)
        return {'id': user.id, 'name': user.name, 'email': user.email, 'username': user.username, 'status': user.status}

    def status(self, actor, tenant_id: UUID | None, user_id: UUID, status: str):
        self.uow.users.lock_administration()
        if tenant_id is None:
            AuthorizationService(self.uow).administrator(actor)
        else:
            AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
            if not self.uow.memberships.for_user(tenant_id, user_id):
                raise NotFound('Cliente no disponible en esta empresa.')
        user = self._client(user_id)
        if user.status == status:
            return
        user.status = status
        # Suspender una cuenta revoca todas sus conexiones, incluso en otras empresas.
        if status == 'disabled':
            user.auth_version += 1
            for member in self.uow.memberships.all_for_user(user_id):
                self.oauth.revoke_member(member.id, utcnow())
        record(self.uow, actor, 'client.' + ('suspend' if status == 'disabled' else 'activate'), tenant_id=tenant_id)
        self.uow.commit()

    def link(self, actor, tenant_id, email):
        AuthorizationService(self.uow).member(actor, tenant_id, admin=True)
        user = self.uow.users.by_email(email)
        if not user or user.is_platform_admin or user.deleted_at is not None:
            raise NotFound('No existe un cliente con ese correo.')
        if not self.uow.memberships.for_user(tenant_id, user.id):
            self.uow.memberships.add(Membership(tenant_id=tenant_id, user_id=user.id, role='member'))
            record(self.uow, actor, 'client.link', tenant_id=tenant_id)
            self.uow.commit()
        return next(client for client in self.list(actor, tenant_id) if client['id'] == user.id)
