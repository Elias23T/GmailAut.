import base64
from datetime import timedelta
import hashlib
import json
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from sqlalchemy import select, text

from test_api import api_client, register, company, mailbox
from app.modules.mcp_integration.domain.entities import OAuthToken, AuthorizationCode
from app.modules.mcp_integration.application.service import digest
from app.shared.domain.entities import utcnow

CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'
RESOURCE = 'http://127.0.0.1:8000/mcp'
VERIFIER = 'v' * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b'=').decode()


def setup_client(client):
    admin, headers = register(client)
    tenant = company(client, headers)
    box = mailbox(client, headers, tenant)
    path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    assert client.post(path + '/check', headers=headers).status_code == 200
    email = uuid4().hex + '@example.com'
    response = client.post('/admin/clients', headers=headers, json={
        'tenant_id': tenant['id'], 'name': 'Cliente de prueba', 'email': email, 'password': 'private-client-password'})
    assert response.status_code == 201, response.text
    customer = response.json()
    assert client.post(path + '/grants', headers=headers, json={'membership_id': customer['membership_id']}).status_code == 201
    login = client.post('/auth/login', json={'email': email, 'password': 'private-client-password'}).json()
    customer_headers = {'Authorization': 'Bearer ' + login['access_token']}
    registration = client.post('/oauth/register', json={'client_name': 'ChatGPT', 'redirect_uris': [CALLBACK]})
    assert registration.status_code == 201, registration.text
    return headers, tenant, box, customer, customer_headers, registration.json()['client_id']


def prepare(client, client_id, **overrides):
    parameters = {'client_id': client_id, 'redirect_uri': CALLBACK, 'response_type': 'code',
        'resource': RESOURCE, 'state': 'original-state', 'scope': 'mail:read',
        'code_challenge': CHALLENGE, 'code_challenge_method': 'S256', **overrides}
    return client.get('/oauth/authorize', params=parameters, follow_redirects=False)


def authorize(client, client_id, customer_headers, tenant, scope='mail:read'):
    redirect = prepare(client, client_id, scope=scope)
    assert redirect.status_code == 302, redirect.text
    request = parse_qs(urlsplit(redirect.headers['location']).query)['request'][0]
    context = client.post('/oauth/context', headers=customer_headers, json={'request': request})
    assert context.status_code == 200, context.text
    assert str(tenant['id']) in [str(item['id']) for item in context.json()['tenants']]
    consent = client.post('/oauth/consent', headers=customer_headers,
        json={'request': request, 'tenant_id': tenant['id'], 'approve': True})
    assert consent.status_code == 200, consent.text
    result = parse_qs(urlsplit(consent.json()['redirect_uri']).query)
    assert result['state'] == ['original-state'] and result['iss'] == ['http://127.0.0.1:8000']
    return result['code'][0]


def exchange(client, client_id, code, **overrides):
    return client.post('/oauth/token', data={'grant_type': 'authorization_code', 'client_id': client_id,
        'code': code, 'redirect_uri': CALLBACK, 'resource': RESOURCE, 'code_verifier': VERIFIER, **overrides})


def rpc(client, token, method, params=None):
    return client.post('/mcp', headers={'Authorization': 'Bearer ' + token,
        'Accept': 'application/json, text/event-stream', 'Host': '127.0.0.1:8000'},
        json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})


def call(client, token, name, arguments=None):
    return rpc(client, token, 'tools/call', {'name': name, 'arguments': arguments or {}})


