"""Configuracion de entorno; las credenciales no forman parte del codigo."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    migration_database_url: SecretStr | None = None
    database_pool_size: int = Field(default=2, ge=1, le=20)
    database_max_overflow: int = Field(default=3, ge=0, le=20)
    database_pool_timeout: int = Field(default=10, ge=1, le=60)
    database_connect_timeout: int = Field(default=5, ge=1, le=60)
    jwt_secret: SecretStr | None = None
    jwt_minutes: int = Field(default=30, ge=5, le=120)
    mailbox_encryption_key: SecretStr | None = None
    mailbox_encryption_key_version: int = Field(default=1, ge=1)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    imap_timeout: int = Field(default=10, ge=1, le=60)
    imap_max_message_bytes: int = Field(default=1048576, ge=16384, le=5242880)
    imap_allow_private_hosts: bool = False
    smtp_timeout: int = Field(default=10, ge=1, le=60)
    smtp_allow_private_hosts: bool = False
    public_base_url: str = 'http://127.0.0.1:8000'
    frontend_url: str = 'http://127.0.0.1:5173'
    oauth_redirect_uris: list[str] = ['https://chatgpt.com/connector_platform_oauth_redirect']

    @field_validator('oauth_redirect_uris')
    @classmethod
    def validate_callbacks(cls, values: list[str]) -> list[str]:
        from urllib.parse import urlsplit
        if not values or len(values) > 20:
            raise ValueError('Configura entre uno y veinte callbacks OAuth exactos.')
        for value in values:
            parsed = urlsplit(value)
            if (len(value) > 2048 or any(ord(char) < 33 for char in value) or not parsed.hostname
                    or parsed.username or parsed.password or parsed.fragment or parsed.scheme not in ('https', 'http')
                    or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))):
                raise ValueError('El callback OAuth debe ser una URL HTTPS sin fragmentos; HTTP solo en localhost.')
        return values

    @model_validator(mode='after')
    def production_https(self):
        if self.app_env == 'production' and any(not url.startswith('https://') for url in
                [self.public_base_url, self.frontend_url, *self.oauth_redirect_uris]):
            raise ValueError('Producción requiere HTTPS en los orígenes y callbacks configurados.')
        if self.app_env == 'production':
            import base64
            secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ''
            if len(secret) < 32 or secret.startswith('CHANGE_ME'):
                raise ValueError('Producción requiere un JWT_SECRET válido de al menos 32 caracteres.')
            try:
                key = base64.b64decode(self.mailbox_encryption_key.get_secret_value() if self.mailbox_encryption_key else '', altchars=b'-_', validate=True)
            except ValueError:
                key = b''
            if len(key) != 32:
                raise ValueError('Producción requiere MAILBOX_ENCRYPTION_KEY de 32 bytes en Base64 URL-safe.')
            if self.imap_allow_private_hosts or self.smtp_allow_private_hosts:
                raise ValueError('Producción requiere IMAP_ALLOW_PRIVATE_HOSTS y SMTP_ALLOW_PRIVATE_HOSTS desactivados.')
        return self

    @field_validator('public_base_url', 'frontend_url')
    @classmethod
    def validate_public_url(cls, value: str) -> str:
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/')
                or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))):
            raise ValueError('Usa un origen HTTPS; HTTP solo se permite en localhost.')
        return value.rstrip('/')

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError("DATABASE_URL debe ser una URL valida de PostgreSQL.") from None
        if url.drivername != "postgresql+psycopg" or not url.username or not url.database:
            raise ValueError(
                "DATABASE_URL debe usar postgresql+psycopg e incluir usuario y base de datos."
            )
        return value
