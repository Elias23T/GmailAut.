from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.audit.domain.entities import AuditEvent


class SQLAuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, event: AuditEvent) -> None:
        self.session.add(event)

    def list(self, tenant_id: UUID, limit: int, offset: int) -> list[AuditEvent]:
        return list(self.session.scalars(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(
            AuditEvent.created_at.desc(), AuditEvent.id.desc(),
        ).limit(limit).offset(offset)))