def test_complete_oauth_mcp_flow_is_read_only_scoped_and_audited(api_client):
    client, connection, reader = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    resource = client.get('/.well-known/oauth-protected-resource/mcp').json()
    assert resource['resource'] == RESOURCE
    metadata = client.get('/.well-known/oauth-authorization-server').json()
    assert metadata['code_challenge_methods_supported'] == ['S256']
    code = authorize(client, client_id, customer_headers, tenant)
    response = exchange(client, client_id, code)
    assert response.status_code == 200, response.text
    access = response.json()['access_token']
    raw_tokens = connection.execute(text('SELECT token_hash FROM public.oauth_tokens')).scalars().all()
    assert access not in raw_tokens and digest(access) in raw_tokens
    assert rpc(client, customer_headers['Authorization'][7:], 'tools/list').status_code == 401
    assert client.get('/auth/me', headers={'Authorization': 'Bearer ' + access}).status_code == 401
    initialized = rpc(client, access, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}})
    assert initialized.status_code == 200, initialized.text
    tools = rpc(client, access, 'tools/list')
    assert tools.status_code == 200, tools.text
    descriptions = {item['name']: item for item in tools.json()['result']['tools']}
    assert set(descriptions) == {'list_mailboxes', 'search_mail', 'read_mail', 'prepare_email', 'send_email'}
    assert all(descriptions[name]['annotations']['readOnlyHint'] for name in ('list_mailboxes', 'search_mail', 'read_mail'))
    assert descriptions['send_email']['annotations']['readOnlyHint'] is False
    assert descriptions['send_email']['annotations']['destructiveHint'] is True
    boxes = call(client, access, 'list_mailboxes')
    assert boxes.status_code == 200 and box['id'] in boxes.text, boxes.text
    searched = call(client, access, 'search_mail', {'mailbox_id': box['id'], 'query': 'Meeting'})
    assert searched.status_code == 200 and 'uid_validity' in searched.text, searched.text
    read = call(client, access, 'read_mail', {'mailbox_id': box['id'], 'uid': 7, 'uid_validity': 91})
    assert read.status_code == 200 and 'Private message body' in read.text, read.text
    events = client.get(f"/tenants/{tenant['id']}/audit", headers=headers)
    assert 'Private message body' not in events.text and access not in events.text
    assert {'mail.search', 'mail.read', 'oauth.authorize'} <= {item['action'] for item in events.json()}
    assert connection.execute(text("SELECT count(*) FROM audit_events WHERE source = 'mcp'")).scalar_one() == 2


def test_consent_explains_unverified_authorized_mailboxes_without_exposing_other_accounts(api_client):
    client, _, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    assert client.patch(path, headers=headers, json={'imap_port': 995}).status_code == 200
    # Otro buzon de la empresa, sin concesion para este cliente, debe permanecer oculto.
    hidden = client.post(f"/tenants/{tenant['id']}/mailboxes", headers=headers, json={
        'email': 'privado@example.com', 'display_name': 'Buzon privado', 'imap_host': 'imap.example.com',
        'username': 'privado@example.com', 'password': 'private-imap-password'})
    assert hidden.status_code == 201
    redirect = prepare(client, client_id)
    signed = parse_qs(urlsplit(redirect.headers['location']).query)['request'][0]
    context = client.post('/oauth/context', headers=customer_headers, json={'request': signed})
    assert context.status_code == 200
    assert context.json()['tenants'] == []
    assert context.json()['unavailable_mailboxes'] == [{'email': box['email'], 'status': 'pending'}]
    assert 'privado@example.com' not in context.text
    assert client.post('/oauth/consent', headers=customer_headers,
                       json={'request': signed, 'tenant_id': tenant['id'], 'approve': True}).status_code == 403
    assert client.patch(path, headers=headers, json={'imap_port': 993}).status_code == 200
    assert client.post(path + '/check', headers=headers).status_code == 200
    refreshed = client.post('/oauth/context', headers=customer_headers, json={'request': signed}).json()
    assert refreshed['unavailable_mailboxes'] == []
    assert refreshed['tenants'][0]['mailboxes'][0]['id'] == box['id']


