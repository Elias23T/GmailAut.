"""Eliminacion en cascada de datos pertenecientes a una empresa.

La regla de desactivar primero se valida en el caso de uso bajo bloqueo.
No borra empresas, no agrega tablas y no crea triggers de aplicacion.
"""
from alembic import op

revision = '20261021_0004'
down_revision = '20261021_0003'
branch_labels = None
depends_on = None

CONSTRAINTS = (
    ('memberships_tenant_id_fkey', 'memberships', 'tenants', ['tenant_id'], ['id']),
    ('mailboxes_tenant_id_fkey', 'mailboxes', 'tenants', ['tenant_id'], ['id']),
    ('mailbox_credentials_mailbox_id_fkey', 'mailbox_credentials', 'mailboxes', ['mailbox_id'], ['id']),
    ('mailbox_grants_tenant_id_fkey', 'mailbox_grants', 'tenants', ['tenant_id'], ['id']),
    ('fk_mailbox_grants_membership', 'mailbox_grants', 'memberships', ['tenant_id', 'membership_id'], ['tenant_id', 'id']),
    ('fk_mailbox_grants_mailbox', 'mailbox_grants', 'mailboxes', ['tenant_id', 'mailbox_id'], ['tenant_id', 'id']),
    ('fk_mailbox_grants_grantor', 'mailbox_grants', 'memberships', ['tenant_id', 'granted_by_membership_id'], ['tenant_id', 'id']),
    ('audit_events_tenant_id_fkey', 'audit_events', 'tenants', ['tenant_id'], ['id']),
    ('fk_audit_events_mailbox', 'audit_events', 'mailboxes', ['tenant_id', 'mailbox_id'], ['tenant_id', 'id']),
    ('oauth_authorization_codes_tenant_id_fkey', 'oauth_authorization_codes', 'tenants', ['tenant_id'], ['id']),
    ('fk_oauth_codes_membership', 'oauth_authorization_codes', 'memberships', ['tenant_id', 'membership_id'], ['tenant_id', 'id']),
    ('oauth_tokens_tenant_id_fkey', 'oauth_tokens', 'tenants', ['tenant_id'], ['id']),
    ('fk_oauth_tokens_membership', 'oauth_tokens', 'memberships', ['tenant_id', 'membership_id'], ['tenant_id', 'id']),
)


def replace_foreign_keys(action):
    for name, source, target, local, remote in CONSTRAINTS:
        op.drop_constraint(name, source, type_='foreignkey', schema='public')
        op.create_foreign_key(name, source, target, local, remote,
                             source_schema='public', referent_schema='public', ondelete=action)


def upgrade():
    replace_foreign_keys('CASCADE')


def downgrade():
    replace_foreign_keys('RESTRICT')
