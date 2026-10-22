from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.authorization.domain.entities import MailboxGrant


class SQLGrantRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, tenant_id: UUID, membership_id: UUID, mailbox_id: UUID) -> MailboxGrant | None:
        return self.session.scalar(select(MailboxGrant).where(
            MailboxGrant.tenant_id == tenant_id, MailboxGrant.membership_id == membership_id, MailboxGrant.mailbox_id == mailbox_id,
        ))

    def list(self, tenant_id: UUID, mailbox_id: UUID) -> list[MailboxGrant]:
        return list(self.session.scalars(select(MailboxGrant).where(MailboxGrant.tenant_id == tenant_id, MailboxGrant.mailbox_id == mailbox_id)))

    def add(self, grant: MailboxGrant) -> None:
        self.session.add(grant)

    def remove(self, grant: MailboxGrant) -> None:
        self.session.delete(grant)
