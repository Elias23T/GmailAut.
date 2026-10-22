from datetime import datetime
from uuid import UUID
from app.shared.presentation.schemas import InputModel, OutputModel


class GrantCreate(InputModel):
    membership_id: UUID


class GrantOutput(OutputModel):
    id: UUID
    membership_id: UUID
    mailbox_id: UUID
    granted_by_membership_id: UUID | None
    created_at: datetime
