"""Dependencias de entrada HTTP; el dominio no importa FastAPI."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.shared.infrastructure.database import Database
from typing import Annotated
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.shared.infrastructure.unit_of_work import SQLUnitOfWork
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor
from app.shared.domain.errors import Unauthorized, Forbidden
from app.modules.identity.domain.entities import User


def get_db_session(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    with database.session() as session:
        yield session


def get_uow(session: Annotated[Session, Depends(get_db_session)]) -> UnitOfWork:
    return SQLUnitOfWork(session)


UowDependency = Annotated[UnitOfWork, Depends(get_uow)]
bearer = HTTPBearer(auto_error=False)


def get_current_user(request: Request, uow: UowDependency,
                     credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if not credential or credential.scheme.lower() != 'bearer':
        raise Unauthorized('Inicia sesión para continuar.')
    user_id = request.app.state.tokens.subject(credential.credentials)
    user = uow.users.get(user_id)
    if not user or user.status != 'active':
        raise Unauthorized('La cuenta no está disponible.')
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_administrator(user: CurrentUser) -> User:
    if not user.is_platform_admin:
        raise Forbidden('Esta sección está reservada al administrador de la plataforma.')
    return user


Administrator = Annotated[User, Depends(require_administrator)]


def get_actor(request: Request, user: CurrentUser) -> Actor:
    return Actor(user.id, request.state.request_id)


ActorDependency = Annotated[Actor, Depends(get_actor)]
