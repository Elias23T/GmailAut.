from uuid import UUID
from fastapi import APIRouter, Depends
from app.core.dependencies import ActorDependency, UowDependency, require_administrator
from app.modules.tenants.application.service import TenantService
from .schemas import TenantCreate, TenantUpdate, TenantStatus, TenantOutput

router = APIRouter(prefix='/tenants', tags=['Empresas'], dependencies=[Depends(require_administrator)])


@router.get('', response_model=list[TenantOutput])
def list_tenants(actor: ActorDependency, uow: UowDependency):
    return TenantService(uow).list(actor)


@router.post('', response_model=TenantOutput, status_code=201)
def create_tenant(body: TenantCreate, actor: ActorDependency, uow: UowDependency):
    service = TenantService(uow)
    return service.view(actor, service.create(actor, body.name, body.slug))


@router.patch('/{tenant_id}', response_model=TenantOutput)
def update_tenant(tenant_id: UUID, body: TenantUpdate, actor: ActorDependency, uow: UowDependency):
    service = TenantService(uow)
    return service.view(actor, service.update(actor, tenant_id, body.model_dump(exclude_unset=True)))


@router.patch('/{tenant_id}/status', response_model=TenantOutput)
def change_status(tenant_id: UUID, body: TenantStatus, actor: ActorDependency, uow: UowDependency):
    service = TenantService(uow)
    return service.view(actor, service.change_status(actor, tenant_id, body.status))


@router.delete('/{tenant_id}', status_code=204)
def delete_tenant(tenant_id: UUID, actor: ActorDependency, uow: UowDependency):
    TenantService(uow).delete(actor, tenant_id)
