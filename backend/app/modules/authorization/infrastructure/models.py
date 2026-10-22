import sqlalchemy as sa

from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.authorization.domain.entities import MailboxGrant

mailbox_grants_table = sa.Table(
    "mailbox_grants",
    Base.metadata,
    sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
    sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
    sa.Column("membership_id", sa.Uuid(), nullable=False),
    sa.Column("mailbox_id", sa.Uuid(), nullable=False),
    sa.Column("granted_by_membership_id", sa.Uuid(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.UniqueConstraint("membership_id", "mailbox_id", name="uq_mailbox_grants_membership_mailbox"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "membership_id"], ["memberships.tenant_id", "memberships.id"],
        name="fk_mailbox_grants_membership", ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "mailbox_id"], ["mailboxes.tenant_id", "mailboxes.id"],
        name="fk_mailbox_grants_mailbox", ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "granted_by_membership_id"], ["memberships.tenant_id", "memberships.id"],
        name="fk_mailbox_grants_grantor", ondelete="CASCADE",
    ),
    comment="Todos los permisos son de lectura. Revocar elimina la concesion y genera un evento de auditoria.",

)
Base.registry.map_imperatively(MailboxGrant, mailbox_grants_table)

sa.Index('ix_mailbox_grants_tenant_mailbox', mailbox_grants_table.c.tenant_id, mailbox_grants_table.c.mailbox_id)

sa.Index('ix_mailbox_grants_tenant_grantor', mailbox_grants_table.c.tenant_id, mailbox_grants_table.c.granted_by_membership_id)
