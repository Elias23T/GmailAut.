from uuid import UUID
from fastapi import APIRouter, Request
from app.core.dependencies import ActorDependency, UowDependency
from app.modules.mail_sending.application.schemas import ConfirmEmail, PrepareEmail
from app.modules.mail_sending.application.service import MailSendingService

router = APIRouter(prefix='/tenants/{tenant_id}', tags=['Envio de correo'])


def service(request, uow):
    return MailSendingService(uow, request.app.state.cipher, request.app.state.mail_reader, request.app.state.mail_sender)


@router.post('/mailboxes/{mailbox_id}/smtp-check')
def check(tenant_id: UUID, mailbox_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).check(actor, tenant_id, mailbox_id)


@router.post('/mailboxes/{mailbox_id}/outgoing/prepare', status_code=201)
def prepare(tenant_id: UUID, mailbox_id: UUID, body: PrepareEmail, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).prepare(actor, tenant_id, mailbox_id, body)


@router.post('/outgoing/{preparation_id}/send')
def send(tenant_id: UUID, preparation_id: UUID, body: ConfirmEmail, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).send(actor, tenant_id, preparation_id, body)
