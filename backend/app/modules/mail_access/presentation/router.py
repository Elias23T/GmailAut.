from uuid import UUID
from fastapi import APIRouter, Request, Query, Path
from app.core.dependencies import ActorDependency, UowDependency
from app.modules.mail_access.application.service import MailAccessService
from app.modules.mail_access.domain.entities import MessagePage, MessageDetail

router = APIRouter(prefix='/tenants/{tenant_id}/mailboxes/{mailbox_id}', tags=['Lectura de correo'])


def service(request: Request, uow):
    return MailAccessService(uow, request.app.state.cipher, request.app.state.mail_reader)


@router.post('/check')
def check_mailbox(tenant_id: UUID, mailbox_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    service(request, uow).check(actor, tenant_id, mailbox_id)
    return {'status': 'ok'}


@router.get('/messages', response_model=MessagePage)
def search_messages(tenant_id: UUID, mailbox_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency,
                    query: str = Query(default='', max_length=200), unread: bool = False,
                    limit: int = Query(default=20, ge=1, le=50), offset: int = Query(default=0, ge=0, le=10000)):
    return service(request, uow).search(actor, tenant_id, mailbox_id, query, unread, limit, offset)


@router.get('/messages/{uid}', response_model=MessageDetail)
def read_message(tenant_id: UUID, mailbox_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency,
                 uid: int = Path(ge=1, le=4294967295), uid_validity: int = Query(ge=1, le=4294967295)):
    return service(request, uow).read(actor, tenant_id, mailbox_id, uid, uid_validity)
