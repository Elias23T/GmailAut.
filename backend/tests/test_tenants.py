import pytest
from sqlalchemy import text

from test_api import api_client, register, company, mailbox
from test_oauth_mcp import setup_client, authorize, exchange, rpc, RESOURCE


def test_company_identifier_is_automatic_unique_and_stable_on_rename(api_client):
    client, _, _ = api_client
    _, headers = register(client)
    first = client.post('/tenants', headers=headers, json={'name': '  Organización de prueba  '})
    second = client.post('/tenants', headers=headers, json={'name': 'Organización de prueba'})
    assert first.status_code == second.status_code == 201
    original, duplicate_name = first.json(), second.json()
    assert original['name'] == 'Organización de prueba'
    assert original['id'] != duplicate_name['id'] and original['slug'] != duplicate_name['slug']
    assert original['slug'] and len(original['slug']) <= 64
    renamed = client.patch('/tenants/' + original['id'], headers=headers, json={'name': 'Empresa renombrada'})
    assert renamed.status_code == 200
    assert renamed.json()['id'] == original['id'] and renamed.json()['slug'] == original['slug']
    assert renamed.json()['name'] == 'Empresa renombrada'
    for invalid in ({}, {'name': ''}, {'name': '   '}):
        assert client.post('/tenants', headers=headers, json=invalid).status_code == 422


def test_company_management_and_active_deletion_guard(api_client):
    client, connection, _ = api_client
    _, headers = register(client)
    tenant = company(client, headers)
    other = company(client, headers)
    path = '/tenants/' + tenant['id']
    denied = client.delete(path, headers=headers)
    assert denied.status_code == 409
    assert 'activa' in denied.json()['detail'] and 'desact' in denied.json()['detail']
    assert connection.execute(text('SELECT count(*) FROM public.tenants')).scalar_one() == 2
    renamed = client.patch(path, headers=headers, json={'name': 'Renamed Company'})
    assert renamed.status_code == 200 and renamed.json()['name'] == 'Renamed Company'
    duplicate = client.patch(path, headers=headers, json={'slug': other['slug']})
    assert duplicate.status_code == 409 and 'identificador' in duplicate.json()['detail']
    for invalid in ({}, {'name': None}, {'name': '   '}, {'slug': 'INVALID'}):
        assert client.patch(path, headers=headers, json=invalid).status_code == 422
    assert client.patch(path + '/status', headers=headers, json={'status': 'disabled'}).status_code == 200
    listed = client.get('/tenants', headers=headers).json()
    assert next(item for item in listed if item['id'] == tenant['id'])['status'] == 'disabled'
    assert client.get(path + '/mailboxes', headers=headers).status_code == 404
    assert client.patch(path, headers=headers, json={'name': 'Disabled renamed'}).status_code == 200
    assert client.patch(path + '/status', headers=headers, json={'status': 'active'}).status_code == 200
    assert client.get(path + '/mailboxes', headers=headers).status_code == 200
    assert client.delete(path, headers=headers).status_code == 409
    _, customer_headers = register(client, administrator=False)
    assert client.get('/tenants', headers=customer_headers).status_code == 403
    assert client.patch(path, headers=customer_headers, json={'name': 'Hacked'}).status_code == 403
    assert client.patch(path + '/status', headers=customer_headers, json={'status': 'disabled'}).status_code == 403
    assert client.delete(path, headers=customer_headers).status_code == 403


def test_deactivation_revokes_existing_and_pending_oauth_authorizations(api_client):
    client, _, _ = api_client
    headers, tenant, _, _, customer_headers, client_id = setup_client(client)
    tokens = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    pending_code = authorize(client, client_id, customer_headers, tenant)
    path = f"/tenants/{tenant['id']}/status"
    assert client.patch(path, headers=headers, json={'status': 'disabled'}).status_code == 200
    assert rpc(client, tokens['access_token'], 'tools/list').status_code == 401
    assert client.patch(path, headers=headers, json={'status': 'active'}).status_code == 200
    assert rpc(client, tokens['access_token'], 'tools/list').status_code == 401
    assert exchange(client, client_id, pending_code).status_code == 400
    refresh = client.post('/oauth/token', data={'grant_type': 'refresh_token', 'client_id': client_id,
        'refresh_token': tokens['refresh_token'], 'resource': RESOURCE})
    assert refresh.status_code == 400
    assert exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).status_code == 200


