"""Administrador unico y persistencia de autorizaciones MCP.

Revision ID: 20261021_0002
Revises: 20261021_0001
"""
from alembic import op
import sqlalchemy as sa

revision = '20261021_0002'
down_revision = '20261021_0001'
branch_labels = None
depends_on = None

OAUTH_SQL = """CREATE TABLE public.oauth_clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL UNIQUE CHECK (btrim(client_id) <> ''),
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    client_secret_hash TEXT,
    redirect_uris TEXT[] NOT NULL,
    token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none'
        CHECK (token_endpoint_auth_method IN ('none', 'client_secret_basic')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_oauth_clients_redirect_uris CHECK (
        cardinality(redirect_uris) > 0
        AND array_position(redirect_uris, NULL) IS NULL
        AND NOT ('' = ANY (redirect_uris))
    ),
    CONSTRAINT ck_oauth_clients_secret CHECK (
        (token_endpoint_auth_method = 'none' AND client_secret_hash IS NULL)
        OR (token_endpoint_auth_method = 'client_secret_basic'
            AND client_secret_hash IS NOT NULL AND btrim(client_secret_hash) <> '')
    )
);

CREATE TABLE public.oauth_authorization_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code_hash TEXT NOT NULL UNIQUE CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    client_id UUID NOT NULL REFERENCES public.oauth_clients (id) ON DELETE RESTRICT,
    tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE RESTRICT,
    membership_id UUID NOT NULL,
    redirect_uri TEXT NOT NULL CHECK (btrim(redirect_uri) <> ''),
    resource_uri TEXT NOT NULL CHECK (btrim(resource_uri) <> ''),
    scopes TEXT[] NOT NULL DEFAULT ARRAY['mail:read'] CHECK (scopes = ARRAY['mail:read']),
    code_challenge TEXT NOT NULL CHECK (code_challenge ~ '^[A-Za-z0-9_-]{43}$'),
    code_challenge_method TEXT NOT NULL DEFAULT 'S256' CHECK (code_challenge_method = 'S256'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT fk_oauth_codes_membership FOREIGN KEY (tenant_id, membership_id)
        REFERENCES public.memberships (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_oauth_codes_expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_oauth_codes_consumed CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX ix_oauth_codes_client_id ON public.oauth_authorization_codes (client_id);
CREATE INDEX ix_oauth_codes_tenant_membership ON public.oauth_authorization_codes (tenant_id, membership_id);
CREATE INDEX ix_oauth_codes_expires_at ON public.oauth_authorization_codes (expires_at);

CREATE TABLE public.oauth_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    token_type TEXT NOT NULL CHECK (token_type IN ('access', 'refresh')),
    grant_id UUID NOT NULL,
    client_id UUID NOT NULL REFERENCES public.oauth_clients (id) ON DELETE RESTRICT,
    tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE RESTRICT,
    membership_id UUID NOT NULL,
    resource_uri TEXT NOT NULL CHECK (btrim(resource_uri) <> ''),
    scopes TEXT[] NOT NULL DEFAULT ARRAY['mail:read'] CHECK (scopes = ARRAY['mail:read']),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT fk_oauth_tokens_membership FOREIGN KEY (tenant_id, membership_id)
        REFERENCES public.memberships (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_oauth_tokens_expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_oauth_tokens_revocation CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE INDEX ix_oauth_tokens_client_id ON public.oauth_tokens (client_id);
CREATE INDEX ix_oauth_tokens_tenant_membership ON public.oauth_tokens (tenant_id, membership_id);
CREATE INDEX ix_oauth_tokens_grant_id ON public.oauth_tokens (grant_id);
CREATE INDEX ix_oauth_tokens_expires_at ON public.oauth_tokens (expires_at);

COMMENT ON TABLE public.oauth_tokens IS
    'Una fila por token opaco. grant_id agrupa access/refresh y sus rotaciones para revocacion conjunta.';
"""


def upgrade():
    op.add_column('users', sa.Column('is_platform_admin', sa.Boolean(), nullable=False, server_default=sa.false()), schema='public')
    op.create_index('uq_users_single_platform_admin', 'users', ['is_platform_admin'], unique=True, postgresql_where=sa.text('is_platform_admin IS true'), schema='public')
    op.execute(OAUTH_SQL)


def downgrade():
    for table in ('oauth_tokens', 'oauth_authorization_codes', 'oauth_clients'):
        op.drop_table(table, schema='public')
    op.drop_index('uq_users_single_platform_admin', table_name='users', schema='public')
    op.drop_column('users', 'is_platform_admin', schema='public')

