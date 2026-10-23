from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import EmailStr, Field, SecretStr, StringConstraints, field_validator, model_validator
from pydantic import AnyUrl, TypeAdapter, UrlConstraints
from app.shared.presentation.schemas import InputModel, OutputModel, Name

Host = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=253, pattern=r'^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$')]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]
WebmailUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
_https_url = TypeAdapter(Annotated[AnyUrl, UrlConstraints(allowed_schemes=['https'], host_required=True)])


class WebmailInput(InputModel):
    webmail_url: WebmailUrl | None = None

    @field_validator('webmail_url')
    @classmethod
    def valid_webmail_url(cls, value):
        if value is None:
            return None
        url = _https_url.validate_python(value)
        if url.username or url.password:
            raise ValueError('La URL del webmail no debe incluir usuario ni contraseña.')
        normalized = str(url)
        if len(normalized) > 2048:
            raise ValueError('La URL del webmail admite hasta 2048 caracteres.')
        return normalized


class MailboxCreate(WebmailInput):
    email: EmailStr
    display_name: Name
    imap_host: Host
    imap_port: int = Field(default=993, ge=1, le=65535)
    username: Username
    password: SecretStr = Field(min_length=1, max_length=1024)
    smtp_enabled: bool = False
    smtp_host: Host | None = None
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_security: Literal['tls', 'starttls'] = 'tls'

    @model_validator(mode='after')
    def require_smtp_host(self):
        if self.smtp_enabled and not self.smtp_host:
            raise ValueError('Indica el servidor SMTP para habilitar el envio.')
        return self


class MailboxUpdate(WebmailInput):
    display_name: Name | None = None
    imap_host: Host | None = None
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    username: Username | None = None
    password: SecretStr | None = Field(default=None, min_length=1, max_length=1024)
    status: Literal['disabled', 'pending'] | None = None
    smtp_enabled: bool | None = None
    smtp_host: Host | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: Literal['tls', 'starttls'] | None = None

    @model_validator(mode='after')
    def require_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set - {'webmail_url'}):
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
    smtp_enabled: bool
    smtp_host: str | None
    smtp_port: int
    smtp_security: str
    can_send: bool
    webmail_url: str | None
