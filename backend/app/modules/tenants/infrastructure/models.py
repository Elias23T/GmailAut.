import sqlalchemy as sa

from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.tenants.domain.entities import Tenant

tenants_table = sa.Table(
    "tenants",
    Base.metadata,
    sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
    sa.Column("name", sa.Text(), sa.CheckConstraint("btrim(name) <> ''"), nullable=False),
    sa.Column("slug", sa.Text(), sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'"), nullable=False, unique=True),
    sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('active', 'suspended', 'disabled')"), nullable=False, server_default=sa.text("'active'")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=utcnow),

)
Base.registry.map_imperatively(Tenant, tenants_table)
