import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.mcp_integration.domain.entities import OAuthClient, AuthorizationCode, OAuthToken

# Las definiciones coinciden con el SQL versionado; ninguna tabla guarda tokens en claro.
def identifier():
    return sa.Column('id', sa.Uuid(), primary_key=True, server_default=sa.text('gen_random_uuid()'))


def moment(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))


clients = sa.Table('oauth_clients', Base.metadata, identifier(),
    sa.Column('client_id', sa.Text(), sa.CheckConstraint("btrim(client_id) <> ''"), unique=True, nullable=False),
    sa.Column('name', sa.Text(), sa.CheckConstraint("btrim(name) <> ''"), nullable=False),
    sa.Column('client_secret_hash', sa.Text()),
    sa.Column('redirect_uris', ARRAY(sa.Text()), nullable=False),
    sa.Column('token_endpoint_auth_method', sa.Text(), sa.CheckConstraint("token_endpoint_auth_method IN ('none', 'client_secret_basic')"), nullable=False, server_default=sa.text("'none'")),
    sa.Column('status', sa.Text(), sa.CheckConstraint("status IN ('active', 'disabled')"), nullable=False, server_default=sa.text("'active'")),
    moment('created_at'), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=utcnow),
    sa.CheckConstraint("cardinality(redirect_uris) > 0 AND array_position(redirect_uris, NULL) IS NULL AND NOT ('' = ANY (redirect_uris))", name='ck_oauth_clients_redirect_uris'),
    sa.CheckConstraint("(token_endpoint_auth_method = 'none' AND client_secret_hash IS NULL) OR (token_endpoint_auth_method = 'client_secret_basic' AND client_secret_hash IS NOT NULL AND btrim(client_secret_hash) <> '')", name='ck_oauth_clients_secret'))


def grant_columns():
    return [sa.Column('client_id', sa.Uuid(), sa.ForeignKey('oauth_clients.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('membership_id', sa.Uuid(), nullable=False),
        sa.Column('resource_uri', sa.Text(), sa.CheckConstraint("btrim(resource_uri) <> ''"), nullable=False),
        sa.Column('scopes', ARRAY(sa.Text()), sa.CheckConstraint("scopes = ARRAY['mail:read']"), nullable=False, server_default=sa.text("ARRAY['mail:read']")),
        moment('created_at'), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False)]


codes = sa.Table('oauth_authorization_codes', Base.metadata, identifier(),
    sa.Column('code_hash', sa.Text(), sa.CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'"), unique=True, nullable=False),
    *grant_columns(), sa.Column('redirect_uri', sa.Text(), sa.CheckConstraint("btrim(redirect_uri) <> ''"), nullable=False),
    sa.Column('code_challenge', sa.Text(), sa.CheckConstraint("code_challenge ~ '^[A-Za-z0-9_-]{43}$'"), nullable=False),
    sa.Column('code_challenge_method', sa.Text(), sa.CheckConstraint("code_challenge_method = 'S256'"), nullable=False, server_default=sa.text("'S256'")),
    sa.Column('consumed_at', sa.DateTime(timezone=True)),
    sa.ForeignKeyConstraint(['tenant_id', 'membership_id'], ['memberships.tenant_id', 'memberships.id'], name='fk_oauth_codes_membership', ondelete='CASCADE'),
    sa.CheckConstraint('expires_at > created_at', name='ck_oauth_codes_expiry'),
    sa.CheckConstraint('consumed_at IS NULL OR consumed_at >= created_at', name='ck_oauth_codes_consumed'))

tokens = sa.Table('oauth_tokens', Base.metadata, identifier(),
    sa.Column('token_hash', sa.Text(), sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'"), unique=True, nullable=False),
    sa.Column('token_type', sa.Text(), sa.CheckConstraint("token_type IN ('access', 'refresh')"), nullable=False),
    sa.Column('grant_id', sa.Uuid(), nullable=False), *grant_columns(),
    sa.Column('revoked_at', sa.DateTime(timezone=True)),
    sa.ForeignKeyConstraint(['tenant_id', 'membership_id'], ['memberships.tenant_id', 'memberships.id'], name='fk_oauth_tokens_membership', ondelete='CASCADE'),
    sa.CheckConstraint('expires_at > created_at', name='ck_oauth_tokens_expiry'),
    sa.CheckConstraint('revoked_at IS NULL OR revoked_at >= created_at', name='ck_oauth_tokens_revocation'),
    comment='Una fila por token opaco. grant_id agrupa access/refresh y sus rotaciones para revocacion conjunta.')
for table, prefix in ((codes, 'oauth_codes'), (tokens, 'oauth_tokens')):
    for suffix, columns in (('client_id', ['client_id']), ('tenant_membership', ['tenant_id', 'membership_id']), ('expires_at', ['expires_at'])):
        sa.Index(f'ix_{prefix}_{suffix}', *(table.c[name] for name in columns))
sa.Index('ix_oauth_tokens_grant_id', tokens.c.grant_id)
for entity, table in ((OAuthClient, clients), (AuthorizationCode, codes), (OAuthToken, tokens)):
    Base.registry.map_imperatively(entity, table)
