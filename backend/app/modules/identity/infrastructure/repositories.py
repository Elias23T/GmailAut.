from uuid import UUID
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session
from app.modules.identity.domain.entities import User


class SQLUserRepository:
    def __init__(self, session: Session):
        self.session = session

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
