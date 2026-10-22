from uuid import UUID
from app.modules.authorization.application.service import AuthorizationService
from app.modules.audit.application.service import record
from app.modules.mail_access.domain.ports import MailReader
from app.shared.application.ports import SecretCipher
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor
from app.shared.domain.errors import ApplicationError, Unavailable


class MailAccessService:
    def __init__(self, uow: UnitOfWork, cipher: SecretCipher, reader: MailReader):
        self.uow, self.cipher, self.reader = uow, cipher, reader
        self.authorization = AuthorizationService(uow)

    def _access(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, check: bool = False):
        if check:
            self.authorization.member(actor, tenant_id, admin=True)
        mailbox = self.authorization.mailbox(actor, tenant_id, mailbox_id, require_active=not check)
        credential = self.uow.mailboxes.credential(mailbox_id)
        if not credential:
            raise Unavailable('El buzón no tiene credenciales configuradas.')
        password = self.cipher.decrypt(credential.encrypted_secret, mailbox_id, credential.key_version)
        self.uow.commit()  # Liberar la conexion PostgreSQL mientras se consulta IMAP.
        return mailbox, credential.username, password

    def _run(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, action: str, operation, *, check: bool = False):
        mailbox, username, password = self._access(actor, tenant_id, mailbox_id, check)
        try:
            result = operation(mailbox, username, password)
        except ApplicationError:
            record(self.uow, actor, action, tenant_id=tenant_id, mailbox_id=mailbox_id, outcome='error')
            self.uow.commit()
            raise
        # Revalidar permisos despues de la operacion de red antes de devolver contenido.
        mailbox = self.authorization.mailbox(actor, tenant_id, mailbox_id, require_active=not check)
        if check:
            self.authorization.member(actor, tenant_id, admin=True)
            mailbox.status = 'active'
        record(self.uow, actor, action, tenant_id=tenant_id, mailbox_id=mailbox_id)
        self.uow.commit()
        return result

    def check(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID) -> None:
        self._run(actor, tenant_id, mailbox_id, 'mailbox.check', self.reader.check, check=True)

    def search(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, query: str, unread: bool, limit: int, offset: int):
        return self._run(actor, tenant_id, mailbox_id, 'mail.search',
                         lambda box, user, password: self.reader.search(box, user, password, query, unread, limit, offset))

    def read(self, actor: Actor, tenant_id: UUID, mailbox_id: UUID, uid: int, uid_validity: int):
        return self._run(actor, tenant_id, mailbox_id, 'mail.read',
                         lambda box, user, password: self.reader.read(box, user, password, uid, uid_validity))