def test_new_connections_advertise_both_scopes_without_forcing_sending_consent(api_client):
    client, _, _ = api_client
    challenge = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    assert challenge.status_code == 401
    assert 'scope="mail:read mail:send"' in challenge.headers['www-authenticate']
    assert 'resource_metadata=' in challenge.headers['www-authenticate']
    assert 'error=' in challenge.headers['www-authenticate']
    registered = client.post('/oauth/register', json={'client_name': 'ChatGPT', 'redirect_uris': [CALLBACK]})
    assert registered.status_code == 201 and registered.json()['scope'] == 'mail:read mail:send'
    explicit_read = client.post('/oauth/register', json={'redirect_uris': [CALLBACK], 'scope': 'mail:read'})
    assert explicit_read.status_code == 201 and explicit_read.json()['scope'] == 'mail:read'
    headers, tenant, box, _, customer_headers, client_id = setup_client(client)
    params = {'client_id': client_id, 'redirect_uri': CALLBACK, 'response_type': 'code',
              'resource': RESOURCE, 'state': 'new-connection', 'code_challenge': CHALLENGE, 'code_challenge_method': 'S256'}
    redirect = client.get('/oauth/authorize', params=params, follow_redirects=False)
    assert redirect.status_code == 302
    signed = parse_qs(urlsplit(redirect.headers['location']).query)['request'][0]
    context = client.post('/oauth/context', headers=customer_headers, json={'request': signed}).json()
    assert context['scope'] == 'mail:read mail:send'
    # A full request still allows the client to choose read-only consent.
    consent = client.post('/oauth/consent', headers=customer_headers,
                          json={'request': signed, 'tenant_id': tenant['id'], 'approve': True, 'scope': 'mail:read'})
    assert consent.status_code == 200
    code = parse_qs(urlsplit(consent.json()['redirect_uri']).query)['code'][0]
    tokens = exchange(client, client_id, code)
    assert tokens.status_code == 200 and tokens.json()['scope'] == 'mail:read'
    access = tokens.json()['access_token']
    assert rpc(client, access, 'tools/list').status_code == 200
    denied = call(client, access, 'prepare_email', {'mailbox_id': box['id'], 'to': 'destino@example.com', 'subject': 'Prueba', 'body': 'Hola'})
    assert denied.status_code == 200 and denied.json()['result']['isError']
    challenge = denied.json()['result']['_meta']['mcp/www_authenticate']
    assert isinstance(challenge, list) and 'error="insufficient_scope"' in challenge[0]
    assert 'error_description=' in challenge[0] and 'scope="mail:read mail:send"' in challenge[0]


def test_pkce_resource_redirect_and_code_replay_are_enforced(api_client):
    client, _, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    assert client.post('/oauth/register', json={'redirect_uris': ['https://attacker.invalid/callback']}).status_code == 400
    assert prepare(client, client_id, redirect_uri='https://attacker.invalid/callback').status_code == 400
    assert prepare(client, client_id, resource='https://attacker.invalid/mcp').status_code == 400
    assert prepare(client, client_id, code_challenge_method='plain').status_code == 400
    assert prepare(client, client_id, scope='mail:write').status_code == 400
    code = authorize(client, client_id, customer_headers, tenant)
    assert exchange(client, client_id, code, code_verifier='z' * 64).status_code == 400
    assert exchange(client, client_id, code, resource='https://other.invalid/mcp').status_code == 400
    assert exchange(client, client_id, code, redirect_uri=CALLBACK + '?changed=true').status_code == 400
    issued = exchange(client, client_id, code)
    assert issued.status_code == 200, issued.text
    assert exchange(client, client_id, code).status_code == 400
    assert rpc(client, issued.json()['access_token'], 'tools/list').status_code == 401


def test_refresh_rotation_replay_and_expired_tokens(api_client):
    client, _, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    issued = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    data = {'grant_type': 'refresh_token', 'client_id': client_id, 'resource': RESOURCE, 'refresh_token': issued['refresh_token']}
    rotated = client.post('/oauth/token', data=data)
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()['refresh_token'] != issued['refresh_token']
    assert client.post('/oauth/token', data=data).status_code == 400
    assert rpc(client, rotated.json()['access_token'], 'tools/list').status_code == 401
    fresh = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    with client.app.state.database.session() as session:
        row = session.scalar(select(OAuthToken).where(OAuthToken.token_hash == digest(fresh['access_token'])))
        row.created_at = utcnow() - timedelta(hours=2)
        row.expires_at = utcnow() - timedelta(hours=1)
        session.commit()
    assert rpc(client, fresh['access_token'], 'tools/list').status_code == 401


