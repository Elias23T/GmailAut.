from uuid import UUID
from fastapi import APIRouter, Query
from app.core.dependencies import ActorDependency, UowDependency
from app.modules.authorization.application.service import AuthorizationService
from .schemas import AuditOutput

router = APIRouter(prefix='/tenants/{tenant_id}/audit', tags=['Auditoría'])


@router.get('', response_model=list[AuditOutput])
def list_events(tenant_id: UUID, actor: ActorDependency, uow: UowDependency,
                limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=100000)):
    AuthorizationService(uow).member(actor, tenant_id, admin=True)
    return uow.audit.list(tenant_id, limit, offset)
