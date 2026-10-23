import sqlalchemy as sa

from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.mailboxes.domain.entities import Mailbox, MailboxCredential

mailboxes_table = sa.Table(
    "mailboxes",
    Base.metadata,
    sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
    sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
    sa.Column("email", sa.Text(), sa.CheckConstraint("email = btrim(email) AND email <> ''"), nullable=False),
    sa.Column("display_name", sa.Text(), sa.CheckConstraint("btrim(display_name) <> ''"), nullable=False),
    sa.Column("imap_host", sa.Text(), sa.CheckConstraint("imap_host = btrim(imap_host) AND imap_host <> ''"), nullable=False),
    sa.Column("imap_port", sa.Integer(), sa.CheckConstraint("imap_port BETWEEN 1 AND 65535"), nullable=False, server_default=sa.text("993")),
    sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('pending', 'active', 'disabled', 'error')"), nullable=False, server_default=sa.text("'pending'")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=utcnow),
    sa.Column('smtp_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('smtp_host', sa.Text()),
    sa.Column('smtp_port', sa.Integer(), nullable=False, server_default=sa.text('465')),
    sa.Column('smtp_security', sa.Text(), nullable=False, server_default=sa.text("'tls'")),
    sa.Column('webmail_url', sa.Text()),
    sa.CheckConstraint("webmail_url IS NULL OR (length(webmail_url) <= 2048 AND webmail_url LIKE 'https://%')", name='ck_mailboxes_webmail_url'),
    sa.CheckConstraint('smtp_port BETWEEN 1 AND 65535', name='ck_mailboxes_smtp_port'),
    sa.CheckConstraint("smtp_security IN ('tls', 'starttls')", name='ck_mailboxes_smtp_security'),
    sa.CheckConstraint("NOT smtp_enabled OR (smtp_host IS NOT NULL AND btrim(smtp_host) <> '')", name='ck_mailboxes_smtp_host'),
    sa.UniqueConstraint("tenant_id", "id", name="uq_mailboxes_tenant_id"),
    comment="Configuracion IMAP TLS y envio SMTP opcional con TLS y validacion de certificado.",

)
Base.registry.map_imperatively(Mailbox, mailboxes_table)

sa.Index('uq_mailboxes_tenant_email_normalized', mailboxes_table.c.tenant_id, sa.func.lower(mailboxes_table.c.email), unique=True)

mailbox_credentials_table = sa.Table(
    "mailbox_credentials",
    Base.metadata,
    sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
    sa.Column("mailbox_id", sa.Uuid(), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, unique=True),
    sa.Column("username", sa.Text(), sa.CheckConstraint("btrim(username) <> ''"), nullable=False),
    sa.Column(
        "encrypted_secret", sa.LargeBinary(), sa.CheckConstraint("octet_length(encrypted_secret) > 0"), nullable=False,
        comment="Sobre cifrado autenticado generado por la aplicacion; debe incluir nonce y tag. Nunca texto plano.",
    ),
    sa.Column(
        "key_version", sa.Integer(), sa.CheckConstraint("key_version > 0"), nullable=False,
        comment="Referencia a una clave externa a PostgreSQL; permite rotar las credenciales.",
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=utcnow),

)
Base.registry.map_imperatively(MailboxCredential, mailbox_credentials_table)