def test_revocation_suspension_and_mailbox_grants_are_rechecked(api_client):
    client, _, reader = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    issued = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    assert client.delete(path + '/grants/' + customer['membership_id'], headers=headers).status_code == 204
    result = call(client, issued['access_token'], 'search_mail', {'mailbox_id': box['id']})
    assert result.json()['result']['isError'] is True, result.text
    assert reader.calls == 1
    assert client.post(path + '/grants', headers=headers, json={'membership_id': customer['membership_id']}).status_code == 201
    assert client.delete(f"/admin/connections/{customer['membership_id']}?tenant_id={tenant['id']}", headers=headers).status_code == 204
    assert rpc(client, issued['access_token'], 'tools/list').status_code == 401
    fresh = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    assert client.patch(f"/admin/clients/{customer['id']}?tenant_id={tenant['id']}", headers=headers, json={'status': 'disabled'}).status_code == 204
    assert rpc(client, fresh['access_token'], 'tools/list').status_code == 401
    assert client.patch(f"/admin/clients/{customer['id']}?tenant_id={tenant['id']}", headers=headers, json={'status': 'active'}).status_code == 204
    assert rpc(client, fresh['access_token'], 'tools/list').status_code == 401


def test_consent_cannot_cross_tenants_and_tampered_requests_are_rejected(api_client):
    client, _, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    other = company(client, headers)
    redirect = prepare(client, client_id)
    signed = parse_qs(urlsplit(redirect.headers['location']).query)['request'][0]
    body = {'request': signed, 'tenant_id': other['id'], 'approve': True}
    assert client.post('/oauth/consent', headers=customer_headers, json=body).status_code == 403
    assert client.post('/oauth/context', headers=customer_headers, json={'request': signed[:-8] + 'tampered'}).status_code == 400
    denied = client.post('/oauth/consent', headers=customer_headers, json={'request': signed, 'approve': False})
    assert denied.status_code == 200
    params = parse_qs(urlsplit(denied.json()['redirect_uri']).query)
    assert params['error'] == ['access_denied'] and params['state'] == ['original-state']
    assert params['iss'] == ['http://127.0.0.1:8000']


def test_mcp_rejects_cross_tenant_mailboxes_and_revocation_during_imap(api_client):
    client, _, reader = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    other_tenant = company(client, headers)
    other_box = mailbox(client, headers, other_tenant)
    issued = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    result = call(client, issued['access_token'], 'search_mail', {'mailbox_id': other_box['id']})
    assert result.json()['result']['isError'] is True, result.text
    original = reader.search
    def revoke_during_read(*args):
        from app.modules.mcp_integration.infrastructure.repository import SQLOAuthRepository
        with client.app.state.database.session() as session:
            SQLOAuthRepository(session).revoke_member(UUID(customer['membership_id']), utcnow())
            session.commit()
        return original(*args)
    from uuid import UUID
    reader.search = revoke_during_read
    result = call(client, issued['access_token'], 'search_mail', {'mailbox_id': box['id']})
    assert result.json()['result']['isError'] is True and 'Meeting' not in result.text, result.text


def test_existing_customer_can_link_two_companies_and_revocation_blocks_pending_code(api_client):
    client, _, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    other = company(client, headers)
    linked = client.post('/admin/clients/link', headers=headers, json={'tenant_id': other['id'], 'email': customer['email']})
    assert linked.status_code == 201 and linked.json()['id'] == customer['id'], linked.text
    other_box = mailbox(client, headers, other)
    path = f"/tenants/{other['id']}/mailboxes/{other_box['id']}"
    assert client.post(path + '/check', headers=headers).status_code == 200
    assert client.post(path + '/grants', headers=headers, json={'membership_id': linked.json()['membership_id']}).status_code == 201
    code = authorize(client, client_id, customer_headers, other)
    assert client.delete(f"/admin/connections/{linked.json()['membership_id']}?tenant_id={other['id']}", headers=headers).status_code == 204
    assert exchange(client, client_id, code).status_code == 400


