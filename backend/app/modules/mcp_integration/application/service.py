"""Vinculacion OAuth: PKCE obligatorio, audiencia fija y tokens opacos revocables."""
import base64
from datetime import timedelta
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlencode
from uuid import UUID, uuid4

import jwt

from app.modules.audit.application.service import record
from app.modules.authorization.application.service import AuthorizationService
from app.modules.mcp_integration.domain.entities import OAuthClient, AuthorizationCode, OAuthToken
from app.modules.mcp_integration.domain.repository import OAuthRepository
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.entities import Actor, utcnow
from app.shared.domain.errors import Unauthorized, Forbidden


class OAuthError(Exception):
    def __init__(self, code='invalid_request', description='Solicitud OAuth no válida.', status=400):
        self.code, self.description, self.status = code, description, status


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def scopes_of(value: str) -> list[str]:
    requested = value.split()
    if not requested or len(requested) != len(set(requested)) or 'mail:read' not in requested or set(requested) - {'mail:read', 'mail:send'}:
        raise OAuthError('invalid_scope', 'Los permisos admitidos son mail:read y, opcionalmente, mail:send.')
    return [scope for scope in ('mail:read', 'mail:send') if scope in requested]


class OAuthService:
    def __init__(self, uow: UnitOfWork, store: OAuthRepository, settings, tokens):
        self.uow, self.store, self.settings, self.tokens = uow, store, settings, tokens
        self.resource = settings.public_base_url + '/mcp'

    def register(self, name: str, redirect_uris: list[str], method: str, grant_types: list[str], response_types: list[str]):
        # Registro publico acotado a callbacks exactos aprobados por el administrador.
        if not redirect_uris or len(redirect_uris) > 5 or any(uri not in self.settings.oauth_redirect_uris for uri in redirect_uris):
            raise OAuthError('invalid_redirect_uri', 'La URL de retorno no está autorizada.')
        if method != 'none' or set(grant_types) - {'authorization_code', 'refresh_token'} or response_types != ['code']:
            raise OAuthError('invalid_client_metadata', 'Usa un cliente público con PKCE y authorization_code.')
        client = OAuthClient(client_id=secrets.token_urlsafe(32), name=name, redirect_uris=redirect_uris)
        self.store.add(client)
        self.uow.commit()
        return client

    def _client(self, client_id: str):
        client = self.store.client(client_id)
        if not client or client.status != 'active' or client.token_endpoint_auth_method != 'none':
            raise OAuthError('invalid_client', 'Cliente OAuth no disponible.', 401)
        return client

    def prepare(self, parameters: dict) -> str:
        client = self._client(parameters['client_id'])
        if parameters['redirect_uri'] not in client.redirect_uris or parameters['redirect_uri'] not in self.settings.oauth_redirect_uris:
            raise OAuthError('invalid_request', 'La URL de retorno no está autorizada.')
        if parameters.get('response_type') != 'code':
            raise OAuthError('unsupported_response_type')
        if parameters.get('resource') != self.resource:
            raise OAuthError('invalid_target', 'El recurso solicitado no corresponde a este servidor.')
        scopes_of(parameters.get('scope', 'mail:read'))
        if parameters.get('code_challenge_method') != 'S256' or not re.fullmatch(r'[A-Za-z0-9_-]{43}', parameters.get('code_challenge', '')):
            raise OAuthError('invalid_request', 'Se requiere PKCE S256.')
        now = utcnow()
        return jwt.encode({'iss': 'corporate-mail-ai', 'aud': 'corporate-mail-consent',
                           'iat': now, 'exp': now + timedelta(minutes=5), 'jti': str(uuid4()),
                           'parameters': parameters}, self.tokens._key(), algorithm='HS256')

    def request(self, signed: str) -> dict:
        try:
            payload = jwt.decode(signed, self.tokens._key(), algorithms=['HS256'], issuer='corporate-mail-ai',
                                 audience='corporate-mail-consent', options={'require': ['exp', 'iat', 'jti', 'parameters']})
            params = payload['parameters']
            client = self._client(params['client_id'])
            if params['redirect_uri'] not in client.redirect_uris or params['redirect_uri'] not in self.settings.oauth_redirect_uris or params['resource'] != self.resource:
                raise ValueError()
            return payload
        except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
            raise OAuthError('invalid_request', 'La solicitud expiró. Inicia la conexión de nuevo desde ChatGPT.') from None

    def context(self, actor: Actor, signed: str):
        self._customer(actor)
        payload = self.request(signed)
        result = []
        unavailable = []
        for tenant in self.uow.tenants.for_user(actor.user_id):
            member = AuthorizationService(self.uow).member(actor, tenant.id)
            authorized = [box for box in self.uow.mailboxes.list(tenant.id)
                          if self.uow.grants.get(tenant.id, member.id, box.id)]
            boxes = [box for box in authorized if box.status == 'active']
            unavailable.extend({'email': box.email, 'status': box.status} for box in authorized if box.status != 'active')
            if boxes:
                result.append({'id': tenant.id, 'name': tenant.name,
                               'mailboxes': [{'id': box.id, 'email': box.email,
                                   'can_send': bool(box.smtp_enabled and (grant := self.uow.grants.get(tenant.id, member.id, box.id)) and grant.can_send)} for box in boxes]})
        return {'client_name': self._client(payload['parameters']['client_id']).name, 'tenants': result,
                'unavailable_mailboxes': unavailable,
                'scope': ' '.join(scopes_of(payload['parameters'].get('scope', 'mail:read'))), 'expires_at': payload['exp']}

    def _customer(self, actor):
        user = self.uow.users.get(actor.user_id)
        if not user or user.status != 'active':
            raise Unauthorized('La cuenta no está disponible.')
        if user.is_platform_admin:
            raise Forbidden('Conecta ChatGPT con el usuario y la contraseña del cliente. La cuenta de administrador solo gestiona la plataforma.')

    def consent(self, actor: Actor, signed: str, tenant_id: UUID | None, approve: bool, scope: str | None = None):
        self._customer(actor)
        payload = self.request(signed)
        params = payload['parameters']
        callback = {'state': params['state'], 'iss': self.settings.public_base_url}
        if not approve:
            callback['error'] = 'access_denied'
        else:
            requested = scopes_of(params.get('scope', 'mail:read'))
            selected_scopes = scopes_of(scope) if scope is not None else requested
            if not set(selected_scopes) <= set(requested):
                raise OAuthError('invalid_scope', 'Solo puedes autorizar los permisos solicitados por ChatGPT.')
            tenant = next((tenant for tenant in self.context(actor, signed)['tenants'] if str(tenant['id']) == str(tenant_id)), None)
            if not tenant_id or not tenant:
                raise Forbidden('No tienes buzones activos autorizados en esa empresa.')
            if 'mail:send' in selected_scopes and not any(box['can_send'] for box in tenant['mailboxes']):
                raise Forbidden('El administrador todavía no habilitó el envío en tus buzones. Puedes autorizar solo lectura.')
            member = AuthorizationService(self.uow).member(actor, tenant_id)
            self.store.lock_member(member.id)
            AuthorizationService(self.uow).member(actor, tenant_id)
            raw = secrets.token_urlsafe(48)
            self.store.add(AuthorizationCode(id=UUID(payload['jti']), code_hash=digest(raw),
                client_id=self._client(params['client_id']).id, tenant_id=tenant_id, membership_id=member.id,
                redirect_uri=params['redirect_uri'], resource_uri=self.resource,
                code_challenge=params['code_challenge'], scopes=selected_scopes,
                expires_at=utcnow() + timedelta(seconds=90)))
            record(self.uow, actor, 'oauth.authorize', tenant_id=tenant_id)
            self.uow.commit()
            callback['code'] = raw
        separator = '&' if '?' in params['redirect_uri'] else '?'
        return params['redirect_uri'] + separator + urlencode(callback)

    def _member(self, tenant_id, membership_id):
        member = self.uow.memberships.get(tenant_id, membership_id)
        if not member:
            raise Unauthorized('La autorización no está disponible.')
        user = self.uow.users.get(member.user_id)
        if user and user.is_platform_admin:
            raise Unauthorized('Vuelve a conectar ChatGPT con una cuenta de cliente, no con el administrador.')
        AuthorizationService(self.uow).member(Actor(member.user_id, uuid4(), 'mcp'), tenant_id)
        return member

    def _issue(self, client, tenant_id, membership_id, grant_id, refresh_expires, scopes):
        now = utcnow()
        access, refresh = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
        for raw, kind, expiry in ((access, 'access', now + timedelta(minutes=15)), (refresh, 'refresh', refresh_expires)):
            self.store.add(OAuthToken(token_hash=digest(raw), token_type=kind, grant_id=grant_id,
                client_id=client.id, tenant_id=tenant_id, membership_id=membership_id,
                resource_uri=self.resource, expires_at=expiry, scopes=list(scopes)))
        self.uow.commit()
        return {'access_token': access, 'refresh_token': refresh, 'token_type': 'Bearer',
                'expires_in': 900, 'scope': ' '.join(scopes)}

    def exchange(self, data: dict):
        client = self._client(data.get('client_id', ''))
        if data.get('resource') != self.resource:
            raise OAuthError('invalid_target')
        now = utcnow()
        if data.get('grant_type') == 'authorization_code':
            code = self.store.code(digest(data.get('code', '')))
            if not code or code.client_id != client.id:
                raise OAuthError('invalid_grant')
            self.store.lock_member(code.membership_id)
            code = self.store.code(digest(data.get('code', '')), lock=True)
            if not code:
                raise OAuthError('invalid_grant')
            if code.consumed_at:
                # El grant usa el id del codigo: reutilizar un codigo revoca sus tokens.
                self.store.revoke_grant(code.id, now)
                self.uow.commit()
                raise OAuthError('invalid_grant')
            verifier = data.get('code_verifier', '')
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            if (code.expires_at <= now or code.redirect_uri != data.get('redirect_uri') or code.resource_uri != self.resource
                    or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier) or not hmac.compare_digest(challenge, code.code_challenge)):
                raise OAuthError('invalid_grant')
            self._member(code.tenant_id, code.membership_id)
            code.consumed_at = now
            return self._issue(client, code.tenant_id, code.membership_id, code.id, now + timedelta(days=7), code.scopes)
        if data.get('grant_type') == 'refresh_token':
            token = self.store.token(digest(data.get('refresh_token', '')))
            if not token or token.client_id != client.id or token.token_type != 'refresh' or token.resource_uri != self.resource:
                raise OAuthError('invalid_grant')
            self.store.lock_member(token.membership_id)
            token = self.store.token(digest(data.get('refresh_token', '')), lock=True)
            if not token:
                raise OAuthError('invalid_grant')
            if token.revoked_at:
                self.store.revoke_grant(token.grant_id, now)
                self.uow.commit()
                raise OAuthError('invalid_grant', 'El token de renovación ya fue utilizado. Vuelve a conectar.')
            requested = scopes_of(data.get('scope', ' '.join(token.scopes)))
            if token.expires_at <= now or not set(requested) <= set(token.scopes):
                raise OAuthError('invalid_grant')
            self._member(token.tenant_id, token.membership_id)
            token.revoked_at = now
            return self._issue(client, token.tenant_id, token.membership_id, token.grant_id, token.expires_at, requested)
        raise OAuthError('unsupported_grant_type')

    def verify(self, raw: str):
        token = self.store.token(digest(raw))
        if (not token or token.token_type != 'access' or token.revoked_at or token.expires_at <= utcnow()
                or token.resource_uri != self.resource or token.scopes not in (['mail:read'], ['mail:read', 'mail:send'])):
            raise Unauthorized('La conexión con ChatGPT no es válida o expiró.')
        client = self.store.client_by_id(token.client_id)
        if not client or client.status != 'active':
            raise Unauthorized('La conexión con ChatGPT fue deshabilitada.')
        return token, self._member(token.tenant_id, token.membership_id), client

    def revoke(self, raw: str, client_id: str):
        client = self._client(client_id)
        token = self.store.token(digest(raw))
        if token and token.client_id == client.id:
            self.store.lock_member(token.membership_id)
            self.store.revoke_grant(token.grant_id, utcnow())
            self.uow.commit()
