from typing import Protocol

from app.modules.audit.domain.repositories import AuditRepository
from app.modules.authorization.domain.repositories import GrantRepository
from app.modules.identity.domain.repositories import UserRepository
from app.modules.mailboxes.domain.repositories import MailboxRepository
from app.modules.memberships.domain.repositories import MembershipRepository
from app.modules.tenants.domain.repositories import TenantRepository
from app.modules.mcp_integration.domain.repository import OAuthRepository
from app.modules.mail_sending.domain.ports import OutgoingRepository


class UnitOfWork(Protocol):
    users: UserRepository
    tenants: TenantRepository
    memberships: MembershipRepository
    mailboxes: MailboxRepository
    grants: GrantRepository
    audit: AuditRepository
    oauth: OAuthRepository
    outgoing: OutgoingRepository

    def flush(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
