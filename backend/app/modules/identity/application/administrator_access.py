"""Acceso de los administradores globales sin modificar permisos de clientes."""
from app.modules.memberships.domain.entities import Membership
from app.modules.authorization.domain.entities import MailboxGrant


def attach_administrator(uow, user):
    for tenant in uow.tenants.all():
        member = uow.memberships.for_user(tenant.id, user.id)
        if member:
            member.role, member.status = 'owner', 'active'
        else:
            member = Membership(tenant_id=tenant.id, user_id=user.id, role='owner')
            uow.memberships.add(member)
        uow.flush()
        for mailbox in uow.mailboxes.list(tenant.id):
            if not uow.grants.get(tenant.id, member.id, mailbox.id):
                uow.grants.add(MailboxGrant(tenant_id=tenant.id, membership_id=member.id, mailbox_id=mailbox.id))
