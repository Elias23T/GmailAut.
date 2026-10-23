import sqlalchemy as sa

from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.mail_sending.domain.entities import OutgoingMessage

outgoing_messages = sa.Table('outgoing_messages', Base.metadata,
    sa.Column('id', sa.Uuid(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
    sa.Column('tenant_id', sa.Uuid(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
    sa.Column('mailbox_id', sa.Uuid(), nullable=False),
    sa.Column('membership_id', sa.Uuid(), nullable=False),
    sa.Column('encrypted_payload', sa.LargeBinary()),
    sa.Column('key_version', sa.Integer(), nullable=False),
    sa.Column('payload_hash', sa.String(64), nullable=False),
    sa.Column('message_id', sa.String(254), nullable=False, unique=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'prepared'")),
    sa.Column('sent_at', sa.DateTime(timezone=True)),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=utcnow),
    sa.ForeignKeyConstraint(['tenant_id', 'mailbox_id'], ['mailboxes.tenant_id', 'mailboxes.id'], name='fk_outgoing_mailbox', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'membership_id'], ['memberships.tenant_id', 'memberships.id'], name='fk_outgoing_membership', ondelete='CASCADE'),
    sa.CheckConstraint("status IN ('prepared','sending','sent','failed','unknown','expired')", name='ck_outgoing_status'),
    sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name='ck_outgoing_hash'),
    sa.CheckConstraint('key_version > 0', name='ck_outgoing_key'),
    sa.CheckConstraint('expires_at > created_at', name='ck_outgoing_expiry'),
    comment='Preparaciones de envio cifradas y estados para impedir reenvios. El contenido se elimina al finalizar o expirar.')
sa.Index('ix_outgoing_tenant_member', outgoing_messages.c.tenant_id, outgoing_messages.c.membership_id)
sa.Index('ix_outgoing_mailbox', outgoing_messages.c.tenant_id, outgoing_messages.c.mailbox_id)
sa.Index('ix_outgoing_expiry', outgoing_messages.c.expires_at)
Base.registry.map_imperatively(OutgoingMessage, outgoing_messages)