def test_disabled_company_cascades_only_its_data_and_keeps_shared_accounts(api_client):
    client, connection, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    assert exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).status_code == 200
    authorize(client, client_id, customer_headers, tenant)
    other = company(client, headers)
    other_box = mailbox(client, headers, other)
    assert client.post(f"/tenants/{other['id']}/mailboxes/{other_box['id']}/check", headers=headers).status_code == 200
    linked = client.post('/admin/clients/link', headers=headers, json={'tenant_id': other['id'], 'email': customer['email']})
    assert linked.status_code == 201, linked.text
    assert client.post(f"/tenants/{other['id']}/mailboxes/{other_box['id']}/grants", headers=headers,
        json={'membership_id': linked.json()['membership_id']}).status_code == 201
    other_tokens = exchange(client, client_id, authorize(client, client_id, customer_headers, other)).json()
    path = '/tenants/' + tenant['id']
    assert client.patch(path + '/status', headers=headers, json={'status': 'disabled'}).status_code == 200
    for table in ('memberships', 'mailboxes', 'mailbox_grants', 'audit_events', 'oauth_authorization_codes', 'oauth_tokens'):
        assert connection.execute(text(f'SELECT count(*) FROM public.{table} WHERE tenant_id = :id'), {'id': tenant['id']}).scalar_one() > 0
    assert client.delete(path, headers=headers).status_code == 204
    for table in ('memberships', 'mailboxes', 'mailbox_grants', 'audit_events', 'oauth_authorization_codes', 'oauth_tokens'):
        assert connection.execute(text(f'SELECT count(*) FROM public.{table} WHERE tenant_id = :id'), {'id': tenant['id']}).scalar_one() == 0
    assert connection.execute(text('SELECT count(*) FROM public.mailbox_credentials WHERE mailbox_id = :id'), {'id': box['id']}).scalar_one() == 0
    assert connection.execute(text('SELECT count(*) FROM public.users')).scalar_one() == 2
    assert connection.execute(text('SELECT count(*) FROM public.oauth_clients')).scalar_one() == 1
    assert client.get('/auth/me', headers=customer_headers).status_code == 200
    assert client.get(f"/tenants/{other['id']}/mailboxes", headers=headers).status_code == 200
    assert rpc(client, other_tokens['access_token'], 'tools/list').status_code == 200
    assert connection.execute(text("SELECT count(*) FROM public.audit_events WHERE action = 'tenant.delete' AND tenant_id IS NULL")).scalar_one() == 1
    assert client.delete(path, headers=headers).status_code == 404


def test_cascade_with_restricted_application_role_preserves_direct_audit_protection(api_client):
    client, connection, _ = api_client
    _, headers = register(client)
    tenant = company(client, headers)
    box = mailbox(client, headers, tenant)
    assert client.patch(f"/tenants/{tenant['id']}/status", headers=headers, json={'status': 'disabled'}).status_code == 200
    assert not connection.execute(text("SELECT has_table_privilege('corporate_mail_app', 'public.audit_events', 'DELETE')")).scalar_one()
    connection.execute(text('SET LOCAL ROLE corporate_mail_app'))
    try:
        connection.execute(text('DELETE FROM public.tenants WHERE id = :id AND status = :status'), {'id': tenant['id'], 'status': 'disabled'})
        assert connection.execute(text('SELECT count(*) FROM public.audit_events WHERE tenant_id = :id'), {'id': tenant['id']}).scalar_one() == 0
        assert connection.execute(text('SELECT count(*) FROM public.mailbox_credentials WHERE mailbox_id = :id'), {'id': box['id']}).scalar_one() == 0
    finally:
        connection.execute(text('RESET ROLE'))


def test_company_deletion_rolls_back_when_global_audit_write_fails(api_client, monkeypatch):
    from app.modules.audit.infrastructure.repositories import SQLAuditRepository
    client, connection, _ = api_client
    _, headers = register(client)
    tenant = company(client, headers)
    box = mailbox(client, headers, tenant)
    path = '/tenants/' + tenant['id']
    assert client.patch(path + '/status', headers=headers, json={'status': 'disabled'}).status_code == 200
    def fail_audit(self, event):
        raise RuntimeError('Simulated audit failure')
    monkeypatch.setattr(SQLAuditRepository, 'add', fail_audit)
    with pytest.raises(RuntimeError, match='Simulated audit failure'):
        client.delete(path, headers=headers)
    assert connection.execute(text('SELECT count(*) FROM public.tenants WHERE id = :id'), {'id': tenant['id']}).scalar_one() == 1
    assert connection.execute(text('SELECT count(*) FROM public.mailbox_credentials WHERE mailbox_id = :id'), {'id': box['id']}).scalar_one() == 1
