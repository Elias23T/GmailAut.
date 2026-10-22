from uuid import UUID
from app.modules.audit.domain.entities import AuditEvent
from app.shared.domain.entities import Actor
from app.shared.application.unit_of_work import UnitOfWork


def record(uow: UnitOfWork, actor: Actor | None, action: str, *, tenant_id: UUID | None = None,
           mailbox_id: UUID | None = None, outcome: str = 'success', request_id: UUID | None = None) -> None:
    from uuid import uuid4
    uow.audit.add(AuditEvent(
        action=action, outcome=outcome, tenant_id=tenant_id, mailbox_id=mailbox_id,
        actor_user_id=actor.user_id if actor else None,
        request_id=actor.request_id if actor else (request_id or uuid4()), source=actor.source if actor else 'rest',
    ))
