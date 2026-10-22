from typing import Literal
from pydantic import EmailStr
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from app.core.dependencies import ActorDependency, UowDependency, require_administrator
from app.modules.identity.application.administration import ClientAdministration
from app.modules.identity.presentation.schemas import RegisterInput
from app.modules.mcp_integration.infrastructure.repository import SQLOAuthRepository
from app.shared.presentation.schemas import InputModel, OutputModel

router = APIRouter(prefix='/admin', tags=['Administración'], dependencies=[Depends(require_administrator)])


class ClientCreate(RegisterInput):
    tenant_id: UUID


class ClientStatus(InputModel):
    status: Literal['active', 'disabled']


class ClientLink(InputModel):
    tenant_id: UUID
    email: EmailStr


class ClientOutput(OutputModel):
    id: UUID
    name: str
    email: str
    status: str
    membership_id: UUID


def service(request, uow):
    return ClientAdministration(uow, request.app.state.passwords, SQLOAuthRepository(uow.session))


@router.get('/clients', response_model=list[ClientOutput])
def clients(tenant_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).list(actor, tenant_id)


@router.post('/clients', response_model=ClientOutput, status_code=201)
def create(body: ClientCreate, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).create(actor, body.tenant_id, body.name, str(body.email), body.password.get_secret_value())


@router.patch('/clients/{user_id}', status_code=204)
def status(user_id: UUID, tenant_id: UUID, body: ClientStatus, request: Request, actor: ActorDependency, uow: UowDependency):
    service(request, uow).status(actor, tenant_id, user_id, body.status)


@router.post('/clients/link', response_model=ClientOutput, status_code=201)
def link(body: ClientLink, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).link(actor, body.tenant_id, str(body.email))
