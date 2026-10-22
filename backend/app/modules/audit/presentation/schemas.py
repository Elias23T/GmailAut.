from datetime import datetime
from uuid import UUID
from app.shared.presentation.schemas import OutputModel


class AuditOutput(OutputModel):
    id: UUID
    actor_user_id: UUID | None
    mailbox_id: UUID | None
    action: str
    outcome: str
    request_id: UUID
    source: str
    created_at: datetime
