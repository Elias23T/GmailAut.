from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import Field, model_validator
from app.shared.presentation.schemas import InputModel, OutputModel, Name


class TenantCreate(InputModel):
    name: Name
    slug: str | None = Field(default=None, min_length=3, max_length=64, pattern=r'^[a-z0-9]+(-[a-z0-9]+)*$')


class TenantUpdate(InputModel):
    name: Name | None = None
    slug: str | None = Field(default=None, min_length=3, max_length=64, pattern=r'^[a-z0-9]+(-[a-z0-9]+)*$')

    @model_validator(mode='after')
    def changes_required(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('Indica un nombre o identificador válido para editar la empresa.')
        return self


class TenantStatus(InputModel):
    status: Literal['active', 'disabled']


class TenantOutput(OutputModel):
    id: UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    membership_id: UUID
