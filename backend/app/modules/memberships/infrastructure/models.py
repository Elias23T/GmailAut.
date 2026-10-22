import sqlalchemy as sa

from app.shared.infrastructure.database import Base
from app.shared.domain.entities import utcnow
from app.modules.memberships.domain.entities import Membership

memberships_table = sa.Table(
    "memberships",
    Base.metadata,
    sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
    sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
    sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("role", sa.Text(), sa.CheckConstraint("role IN ('owner', 'admin', 'member')"), nullable=False, server_default=sa.text("'member'")),
    sa.Column("status", sa.Text(), sa.CheckConstraint("status IN ('active', 'disabled')"), nullable=False, server_default=sa.text("'active'")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), onupdate=utcnow),
    sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_memberships_tenant_id"),

)
Base.registry.map_imperatively(Membership, memberships_table)

sa.Index('ix_memberships_user_id', memberships_table.c.user_id)
