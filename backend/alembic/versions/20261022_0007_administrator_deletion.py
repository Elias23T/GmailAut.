"""Retirada de cuentas administradoras conservando la auditoria y sus permisos otorgados."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_0007'
down_revision = '20261022_0006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(timezone=True)), schema='public')
    op.create_check_constraint('ck_users_deleted_disabled', 'users', "deleted_at IS NULL OR status = 'disabled'", schema='public')


def downgrade():
    op.drop_constraint('ck_users_deleted_disabled', 'users', schema='public', type_='check')
    op.drop_column('users', 'deleted_at', schema='public')
