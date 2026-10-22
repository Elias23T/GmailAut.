from uuid import UUID
from fastapi import APIRouter, Request, Depends
from app.core.dependencies import ActorDependency, UowDependency, require_administrator
from app.modules.mailboxes.application.service import MailboxService
from .schemas import MailboxCreate, MailboxUpdate, MailboxOutput

router = APIRouter(prefix='/tenants/{tenant_id}/mailboxes', tags=['Buzones'], dependencies=[Depends(require_administrator)])


def service(request: Request, uow):
    return MailboxService(uow, request.app.state.cipher)


@router.get('', response_model=list[MailboxOutput])
def list_mailboxes(tenant_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).list(actor, tenant_id)


@router.post('', response_model=MailboxOutput, status_code=201)
def create_mailbox(tenant_id: UUID, body: MailboxCreate, request: Request, actor: ActorDependency, uow: UowDependency):
    values = body.model_dump(exclude={'password'})
    values['email'] = str(body.email)
    values['password'] = body.password.get_secret_value()
    application = service(request, uow)
    return application.view(actor, application.create(actor, tenant_id, **values))


@router.patch('/{mailbox_id}', response_model=MailboxOutput)
def update_mailbox(tenant_id: UUID, mailbox_id: UUID, body: MailboxUpdate, request: Request, actor: ActorDependency, uow: UowDependency):
    values = body.model_dump(exclude_unset=True)
    if body.password is not None:
        values['password'] = body.password.get_secret_value()
    application = service(request, uow)
    return application.view(actor, application.update(actor, tenant_id, mailbox_id, values))
