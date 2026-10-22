import sqlalchemy as sa

from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.identity.domain.entities import User

users_table = sa.Table(
    "users",
    Base.metadata,
    sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
    sa.Column("email", sa.Text(), sa.CheckConstraint("email = btrim(email) AND email <> ''"), nullable=True),
    sa.Column('username', sa.Text(), nullable=True),
    sa.Column("password_hash", sa.Text(), sa.CheckConstraint("btrim(password_hash) <> ''"), nullable=False),
    sa.Column("name", sa.Text(), sa.CheckConstraint("btrim(name) <> ''"), nullable=False),
    sa.Column('is_platform_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('active', 'disabled')"), nullable=False, server_default=sa.text("'active'")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=utcnow),

    sa.CheckConstraint('email IS NOT NULL OR username IS NOT NULL', name='ck_users_login_identifier'),
    sa.CheckConstraint("username IS NULL OR username ~ '^[a-z][a-z0-9_.-]{2,31}$'", name='ck_users_username_format'),
)
Base.registry.map_imperatively(User, users_table)
sa.Index('uq_users_single_platform_admin', users_table.c.is_platform_admin, unique=True,
         postgresql_where=users_table.c.is_platform_admin.is_(True))

sa.Index('uq_users_email_normalized', sa.func.lower(users_table.c.email), unique=True)
sa.Index('uq_users_username_normalized', sa.func.lower(users_table.c.username), unique=True)
