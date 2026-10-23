from uuid import UUID
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session
from app.modules.identity.domain.entities import User
from app.modules.memberships.domain.entities import Membership


class SQLUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_administration(self) -> None:
        # Serializa altas/bajas de administradores y altas de empresas/buzones.
        # Evita dejar cero administradores o perder accesos en altas simultaneas.
        self.session.execute(select(func.pg_advisory_xact_lock(836214105)))

    def administrators(self) -> list[User]:
        return list(self.session.scalars(select(User).where(User.is_platform_admin.is_(True), User.deleted_at.is_(None))
            .order_by(User.created_at, User.id).execution_options(populate_existing=True)))

    def get(self, user_id: UUID) -> User | None:
        return self.session.get(User, user_id, populate_existing=True)

    def by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(func.lower(User.email) == email.lower()))

    def by_login(self, identifier: str) -> User | None:
        normalized = identifier.strip().lower()
        return self.session.scalar(select(User).where(or_(func.lower(User.email) == normalized,
                                                         func.lower(User.username) == normalized)))

    def add(self, user: User) -> None:
        self.session.add(user)

    def available_clients(self, tenant_id: UUID) -> list[User]:
        linked = select(Membership.id).where(Membership.user_id == User.id, Membership.tenant_id == tenant_id).exists()
        return list(self.session.scalars(select(User).where(
            User.is_platform_admin.is_(False), User.deleted_at.is_(None), User.email.is_not(None), ~linked,
        ).order_by(func.lower(User.name), User.id)))

    def all_clients(self) -> list[User]:
        return list(self.session.scalars(select(User).where(
            User.is_platform_admin.is_(False), User.deleted_at.is_(None),
        ).order_by(func.lower(User.name), User.id).execution_options(populate_existing=True)))
