from uuid import UUID
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.modules.mail_sending.domain.entities import OutgoingMessage
from app.shared.domain.entities import utcnow


class SQLOutgoingRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, message):
        self.session.add(message)

    def get(self, tenant_id: UUID, membership_id: UUID, message_id: UUID):
        return self.session.scalar(select(OutgoingMessage).where(OutgoingMessage.tenant_id == tenant_id,
            OutgoingMessage.membership_id == membership_id, OutgoingMessage.id == message_id).execution_options(populate_existing=True))

    def claim(self, message):
        result = self.session.execute(update(OutgoingMessage).where(OutgoingMessage.id == message.id,
            OutgoingMessage.status == 'prepared', OutgoingMessage.expires_at > utcnow()).values(status='sending'))
        return result.rowcount == 1

    def expire(self, tenant_id):
        self.session.execute(update(OutgoingMessage).where(OutgoingMessage.tenant_id == tenant_id,
            OutgoingMessage.status.in_(['prepared', 'sending']), OutgoingMessage.expires_at <= utcnow())
            .values(status=case((OutgoingMessage.status == 'prepared', 'expired'), else_='unknown'), encrypted_payload=None))

    def pending(self, tenant_id, membership_id):
        return self.session.scalar(select(func.count()).select_from(OutgoingMessage).where(
            OutgoingMessage.tenant_id == tenant_id, OutgoingMessage.membership_id == membership_id,
            OutgoingMessage.status == 'prepared'))
