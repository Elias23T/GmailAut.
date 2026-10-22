"""Esquema inicial: siete tablas de negocio, sin OAuth ni triggers.

Revision ID: 20261021_0001
Revises: ninguna

DDL equivalente a seeder/01_schema.sql en el momento de crear esta revision.
La revision es independiente de ese archivo y no lo lee al ejecutarse.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.Text(), sa.CheckConstraint("email = btrim(email) AND email <> ''"), nullable=False),
        sa.Column("password_hash", sa.Text(), sa.CheckConstraint("btrim(password_hash) <> ''"), nullable=False),
        sa.Column("name", sa.Text(), sa.CheckConstraint("btrim(name) <> ''"), nullable=False),
        sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('active', 'disabled')"), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="public",
    )
    op.create_index("uq_users_email_normalized", "users", [sa.text("lower(email)")], unique=True, schema="public")

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), sa.CheckConstraint("btrim(name) <> ''"), nullable=False),
        sa.Column("slug", sa.Text(), sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'"), nullable=False, unique=True),
        sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('active', 'suspended', 'disabled')"), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="public",
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("public.tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("public.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.Text(), sa.CheckConstraint("role IN ('owner', 'admin', 'member')"), nullable=False, server_default=sa.text("'member'")),
        sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('active', 'disabled')"), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_memberships_tenant_id"),
        schema="public",
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], schema="public")

    op.create_table(
        "mailboxes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("public.tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.Text(), sa.CheckConstraint("email = btrim(email) AND email <> ''"), nullable=False),
        sa.Column("display_name", sa.Text(), sa.CheckConstraint("btrim(display_name) <> ''"), nullable=False),
        sa.Column("imap_host", sa.Text(), sa.CheckConstraint("imap_host = btrim(imap_host) AND imap_host <> ''"), nullable=False),
        sa.Column("imap_port", sa.Integer(), sa.CheckConstraint("imap_port BETWEEN 1 AND 65535"), nullable=False, server_default=sa.text("993")),
        sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('pending', 'active', 'disabled', 'error')"), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mailboxes_tenant_id"),
        comment="Configuracion IMAP exclusivamente con TLS y validacion de certificado. No almacena mensajes.",
        schema="public",
    )
    op.create_index("uq_mailboxes_tenant_email_normalized", "mailboxes", ["tenant_id", sa.text("lower(email)")], unique=True, schema="public")

    op.create_table(
        "mailbox_credentials",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("mailbox_id", sa.Uuid(), sa.ForeignKey("public.mailboxes.id", ondelete="RESTRICT"), nullable=False, unique=True),
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
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="public",
    )

    op.create_table(
        "mailbox_grants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("public.tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("mailbox_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("membership_id", "mailbox_id", name="uq_mailbox_grants_membership_mailbox"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"], ["public.memberships.tenant_id", "public.memberships.id"],
            name="fk_mailbox_grants_membership", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mailbox_id"], ["public.mailboxes.tenant_id", "public.mailboxes.id"],
            name="fk_mailbox_grants_mailbox", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "granted_by_membership_id"], ["public.memberships.tenant_id", "public.memberships.id"],
            name="fk_mailbox_grants_grantor", ondelete="RESTRICT",
        ),
        comment="Todos los permisos son de lectura. Revocar elimina la concesion y genera un evento de auditoria.",
        schema="public",
    )
    op.create_index("ix_mailbox_grants_tenant_mailbox", "mailbox_grants", ["tenant_id", "mailbox_id"], schema="public")
    op.create_index("ix_mailbox_grants_tenant_grantor", "mailbox_grants", ["tenant_id", "granted_by_membership_id"], schema="public")

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("public.tenants.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("public.users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("mailbox_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), sa.CheckConstraint("btrim(action) <> ''"), nullable=False),
        sa.Column("outcome", sa.Text(), sa.CheckConstraint("outcome IN ('success', 'denied', 'error')"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), sa.CheckConstraint("source IN ('rest', 'mcp', 'system')"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("mailbox_id IS NULL OR tenant_id IS NOT NULL", name="ck_audit_events_mailbox_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "mailbox_id"], ["public.mailboxes.tenant_id", "public.mailboxes.id"],
            name="fk_audit_events_mailbox", ondelete="RESTRICT",
        ),
        comment="Eventos sin cuerpos, asuntos, adjuntos, terminos de busqueda, tokens ni credenciales.",
        schema="public",
    )
    op.create_index("ix_audit_events_tenant_created_at", "audit_events", ["tenant_id", sa.text("created_at DESC")], schema="public")
    op.create_index("ix_audit_events_actor_created_at", "audit_events", ["actor_user_id", sa.text("created_at DESC")], schema="public")
    op.create_index("ix_audit_events_tenant_mailbox", "audit_events", ["tenant_id", "mailbox_id"], schema="public")
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"], schema="public")


def downgrade() -> None:
    # Orden inverso de dependencias; DROP TABLE elimina sus indices asociados.
    op.drop_table("audit_events", schema="public")
    op.drop_table("mailbox_grants", schema="public")
    op.drop_table("mailbox_credentials", schema="public")
    op.drop_table("mailboxes", schema="public")
    op.drop_table("memberships", schema="public")
    op.drop_table("tenants", schema="public")
    op.drop_table("users", schema="public")
