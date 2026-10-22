from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.shared.domain.errors import ApplicationError


class AuthLimiter:
    """Limite local y acotado por proceso; no mantiene sesiones de usuario."""
    def __init__(self):
        self.attempts = OrderedDict()
        self.lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        with self.lock:
            entries = self.attempts.setdefault(key, deque())
            while entries and entries[0] <= now - 60:
                entries.popleft()
            self.attempts.move_to_end(key)
            if len(self.attempts) > 10000:
                self.attempts.popitem(last=False)
            if len(entries) >= 10:
                return False
            entries.append(now)
            return True


def configure_http(application, settings):
    from fastapi.middleware.cors import CORSMiddleware
    application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                               allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                               allow_headers=['Authorization', 'Content-Type', 'MCP-Protocol-Version'], expose_headers=['X-Request-ID', 'WWW-Authenticate'])
    limiter = AuthLimiter()

    @application.middleware('http')
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid4()
        if request.method in ('POST', 'PATCH'):
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 65536:
                    return JSONResponse(status_code=413, content={'detail': 'La solicitud excede el tamaño permitido.'})
            request._body = bytes(data)
        if request.method == 'POST' and request.url.path.rstrip('/') in ('/auth/login', '/oauth/register', '/oauth/token', '/oauth/revoke') and not limiter.allow(request.url.path + ':' + (request.client.host if request.client else 'unknown')):
            response = JSONResponse(status_code=429, content={'detail': 'Demasiados intentos. Intenta nuevamente en un minuto.', 'code': 'rate_limited'}, headers={'Retry-After': '60'})
        else:
            response = await call_next(request)
        response.headers['X-Request-ID'] = str(request.state.request_id)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @application.exception_handler(ApplicationError)
    async def application_error(request: Request, error: ApplicationError):
        codes = {'not_found': 404, 'forbidden': 403, 'unauthorized': 401, 'conflict': 409,
                 'invalid_input': 422, 'unavailable': 503, 'too_large': 413}
        return JSONResponse(status_code=codes.get(error.code, 400),
                            content={'detail': str(error), 'code': error.code, 'request_id': str(request.state.request_id)},
                            headers={'WWW-Authenticate': 'Bearer'} if error.code == 'unauthorized' else None)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        # No reflejar input ni contexto: los formularios contienen passwords y secretos IMAP.
        return JSONResponse(status_code=422, content={
            'detail': 'Revisa los datos enviados.', 'code': 'validation_error',
            'errors': [{'field': '.'.join(str(item) for item in entry['loc']), 'message': entry['msg']} for entry in error.errors()],
        })

    @application.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error: IntegrityError):
        return JSONResponse(status_code=409, content={'detail': 'El registro ya existe o está relacionado con otros datos.', 'code': 'conflict'})

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        return JSONResponse(status_code=503, content={'detail': 'No se pudo completar la operación con la base de datos.', 'code': 'database_unavailable'})
