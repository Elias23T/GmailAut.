"""Composicion de adaptadores REST y MCP sobre los mismos casos de uso."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.dependencies import get_db_session
from app.shared.infrastructure.database import Database
from app.shared.infrastructure.security import ArgonPasswords, JWTokens, AESMailboxCipher
from app.modules.mail_access.infrastructure.imap_reader import TLSMailReader
from app.modules.mail_sending.infrastructure.smtp_sender import SMTPMailSender
from app.modules.mail_sending.presentation.router import router as sending_router
from app.core.http import configure_http
from app.modules.identity.presentation.router import router as identity_router
from app.modules.tenants.presentation.router import router as tenant_router
from app.modules.identity.presentation.admin_router import router as admin_router
from app.modules.mcp_integration.presentation.oauth_router import router as oauth_router, admin_router as connection_router
from app.modules.mcp_integration.presentation.server import create_mcp
from app.modules.mcp_integration.application.service import OAuthError
from fastapi.responses import JSONResponse
from app.modules.mailboxes.presentation.router import router as mailbox_router
from app.modules.authorization.presentation.router import router as authorization_router
from app.modules.audit.presentation.router import router as audit_router
from app.modules.mail_access.presentation.router import router as mail_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(settings)
        application.state.database = database
        application.state.settings = settings
        application.state.passwords = ArgonPasswords()
        application.state.tokens = JWTokens(settings.jwt_secret.get_secret_value() if settings.jwt_secret else None, settings.jwt_minutes)
        application.state.cipher = AESMailboxCipher(settings.mailbox_encryption_key.get_secret_value() if settings.mailbox_encryption_key else None, settings.mailbox_encryption_key_version)
        application.state.mail_reader = TLSMailReader(settings.imap_timeout, settings.imap_max_message_bytes, settings.imap_allow_private_hosts)
        application.state.mail_sender = SMTPMailSender(settings.smtp_timeout, settings.smtp_allow_private_hosts)
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            database.dispose()

    application = FastAPI(title="Corporate Mail AI", version="0.2.0", lifespan=lifespan)
    mcp, mcp_application = create_mcp(settings, application.state)
    configure_http(application, settings)
    for router in (identity_router, admin_router, oauth_router, connection_router, tenant_router, mailbox_router, authorization_router, audit_router, mail_router, sending_router):
        application.include_router(router)

    @application.exception_handler(OAuthError)
    async def oauth_error(request: Request, error: OAuthError):
        return JSONResponse(status_code=error.status, content={'error': error.code, 'error_description': error.description},
                            headers={'Cache-Control': 'no-store'})

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Confirma que el proceso HTTP responde."""
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"], responses={503: {"description": "PostgreSQL no disponible"}})
    def readiness(session: Annotated[Session, Depends(get_db_session)]) -> dict[str, str]:
        """Comprueba la conexion sin leer datos de clientes ni modificar el esquema."""
        try:
            session.execute(text("SELECT 1")).scalar_one()
            revision = session.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one_or_none()
            if revision != '20261023_0008':
                raise HTTPException(status_code=503, detail='Falta aplicar la migración 20261023_0008 con Alembic.')
        except SQLAlchemyError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Base de datos no disponible.",
            ) from None
        return {"status": "ok", "database": "ok"}

    application.mount('/', mcp_application)
    return application


app = create_app()
