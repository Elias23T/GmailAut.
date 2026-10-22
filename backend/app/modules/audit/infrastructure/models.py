import sqlalchemy as sa

from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.audit.domain.entities import AuditEvent

audit_events_table = sa.Table(
    "audit_events",
    Base.metadata,
    sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
    sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
    sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    sa.Column("mailbox_id", sa.Uuid(), nullable=True),
    sa.Column("action", sa.Text(), sa.CheckConstraint("btrim(action) <> ''"), nullable=False),
    sa.Column("outcome", sa.Text(), sa.CheckConstraint("outcome IN ('success', 'denied', 'error')"), nullable=False),
    sa.Column("request_id", sa.Uuid(), nullable=False),
    sa.Column("source", sa.Text(), sa.CheckConstraint("source IN ('rest', 'mcp', 'system')"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.CheckConstraint("mailbox_id IS NULL OR tenant_id IS NOT NULL", name="ck_audit_events_mailbox_tenant"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "mailbox_id"], ["mailboxes.tenant_id", "mailboxes.id"],
        name="fk_audit_events_mailbox", ondelete="CASCADE",
    ),
    comment="Eventos sin cuerpos, asuntos, adjuntos, terminos de busqueda, tokens ni credenciales.",

)
Base.registry.map_imperatively(AuditEvent, audit_events_table)

sa.Index('ix_audit_events_tenant_created_at', audit_events_table.c.tenant_id, audit_events_table.c.created_at.desc())

sa.Index('ix_audit_events_actor_created_at', audit_events_table.c.actor_user_id, audit_events_table.c.created_at.desc())

sa.Index('ix_audit_events_tenant_mailbox', audit_events_table.c.tenant_id, audit_events_table.c.mailbox_id)

sa.Index('ix_audit_events_request_id', audit_events_table.c.request_id)
