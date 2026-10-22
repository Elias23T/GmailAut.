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


def authorize(client, client_id, customer_headers, tenant):
    redirect = prepare(client, client_id)
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
    assert {item['name'] for item in tools.json()['result']['tools']} == {'list_mailboxes', 'search_mail', 'read_mail'}
    assert all(item['annotations']['readOnlyHint'] for item in tools.json()['result']['tools'])
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