def test_administrator_cannot_authorize_chatgpt_or_reuse_an_old_administrator_connection(api_client):
    client, connection, _ = api_client
    headers, tenant, _, _, customer_headers, client_id = setup_client(client)
    redirect = prepare(client, client_id)
    signed = parse_qs(urlsplit(redirect.headers['location']).query)['request'][0]
    result = client.post('/oauth/context', headers=headers, json={'request': signed})
    assert result.status_code == 403 and 'cliente' in result.json()['detail']
    assert client.post('/oauth/consent', headers=headers,
        json={'request': signed, 'tenant_id': tenant['id'], 'approve': True}).status_code == 403
    # Representa una autorización del administrador guardada antes del cambio.
    tokens = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    connection.execute(text('UPDATE oauth_tokens SET membership_id=:id'), {'id': tenant['membership_id']})
    assert rpc(client, tokens['access_token'], 'tools/list').status_code == 401
    assert client.post('/oauth/token', data={'grant_type': 'refresh_token', 'client_id': client_id,
        'resource': RESOURCE, 'refresh_token': tokens['refresh_token']}).status_code != 200
    assert client.get('/admin/clients?tenant_id=' + tenant['id'], headers=headers).status_code == 200


def test_client_can_choose_read_only_even_when_sending_was_requested(api_client):
    client, _, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    assert client.patch(path, headers=headers, json={'smtp_enabled': True, 'smtp_host': 'smtp.example.com'}).status_code == 200
    assert client.patch(path + '/grants/' + customer['membership_id'], headers=headers, json={'can_send': True}).status_code == 200
    for scope in ('mail:read', 'mail:read mail:send'):
        redirect = prepare(client, client_id, scope='mail:read mail:send')
        signed = parse_qs(urlsplit(redirect.headers['location']).query)['request'][0]
        context = client.post('/oauth/context', headers=customer_headers, json={'request': signed}).json()
        assert context['tenants'][0]['mailboxes'][0]['can_send'] is True
        result = client.post('/oauth/consent', headers=customer_headers,
            json={'request': signed, 'tenant_id': tenant['id'], 'approve': True, 'scope': scope})
        assert result.status_code == 200, result.text
        code = parse_qs(urlsplit(result.json()['redirect_uri']).query)['code'][0]
        tokens = exchange(client, client_id, code)
        assert tokens.status_code == 200 and tokens.json()['scope'] == scope
        listed = call(client, tokens.json()['access_token'], 'list_mailboxes').json()['result']
        data = listed.get('structuredContent') or json.loads(listed['content'][0]['text'])
        assert data['mailboxes'][0]['can_send'] is ('mail:send' in scope)
        if scope == 'mail:read':
            response = call(client, tokens.json()['access_token'], 'prepare_email',
                {'mailbox_id': box['id'], 'to': 'recipient@example.com', 'subject': 'Test', 'body': 'Test body'})
            assert response.json()['result']['isError'] is True


def test_consent_never_grants_sending_without_admin_permission_or_beyond_requested_scopes(api_client):
    client, connection, _ = api_client
    _, tenant, box, _, customer_headers, client_id = setup_client(client)
    for requested in ('mail:read', 'mail:read mail:send'):
        redirect = prepare(client, client_id, scope=requested)
        signed = parse_qs(urlsplit(redirect.headers['location']).query)['request'][0]
        body = {'request': signed, 'tenant_id': tenant['id'], 'approve': True, 'scope': 'mail:read mail:send'}
        result = client.post('/oauth/consent', headers=customer_headers, json=body)
        assert result.status_code == (400 if requested == 'mail:read' else 403), result.text
        assert connection.execute(text('SELECT count(*) FROM oauth_authorization_codes')).scalar_one() == 0
    body['scope'] = 'mail:read'
    assert client.post('/oauth/consent', headers=customer_headers, json=body).status_code == 200
