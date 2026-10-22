from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.mailboxes.domain.entities import Mailbox, MailboxCredential


class SQLMailboxRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, tenant_id: UUID, mailbox_id: UUID) -> Mailbox | None:
        return self.session.scalar(select(Mailbox).where(Mailbox.id == mailbox_id, Mailbox.tenant_id == tenant_id).execution_options(populate_existing=True))

    def list(self, tenant_id: UUID) -> list[Mailbox]:
        return list(self.session.scalars(select(Mailbox).where(Mailbox.tenant_id == tenant_id).order_by(Mailbox.created_at)))

    def add(self, mailbox: Mailbox) -> None:
        self.session.add(mailbox)

    def credential(self, mailbox_id: UUID) -> MailboxCredential | None:
        return self.session.scalar(select(MailboxCredential).where(MailboxCredential.mailbox_id == mailbox_id))

    def add_credential(self, credential: MailboxCredential) -> None:
        self.session.add(credential)
