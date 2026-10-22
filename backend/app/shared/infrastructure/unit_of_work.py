from sqlalchemy.orm import Session

from app.shared.infrastructure import model_registry
from app.modules.identity.infrastructure.repositories import SQLUserRepository
from app.modules.tenants.infrastructure.repositories import SQLTenantRepository
from app.modules.memberships.infrastructure.repositories import SQLMembershipRepository
from app.modules.mailboxes.infrastructure.repositories import SQLMailboxRepository
from app.modules.authorization.infrastructure.repositories import SQLGrantRepository
from app.modules.audit.infrastructure.repositories import SQLAuditRepository
from app.modules.mcp_integration.infrastructure.repository import SQLOAuthRepository


class SQLUnitOfWork:
    def __init__(self, session: Session):
        self.session = session
        self.users = SQLUserRepository(session)
        self.tenants = SQLTenantRepository(session)
        self.memberships = SQLMembershipRepository(session)
        self.mailboxes = SQLMailboxRepository(session)
        self.grants = SQLGrantRepository(session)
        self.audit = SQLAuditRepository(session)
        self.oauth = SQLOAuthRepository(session)

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
