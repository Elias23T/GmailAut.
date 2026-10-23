from typing import Literal
from pydantic import EmailStr, Field, SecretStr, model_validator
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from app.core.dependencies import ActorDependency, UowDependency, require_administrator
from app.modules.identity.application.administration import ClientAdministration
from app.modules.identity.application.administrators import AdministratorAdministration
from app.modules.identity.presentation.schemas import RegisterInput, ClientUsername, UserOutput
from app.modules.mcp_integration.infrastructure.repository import SQLOAuthRepository
from app.shared.presentation.schemas import InputModel, OutputModel, Name

router = APIRouter(prefix='/admin', tags=['Administración'], dependencies=[Depends(require_administrator)])


class ClientCreate(RegisterInput):
    tenant_id: UUID
    username: ClientUsername | None = None


class AdministratorCreate(InputModel):
    name: Name
    username: ClientUsername
    email: EmailStr | None = None
    password: SecretStr = Field(min_length=6, max_length=1024)


class AdministratorUpdate(InputModel):
    name: Name | None = None
    username: ClientUsername | None = None
    email: EmailStr | None = None
    password: SecretStr | None = Field(default=None, min_length=6, max_length=1024)

    @model_validator(mode='after')
    def valid_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set - {'email'}):
            raise ValueError('Indica al menos un cambio. Solo el correo opcional admite un valor nulo.')
        return self


class ClientCredentials(InputModel):
    username: ClientUsername
    password: SecretStr | None = Field(default=None, min_length=6, max_length=1024)


class ClientStatus(InputModel):
    status: Literal['active', 'disabled']


class DisabledClientsDelete(InputModel):
    user_ids: list[UUID] = Field(min_length=1)
    confirmed: Literal[True]

    @model_validator(mode='after')
    def unique_clients(self):
        if len(set(self.user_ids)) != len(self.user_ids):
            raise ValueError('La lista no debe repetir clientes.')
        return self


class DisabledClientsDeleted(OutputModel):
    deleted_count: int


class ClientLink(InputModel):
    tenant_id: UUID
    email: EmailStr


class ClientAccountOutput(OutputModel):
    id: UUID
    name: str
    email: str | None
    username: str | None
    status: str


class ClientOutput(ClientAccountOutput):
    membership_id: UUID


class ClientCompanyOutput(OutputModel):
    id: UUID
    name: str
    status: str


class GlobalClientOutput(OutputModel):
    id: UUID
    name: str
    email: str | None
    username: str | None
    status: str
    companies: list[ClientCompanyOutput]


def service(request, uow):
    return ClientAdministration(uow, request.app.state.passwords, SQLOAuthRepository(uow.session))


@router.get('/administrators', response_model=list[UserOutput])
def administrators(request: Request, actor: ActorDependency, uow: UowDependency):
    return AdministratorAdministration(uow, request.app.state.passwords).list(actor)


@router.post('/administrators', response_model=UserOutput, status_code=201)
def create_administrator(body: AdministratorCreate, request: Request, actor: ActorDependency, uow: UowDependency):
    return AdministratorAdministration(uow, request.app.state.passwords).create(actor,
        body.name, body.username, body.password.get_secret_value(), str(body.email) if body.email else None)


@router.patch('/administrators/{user_id}/status', response_model=UserOutput)
def administrator_status(user_id: UUID, body: ClientStatus, request: Request, actor: ActorDependency, uow: UowDependency):
    return AdministratorAdministration(uow, request.app.state.passwords).status(actor, user_id, body.status)


@router.patch('/administrators/{user_id}', response_model=UserOutput)
def update_administrator(user_id: UUID, body: AdministratorUpdate, request: Request, actor: ActorDependency, uow: UowDependency):
    changes = body.model_dump(exclude_unset=True, exclude={'password'})
    if body.password is not None:
        changes['password'] = body.password.get_secret_value()
    return AdministratorAdministration(uow, request.app.state.passwords).update(actor, user_id, changes)


@router.delete('/administrators/{user_id}', status_code=204)
def delete_administrator(user_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    AdministratorAdministration(uow, request.app.state.passwords).delete(actor, user_id)


@router.get('/clients', response_model=list[ClientOutput])
def clients(tenant_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).list(actor, tenant_id)


@router.get('/clients/available', response_model=list[ClientAccountOutput])
def available(tenant_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).available(actor, tenant_id)


@router.get('/clients/all', response_model=list[GlobalClientOutput])
def all_clients(request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).all(actor)


@router.post('/clients/delete-disabled', response_model=DisabledClientsDeleted)
def delete_disabled_clients(body: DisabledClientsDelete, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).delete_disabled(actor, body.user_ids)


@router.patch('/clients/{user_id}/status', status_code=204)
def global_client_status(user_id: UUID, body: ClientStatus, request: Request, actor: ActorDependency, uow: UowDependency):
    service(request, uow).status(actor, None, user_id, body.status)


@router.delete('/clients/{user_id}', status_code=204)
def delete_client(user_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    service(request, uow).delete(actor, user_id)


@router.post('/clients', response_model=ClientOutput, status_code=201)
def create(body: ClientCreate, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).create(actor, body.tenant_id, body.name, str(body.email), body.password.get_secret_value(), body.username)


@router.patch('/clients/{user_id}/credentials', response_model=ClientOutput | ClientAccountOutput)
def credentials(user_id: UUID, body: ClientCredentials, request: Request, actor: ActorDependency, uow: UowDependency, tenant_id: UUID | None = None):
    return service(request, uow).credentials(actor, tenant_id, user_id, body.username,
        body.password.get_secret_value() if body.password is not None else None)


@router.patch('/clients/{user_id}', status_code=204)
def status(user_id: UUID, tenant_id: UUID, body: ClientStatus, request: Request, actor: ActorDependency, uow: UowDependency):
    service(request, uow).status(actor, tenant_id, user_id, body.status)


@router.post('/clients/link', response_model=ClientOutput, status_code=201)
def link(body: ClientLink, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).link(actor, body.tenant_id, str(body.email))
