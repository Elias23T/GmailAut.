from typing import Literal

from pydantic import EmailStr, Field, field_validator, model_validator
from app.shared.presentation.schemas import InputModel


class EmailContent(InputModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=16000)

    @field_validator('to')
    @classmethod
    def ascii_address(cls, value):
        if not str(value).isascii():
            raise ValueError('Usa una direccion de destinatario sin caracteres internacionales.')
        return value

    @field_validator('subject')
    @classmethod
    def safe_subject(cls, value):
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('El asunto debe contener texto sin saltos de linea.')
        return value

    @field_validator('body')
    @classmethod
    def safe_body(cls, value):
        if not value.strip() or any(ord(char) < 32 and char not in '\r\n\t' for char in value):
            raise ValueError('El mensaje debe contener texto sin caracteres de control.')
        return value


class PrepareEmail(InputModel):
    to: EmailStr | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=16000)
    reply_uid: int | None = Field(default=None, ge=1, le=4294967295)
    uid_validity: int | None = Field(default=None, ge=1, le=4294967295)

    @model_validator(mode='after')
    def reply_or_new(self):
        if (self.reply_uid is None) != (self.uid_validity is None):
            raise ValueError('Para responder indica reply_uid y uid_validity del correo original.')
        if self.reply_uid is None and (not self.to or not self.subject):
            raise ValueError('Para un correo nuevo indica destinatario y asunto.')
        return self


class ConfirmEmail(EmailContent):
    confirmed: Literal[True]
