from uuid import UUID
from app.modules.identity.domain.entities import User
from app.modules.audit.application.service import record
from app.shared.application.ports import Passwords, Tokens
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor
from app.shared.domain.errors import Unauthorized


class IdentityService:
    def __init__(self, uow: UnitOfWork, passwords: Passwords, tokens: Tokens):
        self.uow, self.passwords, self.tokens = uow, passwords, tokens

    def login(self, identifier: str, password: str, request_id: UUID) -> tuple[User, str]:
        user = self.uow.users.by_login(identifier)
        encoded = user.password_hash if user else getattr(self.passwords, 'dummy_hash', '')
        valid = self.passwords.verify(password, encoded)
        if not user or not valid or user.status != 'active':
            record(self.uow, None, 'identity.login', outcome='denied', request_id=request_id)
            self.uow.commit()
            raise Unauthorized('Usuario, correo o contraseña incorrectos.')
        token = self.tokens.issue(user.id, user.credential_stamp)
        record(self.uow, Actor(user.id, request_id), 'identity.login')
        self.uow.commit()
        return user, token
