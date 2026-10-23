from uuid import UUID

from app.modules.audit.application.service import record
from app.modules.authorization.domain.entities import MailboxGrant
from app.modules.mailboxes.domain.entities import Mailbox
from app.modules.memberships.domain.entities import Membership
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor
from app.shared.domain.errors import Forbidden, NotFound, Unauthorized


class AuthorizationService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    def administrator(self, actor: Actor):
        user = self.uow.users.get(actor.user_id)
        if not user or user.status != 'active':
            raise Unauthorized('La cuenta no está disponible.')
        if not user.is_platform_admin:
            raise Forbidden('Solo el administrador de la plataforma puede gestionar empresas.')
        return user

    def member(self, actor: Actor, tenant_id: UUID, *, admin: bool = False) -> Membership:
        user = self.uow.users.get(actor.user_id)
        if not user or user.status != 'active':
            raise Unauthorized('La cuenta no está disponible.')
        membership = self.uow.memberships.for_user(tenant_id, actor.user_id)
        tenant = self.uow.tenants.get(tenant_id) if membership else None
        if not membership or membership.status != 'active' or not tenant or tenant.status != 'active':
            record(self.uow, actor, 'authorization.tenant', outcome='denied')
            self.uow.commit()
            raise NotFound('Empresa no disponible.')
        if admin and not user.is_platform_admin:
            record(self.uow, actor, 'authorization.admin', tenant_id=tenant_id, outcome='denied')
            self.uow.commit()
            raise Forbidden('Esta operación requiere administrar la empresa.')
        return membership

    def mailbox(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, *, require_active: bool = True) -> Mailbox:
        membership = self.member(actor, tenant_id)
        mailbox = self.uow.mailboxes.get(tenant_id, mailbox_id)
        if not mailbox:
            raise NotFound('Buzón no disponible.')
        if not self.uow.grants.get(tenant_id, membership.id, mailbox_id):
            record(self.uow, actor, 'authorization.mailbox', tenant_id=tenant_id, mailbox_id=mailbox_id, outcome='denied')
            self.uow.commit()
            raise Forbidden('No tienes autorización para leer este buzón.')
        if mailbox.status == 'disabled' or (require_active and mailbox.status != 'active'):
            raise Forbidden('El buzón debe estar activo para consultar sus correos.')
        return mailbox

    def grant(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, membership_id: UUID) -> MailboxGrant:
        manager = self.member(actor, tenant_id, admin=True)
        mailbox = self.uow.mailboxes.get(tenant_id, mailbox_id)
        member = self.uow.memberships.get(tenant_id, membership_id)
        if not mailbox or not member or member.status != 'active':
            raise NotFound('Buzón o miembro no disponible en esta empresa.')
        grant = self.uow.grants.get(tenant_id, membership_id, mailbox_id)
        if not grant:
            grant = MailboxGrant(tenant_id=tenant_id, membership_id=membership_id, mailbox_id=mailbox_id, granted_by_membership_id=manager.id)
            self.uow.grants.add(grant)
            record(self.uow, actor, 'mailbox.grant', tenant_id=tenant_id, mailbox_id=mailbox_id)
            self.uow.commit()
        return grant

    def sending_mailbox(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID) -> Mailbox:
        mailbox = self.mailbox(actor, tenant_id, mailbox_id)
        member = self.uow.memberships.for_user(tenant_id, actor.user_id)
        grant = self.uow.grants.get(tenant_id, member.id, mailbox_id)
        if not grant.can_send:
            record(self.uow, actor, 'mail.send.authorization', tenant_id=tenant_id, mailbox_id=mailbox_id, outcome='denied')
            self.uow.commit()
            raise Forbidden('No tienes permiso de envio para este buzon. Solicitalo al administrador.')
        if not mailbox.smtp_enabled or not mailbox.smtp_host:
            raise Forbidden('El envio SMTP no esta habilitado para este buzon.')
        return mailbox

    def set_sending(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, membership_id: UUID, can_send: bool) -> MailboxGrant:
        self.member(actor, tenant_id, admin=True)
        if not self.uow.mailboxes.get(tenant_id, mailbox_id):
            raise NotFound('Buzon no disponible.')
        grant = self.uow.grants.get(tenant_id, membership_id, mailbox_id)
        if not grant:
            raise NotFound('Primero concede permiso de lectura a este cliente.')
        grant.can_send = can_send
        record(self.uow, actor, 'mailbox.send.grant' if can_send else 'mailbox.send.revoke', tenant_id=tenant_id, mailbox_id=mailbox_id)
        self.uow.commit()
        return grant

    def revoke(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, membership_id: UUID) -> None:
        self.member(actor, tenant_id, admin=True)
        if not self.uow.mailboxes.get(tenant_id, mailbox_id):
            raise NotFound('Buzón no disponible.')
        grant = self.uow.grants.get(tenant_id, membership_id, mailbox_id)
        if grant:
            self.uow.grants.remove(grant)
            record(self.uow, actor, 'mailbox.revoke', tenant_id=tenant_id, mailbox_id=mailbox_id)
            self.uow.commit()
