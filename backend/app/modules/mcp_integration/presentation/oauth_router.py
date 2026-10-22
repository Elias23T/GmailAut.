from datetime import datetime
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import Field, ConfigDict
from app.core.dependencies import ActorDependency, UowDependency, require_administrator
from app.modules.audit.application.service import record
from app.modules.authorization.application.service import AuthorizationService
from app.modules.mcp_integration.application.service import OAuthService, OAuthError
from app.modules.mcp_integration.infrastructure.repository import SQLOAuthRepository
from app.shared.domain.entities import utcnow
from app.shared.presentation.schemas import InputModel

router = APIRouter(tags=['Conexión ChatGPT'])
admin_router = APIRouter(prefix='/admin', tags=['Conexión ChatGPT'], dependencies=[Depends(require_administrator)])


def service(request, uow):
    return OAuthService(uow, SQLOAuthRepository(uow.session), request.app.state.settings, request.app.state.tokens)


class Registration(InputModel):
    model_config = ConfigDict(extra='ignore')
    client_name: str = Field(default='ChatGPT', min_length=1, max_length=120)
    redirect_uris: list[str] = Field(min_length=1, max_length=5)
    token_endpoint_auth_method: str = 'none'
    grant_types: list[str] = ['authorization_code', 'refresh_token']
    response_types: list[str] = ['code']
    scope: Literal['mail:read'] = 'mail:read'


class ConsentRequest(InputModel):
    request: str = Field(min_length=1, max_length=12000)


class Consent(ConsentRequest):
    tenant_id: UUID | None = None
    approve: bool


@router.get('/.well-known/oauth-authorization-server')
def metadata(request: Request):
    base = request.app.state.settings.public_base_url
    return {'issuer': base, 'authorization_endpoint': base + '/oauth/authorize',
            'token_endpoint': base + '/oauth/token', 'registration_endpoint': base + '/oauth/register',
            'revocation_endpoint': base + '/oauth/revoke', 'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'token_endpoint_auth_methods_supported': ['none'],
            'code_challenge_methods_supported': ['S256'], 'scopes_supported': ['mail:read'],
            'authorization_response_iss_parameter_supported': True}


@router.get('/.well-known/oauth-protected-resource')
@router.get('/.well-known/oauth-protected-resource/mcp')
def resource_metadata(request: Request):
    base = request.app.state.settings.public_base_url
    return {'resource': base + '/mcp', 'authorization_servers': [base],
            'scopes_supported': ['mail:read'], 'bearer_methods_supported': ['header']}


@router.post('/oauth/register', status_code=201)
def register(body: Registration, request: Request, uow: UowDependency):
    client = service(request, uow).register(body.client_name, body.redirect_uris,
                                          body.token_endpoint_auth_method, body.grant_types, body.response_types)
    return {'client_id': client.client_id, 'client_name': client.name, 'redirect_uris': client.redirect_uris,
            'token_endpoint_auth_method': 'none', 'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'], 'scope': 'mail:read'}


@router.get('/oauth/authorize')
def authorize(request: Request, uow: UowDependency,
              client_id: str = Query(min_length=1, max_length=256),
              redirect_uri: str = Query(min_length=1, max_length=2048),
              state: str = Query(min_length=1, max_length=1024),
              code_challenge: str = Query(min_length=1, max_length=128),
              resource: str = Query(min_length=1, max_length=2048),
              response_type: str = 'code', code_challenge_method: str = 'S256', scope: str = 'mail:read'):
    parameters = dict(client_id=client_id, redirect_uri=redirect_uri, state=state, code_challenge=code_challenge,
                      resource=resource, response_type=response_type, code_challenge_method=code_challenge_method, scope=scope)
    signed = service(request, uow).prepare(parameters)
    from urllib.parse import urlencode
    return RedirectResponse(request.app.state.settings.frontend_url + '/connect?' + urlencode({'request': signed}), status_code=302,
                            headers={'Referrer-Policy': 'no-referrer'})


@router.post('/oauth/context')
def context(body: ConsentRequest, request: Request, actor: ActorDependency, uow: UowDependency):
    return service(request, uow).context(actor, body.request)


@router.post('/oauth/consent')
def consent(body: Consent, request: Request, actor: ActorDependency, uow: UowDependency):
    return {'redirect_uri': service(request, uow).consent(actor, body.request, body.tenant_id, body.approve)}


async def form_data(request):
    if request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
        raise OAuthError('invalid_request', 'Se requiere application/x-www-form-urlencoded.')
    form = await request.form(max_fields=20, max_files=0)
    if len(form.multi_items()) != len(form) or any(not isinstance(value, str) or len(value) > 4096 for value in form.values()):
        raise OAuthError()
    return dict(form)


@router.post('/oauth/token')
async def token(request: Request, uow: UowDependency):
    from starlette.concurrency import run_in_threadpool
    data = await form_data(request)
    return await run_in_threadpool(service(request, uow).exchange, data)


@router.post('/oauth/revoke')
async def revoke(request: Request, uow: UowDependency):
    from starlette.concurrency import run_in_threadpool
    data = await form_data(request)
    await run_in_threadpool(service(request, uow).revoke, data.get('token', ''), data.get('client_id', ''))
    return {}


@admin_router.get('/connection-settings')
def settings(request: Request):
    config = request.app.state.settings
    return {'mcp_url': config.public_base_url + '/mcp', 'public_https': config.public_base_url.startswith('https://'),
            'redirect_uris': config.oauth_redirect_uris, 'authentication': 'OAuth 2.1 · PKCE S256', 'scope': 'mail:read'}


@admin_router.get('/connections')
def connections(tenant_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    AuthorizationService(uow).member(actor, tenant_id, admin=True)
    result = {}
    for token in SQLOAuthRepository(uow.session).list_tokens(tenant_id):
        if token.grant_id in result or token.token_type != 'refresh':
            continue
        member = uow.memberships.get(tenant_id, token.membership_id)
        user = uow.users.get(member.user_id)
        result[token.grant_id] = {'id': token.grant_id, 'membership_id': member.id, 'name': user.name,
            'email': user.email, 'created_at': token.created_at, 'expires_at': token.expires_at,
            'active': not token.revoked_at and token.expires_at > utcnow() and user.status == 'active' and member.status == 'active'}
    return list(result.values())


@admin_router.delete('/connections/{membership_id}', status_code=204)
def revoke_connection(membership_id: UUID, tenant_id: UUID, request: Request, actor: ActorDependency, uow: UowDependency):
    AuthorizationService(uow).member(actor, tenant_id, admin=True)
    if not uow.memberships.get(tenant_id, membership_id):
        from app.shared.domain.errors import NotFound
        raise NotFound('Cliente no disponible en esta empresa.')
    SQLOAuthRepository(uow.session).revoke_member(membership_id, utcnow())
    record(uow, actor, 'oauth.revoke', tenant_id=tenant_id)
    uow.commit()
