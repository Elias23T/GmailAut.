from uuid import UUID
from app.modules.mailboxes.domain.entities import Mailbox, MailboxCredential
from app.modules.authorization.domain.entities import MailboxGrant
from app.modules.authorization.application.service import AuthorizationService
from app.modules.audit.application.service import record
from app.shared.application.ports import SecretCipher
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor
from app.shared.domain.errors import NotFound, InvalidInput


class MailboxService:
    def __init__(self, uow: UnitOfWork, cipher: SecretCipher):
        self.uow, self.cipher = uow, cipher
        self.authorization = AuthorizationService(uow)

    def list(self, actor: Actor, tenant_id: UUID) -> list[dict]:
        member = self.authorization.member(actor, tenant_id)
        user = self.uow.users.get(actor.user_id)
        result = []
        for mailbox in self.uow.mailboxes.list(tenant_id):
            can_read = self.uow.grants.get(tenant_id, member.id, mailbox.id) is not None
            if can_read or user.is_platform_admin:
                result.append(self.view(actor, mailbox))
        return result

    def view(self, actor: Actor, mailbox: Mailbox) -> dict:
        member = self.uow.memberships.for_user(mailbox.tenant_id, actor.user_id)
        can_read = bool(member and self.uow.grants.get(mailbox.tenant_id, member.id, mailbox.id))
        grant = self.uow.grants.get(mailbox.tenant_id, member.id, mailbox.id) if member else None
        return {'id': mailbox.id, 'tenant_id': mailbox.tenant_id, 'email': mailbox.email,
                'display_name': mailbox.display_name, 'imap_host': mailbox.imap_host, 'imap_port': mailbox.imap_port,
                'status': mailbox.status, 'can_read': can_read, 'created_at': mailbox.created_at, 'updated_at': mailbox.updated_at,
                'smtp_enabled': mailbox.smtp_enabled, 'smtp_host': mailbox.smtp_host, 'smtp_port': mailbox.smtp_port,
                'smtp_security': mailbox.smtp_security, 'can_send': bool(grant and grant.can_send and mailbox.smtp_enabled),
                'webmail_url': mailbox.webmail_url}

    def create(self, actor: Actor, tenant_id: UUID, *, email: str, display_name: str, imap_host: str,
               imap_port: int, username: str, password: str, smtp_enabled: bool = False, smtp_host: str | None = None,
               smtp_port: int = 465, smtp_security: str = 'tls', webmail_url: str | None = None) -> Mailbox:
        self.uow.users.lock_administration()
        manager = self.authorization.member(actor, tenant_id, admin=True)
        if smtp_enabled and not smtp_host:
            raise InvalidInput('Indica el servidor SMTP para habilitar el envio.')
        mailbox = Mailbox(tenant_id=tenant_id, email=email.lower(), display_name=display_name, imap_host=imap_host, imap_port=imap_port,
                          smtp_enabled=smtp_enabled, smtp_host=smtp_host, smtp_port=smtp_port, smtp_security=smtp_security,
                          webmail_url=webmail_url)
        encrypted = self.cipher.encrypt(password, mailbox.id)
        self.uow.mailboxes.add(mailbox)
        self.uow.flush()
        self.uow.mailboxes.add_credential(MailboxCredential(
            mailbox_id=mailbox.id, username=username, encrypted_secret=encrypted, key_version=self.cipher.version,
        ))
        for administrator in self.uow.users.administrators():
            member = self.uow.memberships.for_user(tenant_id, administrator.id)
            if member:
                self.uow.grants.add(MailboxGrant(tenant_id=tenant_id, mailbox_id=mailbox.id,
                    membership_id=member.id, granted_by_membership_id=manager.id))
        record(self.uow, actor, 'mailbox.create', tenant_id=tenant_id, mailbox_id=mailbox.id)
        record(self.uow, actor, 'mailbox.grant', tenant_id=tenant_id, mailbox_id=mailbox.id)
        self.uow.commit()
        return mailbox

    def update(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, changes: dict) -> Mailbox:
        self.authorization.member(actor, tenant_id, admin=True)
        mailbox = self.uow.mailboxes.get(tenant_id, mailbox_id)
        if not mailbox:
            raise NotFound('Buzón no disponible.')
        if changes.get('smtp_enabled', mailbox.smtp_enabled) and not changes.get('smtp_host', mailbox.smtp_host):
            raise InvalidInput('Indica el servidor SMTP para habilitar el envio.')
        credential = self.uow.mailboxes.credential(mailbox.id)
        secret = changes.pop('password', None)
        username = changes.pop('username', None)
        connection_changed = (
            secret is not None
            or (username is not None and (not credential or credential.username != username))
            or any(key in changes and changes[key] != getattr(mailbox, key) for key in ('imap_host', 'imap_port'))
        )
        if secret is not None:
            encrypted = self.cipher.encrypt(secret, mailbox.id)
            if not credential:
                credential = MailboxCredential(mailbox_id=mailbox.id, username=username or mailbox.email,
                                               encrypted_secret=encrypted, key_version=self.cipher.version)
                self.uow.mailboxes.add_credential(credential)
            else:
                credential.encrypted_secret, credential.key_version = encrypted, self.cipher.version
        if username is not None and credential:
            credential.username = username
        if connection_changed:
            mailbox.status = 'pending'
        for key, value in changes.items():
            setattr(mailbox, key, value)
        record(self.uow, actor, 'mailbox.update', tenant_id=tenant_id, mailbox_id=mailbox_id)
        self.uow.commit()
        return mailbox
