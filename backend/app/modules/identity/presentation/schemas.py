from datetime import datetime
from typing import Annotated
from uuid import UUID
from pydantic import EmailStr, Field, SecretStr, model_validator
from app.shared.presentation.schemas import InputModel, OutputModel, Name
from pydantic import BeforeValidator, StringConstraints

ClientUsername = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True,
    pattern=r'^[a-z][a-z0-9_.-]{2,31}$', min_length=3, max_length=32),
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value)]


class RegisterInput(InputModel):
    name: Name
    email: EmailStr
    password: SecretStr = Field(min_length=6, max_length=1024)


class LoginInput(InputModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @model_validator(mode='after')
    def one_identifier(self):
        if (self.email is None) == (self.username is None):
            raise ValueError('Envía un usuario o un correo para iniciar sesión.')
        return self


class UserOutput(OutputModel):
    id: UUID
    name: str
    email: str | None
    username: str | None
    status: str
    created_at: datetime
    is_platform_admin: bool


class TokenOutput(OutputModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int
    user: UserOutput
