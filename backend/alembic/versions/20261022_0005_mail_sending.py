"""SMTP opcional, permiso de envio y preparaciones cifradas con control de reenvios."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_0005'
down_revision = '20261021_0004'
branch_labels = None
depends_on = None

SCOPES = "scopes = ARRAY['mail:read'] OR scopes = ARRAY['mail:read','mail:send']"


def upgrade():
    op.add_column('mailboxes', sa.Column('smtp_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('mailboxes', sa.Column('smtp_host', sa.Text()))
    op.add_column('mailboxes', sa.Column('smtp_port', sa.Integer(), nullable=False, server_default=sa.text('465')))
    op.add_column('mailboxes', sa.Column('smtp_security', sa.Text(), nullable=False, server_default=sa.text("'tls'")))
    op.create_check_constraint('ck_mailboxes_smtp_port', 'mailboxes', 'smtp_port BETWEEN 1 AND 65535')
    op.create_check_constraint('ck_mailboxes_smtp_security', 'mailboxes', "smtp_security IN ('tls', 'starttls')")
    op.create_check_constraint('ck_mailboxes_smtp_host', 'mailboxes', "NOT smtp_enabled OR (smtp_host IS NOT NULL AND btrim(smtp_host) <> '')")
    op.create_table_comment('mailboxes', 'Configuracion IMAP TLS y envio SMTP opcional con TLS y validacion de certificado.')
    op.add_column('mailbox_grants', sa.Column('can_send', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_table_comment('mailbox_grants', 'La concesion permite lectura; can_send autoriza envio por separado. Revocar genera auditoria.')
    for table in ('oauth_authorization_codes', 'oauth_tokens'):
        op.drop_constraint(table + '_scopes_check', table, type_='check')
        op.create_check_constraint(table + '_scopes_check', table, SCOPES)
    op.create_table('outgoing_messages',
        sa.Column('id', sa.Uuid(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Uuid(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mailbox_id', sa.Uuid(), nullable=False), sa.Column('membership_id', sa.Uuid(), nullable=False),
        sa.Column('encrypted_payload', sa.LargeBinary()), sa.Column('key_version', sa.Integer(), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False), sa.Column('message_id', sa.String(254), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'prepared'")),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['tenant_id', 'mailbox_id'], ['mailboxes.tenant_id', 'mailboxes.id'], name='fk_outgoing_mailbox', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'membership_id'], ['memberships.tenant_id', 'memberships.id'], name='fk_outgoing_membership', ondelete='CASCADE'),
        sa.CheckConstraint("status IN ('prepared','sending','sent','failed','unknown','expired')", name='ck_outgoing_status'),
        sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name='ck_outgoing_hash'),
        sa.CheckConstraint('key_version > 0', name='ck_outgoing_key'),
        sa.CheckConstraint('expires_at > created_at', name='ck_outgoing_expiry'),
        comment='Preparaciones de envio cifradas y estados para impedir reenvios. El contenido se elimina al finalizar o expirar.')
    op.create_index('ix_outgoing_tenant_member', 'outgoing_messages', ['tenant_id', 'membership_id'])
    op.create_index('ix_outgoing_mailbox', 'outgoing_messages', ['tenant_id', 'mailbox_id'])
    op.create_index('ix_outgoing_expiry', 'outgoing_messages', ['expires_at'])


def downgrade():
    op.drop_table('outgoing_messages')
    # No convertir autorizaciones de envio en lectura de forma silenciosa.
    op.execute("DELETE FROM oauth_tokens WHERE scopes <> ARRAY['mail:read']")
    op.execute("DELETE FROM oauth_authorization_codes WHERE scopes <> ARRAY['mail:read']")
    for table in ('oauth_authorization_codes', 'oauth_tokens'):
        op.drop_constraint(table + '_scopes_check', table, type_='check')
        op.create_check_constraint(table + '_scopes_check', table, "scopes = ARRAY['mail:read']")
    op.drop_column('mailbox_grants', 'can_send')
    op.create_table_comment('mailbox_grants', 'Todos los permisos son de lectura. Revocar elimina la concesion y genera un evento de auditoria.')
    for name in ('ck_mailboxes_smtp_host', 'ck_mailboxes_smtp_security', 'ck_mailboxes_smtp_port'):
        op.drop_constraint(name, 'mailboxes', type_='check')
    for name in ('smtp_security', 'smtp_port', 'smtp_host', 'smtp_enabled'):
        op.drop_column('mailboxes', name)
    op.create_table_comment('mailboxes', 'Configuracion IMAP exclusivamente con TLS y validacion de certificado. No almacena mensajes.')
