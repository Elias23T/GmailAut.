from uuid import UUID
from fastapi import APIRouter
from app.core.dependencies import ActorDependency, UowDependency
from app.modules.authorization.application.service import AuthorizationService
from app.shared.domain.errors import NotFound
from .schemas import GrantCreate, GrantOutput

router = APIRouter(prefix='/tenants/{tenant_id}/mailboxes/{mailbox_id}/grants', tags=['Permisos'])


@router.get('', response_model=list[GrantOutput])
def list_grants(tenant_id: UUID, mailbox_id: UUID, actor: ActorDependency, uow: UowDependency):
    AuthorizationService(uow).member(actor, tenant_id, admin=True)
    if not uow.mailboxes.get(tenant_id, mailbox_id):
        raise NotFound('Buzón no disponible.')
    return uow.grants.list(tenant_id, mailbox_id)


@router.post('', response_model=GrantOutput, status_code=201)
def add_grant(tenant_id: UUID, mailbox_id: UUID, body: GrantCreate, actor: ActorDependency, uow: UowDependency):
    return AuthorizationService(uow).grant(actor, tenant_id, mailbox_id, body.membership_id)


@router.delete('/{membership_id}', status_code=204)
def revoke_grant(tenant_id: UUID, mailbox_id: UUID, membership_id: UUID, actor: ActorDependency, uow: UowDependency):
    AuthorizationService(uow).revoke(actor, tenant_id, mailbox_id, membership_id)
