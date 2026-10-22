"""Adaptador SQLAlchemy compartido por los repositorios de infraestructura."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings


class Base(DeclarativeBase):
    """Base para futuros modelos ORM; no crea tablas automaticamente."""


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            connect_args={"connect_timeout": settings.database_connect_timeout, "options": "-c search_path=public"},
            echo=False,
            hide_parameters=True,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Cada consumidor obtiene su sesion; el caso de uso decide el commit."""
        with self.session_factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    def dispose(self) -> None:
        """Libera el pool al detener la aplicacion."""
        self.engine.dispose()
