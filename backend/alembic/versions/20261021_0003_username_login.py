"""Acceso por usuario o correo sin crear tablas adicionales."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_0003'
down_revision = '20261021_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('username', sa.Text(), nullable=True), schema='public')
    op.alter_column('users', 'email', existing_type=sa.Text(), nullable=True, schema='public')
    op.create_check_constraint('ck_users_login_identifier', 'users', 'email IS NOT NULL OR username IS NOT NULL', schema='public')
    op.create_check_constraint('ck_users_username_format', 'users', "username IS NULL OR username ~ '^[a-z][a-z0-9_.-]{2,31}$'", schema='public')
    op.create_index('uq_users_username_normalized', 'users', [sa.text('lower(username)')], unique=True, schema='public')


def downgrade():
    # PostgreSQL rechazara SET NOT NULL si existen cuentas sin correo: asociarles
    # uno real antes del downgrade. No inventar emails ni eliminar usuarios.
    op.alter_column('users', 'email', existing_type=sa.Text(), nullable=False, schema='public')
    op.drop_index('uq_users_username_normalized', table_name='users', schema='public')
    op.drop_constraint('ck_users_username_format', 'users', type_='check', schema='public')
    op.drop_constraint('ck_users_login_identifier', 'users', type_='check', schema='public')
    op.drop_column('users', 'username', schema='public')
