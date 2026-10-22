from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import EmailStr, Field, SecretStr, StringConstraints, model_validator
from app.shared.presentation.schemas import InputModel, OutputModel, Name

Host = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=253, pattern=r'^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$')]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]


class MailboxCreate(InputModel):
    email: EmailStr
    display_name: Name
    imap_host: Host
    imap_port: int = Field(default=993, ge=1, le=65535)
    username: Username
    password: SecretStr = Field(min_length=1, max_length=1024)


class MailboxUpdate(InputModel):
    display_name: Name | None = None
    imap_host: Host | None = None
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    username: Username | None = None
    password: SecretStr | None = Field(default=None, min_length=1, max_length=1024)
    status: Literal['disabled', 'pending'] | None = None

    @model_validator(mode='after')
    def require_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Indica al menos un cambio, sin valores nulos.')
        return self


class MailboxOutput(OutputModel):
    id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    imap_host: str
    imap_port: int
    status: str
    can_read: bool
    created_at: datetime
    updated_at: datetime
