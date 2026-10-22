from uuid import UUID
from app.modules.mailboxes.domain.entities import Mailbox, MailboxCredential
from app.modules.authorization.domain.entities import MailboxGrant
from app.modules.authorization.application.service import AuthorizationService
from app.modules.audit.application.service import record
from app.shared.application.ports import SecretCipher
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor
from app.shared.domain.errors import NotFound


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
        return {'id': mailbox.id, 'tenant_id': mailbox.tenant_id, 'email': mailbox.email,
                'display_name': mailbox.display_name, 'imap_host': mailbox.imap_host, 'imap_port': mailbox.imap_port,
                'status': mailbox.status, 'can_read': can_read, 'created_at': mailbox.created_at, 'updated_at': mailbox.updated_at}

    def create(self, actor: Actor, tenant_id: UUID, *, email: str, display_name: str, imap_host: str,
               imap_port: int, username: str, password: str) -> Mailbox:
        manager = self.authorization.member(actor, tenant_id, admin=True)
        mailbox = Mailbox(tenant_id=tenant_id, email=email.lower(), display_name=display_name, imap_host=imap_host, imap_port=imap_port)
        encrypted = self.cipher.encrypt(password, mailbox.id)
        self.uow.mailboxes.add(mailbox)
        self.uow.flush()
        self.uow.mailboxes.add_credential(MailboxCredential(
            mailbox_id=mailbox.id, username=username, encrypted_secret=encrypted, key_version=self.cipher.version,
        ))
        self.uow.grants.add(MailboxGrant(
            tenant_id=tenant_id, mailbox_id=mailbox.id, membership_id=manager.id, granted_by_membership_id=manager.id,
        ))
        record(self.uow, actor, 'mailbox.create', tenant_id=tenant_id, mailbox_id=mailbox.id)
        record(self.uow, actor, 'mailbox.grant', tenant_id=tenant_id, mailbox_id=mailbox.id)
        self.uow.commit()
        return mailbox

    def update(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, changes: dict) -> Mailbox:
        self.authorization.member(actor, tenant_id, admin=True)
        mailbox = self.uow.mailboxes.get(tenant_id, mailbox_id)
        if not mailbox:
            raise NotFound('Buzón no disponible.')
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
