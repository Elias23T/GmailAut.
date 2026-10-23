"""Registro explicito de mapeos, sin crear ni alterar tablas."""

from app.modules.identity.infrastructure import models as identity_models
from app.modules.tenants.infrastructure import models as tenant_models
from app.modules.memberships.infrastructure import models as membership_models
from app.modules.mailboxes.infrastructure import models as mailbox_models
from app.modules.authorization.infrastructure import models as authorization_models
from app.modules.audit.infrastructure import models as audit_models
from app.modules.mcp_integration.infrastructure import models as oauth_models
from app.modules.mail_sending.infrastructure import models as outgoing_models
from app.shared.infrastructure.database import Base

metadata = Base.metadata
