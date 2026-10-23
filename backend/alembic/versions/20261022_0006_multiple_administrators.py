"""Administradores multiples con acceso compartido y revocacion de sesiones."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_0006'
down_revision = '20261022_0005'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('uq_users_single_platform_admin', table_name='users', schema='public')
    op.add_column('users', sa.Column('auth_version', sa.Integer(), nullable=False, server_default=sa.text('1')), schema='public')
    op.create_check_constraint('ck_users_auth_version', 'users', 'auth_version > 0', schema='public')
    # Todos los administradores gestionan las empresas existentes. Los accesos
    # de los clientes y los permisos de envio permanecen como estaban.
    op.execute("""
        INSERT INTO public.memberships (tenant_id, user_id, role)
        SELECT t.id, u.id, 'owner' FROM public.tenants t CROSS JOIN public.users u
        WHERE u.is_platform_admin
        ON CONFLICT (tenant_id, user_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO public.mailbox_grants (tenant_id, membership_id, mailbox_id)
        SELECT b.tenant_id, m.id, b.id FROM public.mailboxes b
        JOIN public.memberships m ON m.tenant_id = b.tenant_id
        JOIN public.users u ON u.id = m.user_id
        WHERE u.is_platform_admin
        ON CONFLICT (membership_id, mailbox_id) DO NOTHING
    """)


def downgrade():
    # Falla de forma atomica si existen varios administradores; nunca elimina
    # ni degrada cuentas para poder recrear el indice unico anterior.
    op.create_index('uq_users_single_platform_admin', 'users', ['is_platform_admin'],
                    unique=True, postgresql_where=sa.text('is_platform_admin IS true'), schema='public')
    op.drop_constraint('ck_users_auth_version', 'users', schema='public', type_='check')
    op.drop_column('users', 'auth_version', schema='public')
