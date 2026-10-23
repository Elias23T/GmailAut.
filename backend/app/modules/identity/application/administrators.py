from app.modules.audit.application.service import record
from app.modules.identity.application.account_retirement import retire_account
from app.modules.authorization.application.service import AuthorizationService
from app.modules.identity.application.administrator_access import attach_administrator
from app.modules.identity.domain.entities import User
from app.shared.domain.errors import Conflict, Forbidden, NotFound, InvalidInput
from app.shared.domain.entities import utcnow


class AdministratorAdministration:
    def __init__(self, uow, passwords):
        self.uow, self.passwords = uow, passwords

    def list(self, actor):
        AuthorizationService(self.uow).administrator(actor)
        return self.uow.users.administrators()

    def create(self, actor, name, username, password, email=None):
        self.uow.users.lock_administration()
        AuthorizationService(self.uow).administrator(actor)
        if self.uow.users.by_login(username):
            raise Conflict('Ese nombre de usuario ya está en uso. Elige otro para el administrador.')
        if email and self.uow.users.by_email(email):
            raise Conflict('Ya existe una cuenta con ese correo. Usa un correo diferente para el administrador.')
        user = User(name=name, username=username, email=email.lower() if email else None,
                    password_hash=self.passwords.hash(password), is_platform_admin=True)
        self.uow.users.add(user)
        self.uow.flush()
        attach_administrator(self.uow, user)
        record(self.uow, actor, 'administrator.create')
        self.uow.commit()
        return user

    def _administrator(self, user_id):
        user = self.uow.users.get(user_id)
        if not user or not user.is_platform_admin or user.deleted_at is not None:
            raise NotFound('Administrador no disponible.')
        return user

    def _revoke_connections(self, user):
        for member in self.uow.memberships.all_for_user(user.id):
            self.uow.oauth.revoke_member(member.id, utcnow())

    def update(self, actor, user_id, changes):
        self.uow.users.lock_administration()
        AuthorizationService(self.uow).administrator(actor)
        user = self._administrator(user_id)
        if 'username' in changes:
            existing = self.uow.users.by_login(changes['username'])
            if existing and existing.id != user.id:
                raise Conflict('Ese nombre de usuario ya está en uso. Elige otro para el administrador.')
        if changes.get('email'):
            changes['email'] = changes['email'].lower()
            existing = self.uow.users.by_email(changes['email'])
            if existing and existing.id != user.id:
                raise Conflict('Ya existe una cuenta con ese correo. Usa un correo diferente para el administrador.')
        if not changes.get('username', user.username) and not changes.get('email', user.email):
            raise InvalidInput('La cuenta debe conservar un usuario o un correo para iniciar sesión.')
        credential_change = any(key in changes and changes[key] != getattr(user, key) for key in ('username', 'email')) or 'password' in changes
        for key in ('name', 'username', 'email'):
            if key in changes:
                setattr(user, key, changes[key])
        if 'password' in changes:
            user.password_hash = self.passwords.hash(changes['password'])
        if credential_change:
            user.auth_version += 1
            self._revoke_connections(user)
        record(self.uow, actor, 'administrator.update')
        self.uow.commit()
        return user

    def delete(self, actor, user_id):
        self.uow.users.lock_administration()
        AuthorizationService(self.uow).administrator(actor)
        user = self._administrator(user_id)
        if user.id == actor.user_id:
            raise Forbidden('No puedes eliminar tu propia cuenta desde esta sesión.')
        if user.status != 'disabled':
            raise Conflict('No se puede eliminar un administrador activo. Primero desactiva su cuenta y vuelve a intentar.')
        # Retirar el acceso conservando las referencias de auditoria y de los
        # permisos que esta persona concedio. Sus identificadores quedan libres.
        retire_account(self.uow, self.passwords, self.uow.oauth, user)
        record(self.uow, actor, 'administrator.delete')
        self.uow.commit()

    def status(self, actor, user_id, status):
        self.uow.users.lock_administration()
        AuthorizationService(self.uow).administrator(actor)
        user = self._administrator(user_id)
        if user.status == status:
            return user
        if status == 'disabled':
            if sum(admin.status == 'active' for admin in self.uow.users.administrators()) <= 1:
                raise Conflict('No se puede desactivar al último administrador activo. Crea y comprueba otra cuenta administradora primero.')
            if user.id == actor.user_id:
                raise Forbidden('No puedes desactivar tu propia cuenta desde esta sesión. Otro administrador puede hacerlo después de iniciar sesión con su cuenta.')
            # Una reactivacion posterior no recupera sesiones de antes de la baja.
            user.auth_version += 1
            self._revoke_connections(user)
        user.status = status
        record(self.uow, actor, 'administrator.activate' if status == 'active' else 'administrator.deactivate')
        self.uow.commit()
        return user
