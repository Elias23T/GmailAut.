from uuid import uuid4

from sqlalchemy import text

from test_api import api_client, register, company, mailbox
from test_oauth_mcp import setup_client, authorize, exchange, prepare, rpc
from urllib.parse import parse_qs, urlsplit


def create_customer(client, headers, tenant):
    response = client.post('/admin/clients', headers=headers, json={
        'tenant_id': tenant['id'], 'name': 'Cliente de prueba',
        'email': f'{uuid4().hex}@example.com', 'password': 'private-user-password',
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_orphaned_clients_can_be_listed_and_relinked_without_resetting_credentials(api_client):
    client, connection, _ = api_client
    _, headers = register(client)
    original, destination = company(client, headers), company(client, headers)
    customer = create_customer(client, headers, original)
    already_linked = create_customer(client, headers, destination)
    original_hash = connection.execute(text('SELECT password_hash FROM users WHERE id=:id'), {'id': customer['id']}).scalar_one()
    box = mailbox(client, headers, original)
    assert client.post(f"/tenants/{original['id']}/mailboxes/{box['id']}/grants", headers=headers,
                       json={'membership_id': customer['membership_id']}).status_code == 201
    assert client.patch(f"/tenants/{original['id']}/status", headers=headers, json={'status': 'disabled'}).status_code == 200
    assert client.delete('/tenants/' + original['id'], headers=headers).status_code == 204

    available_path = '/admin/clients/available?tenant_id=' + destination['id']
    result = client.get(available_path, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json() == [{'id': customer['id'], 'name': customer['name'], 'email': customer['email'], 'username': None, 'status': 'active'}]
    assert 'password' not in result.text and 'encrypted_secret' not in result.text
    before = client.get('/admin/clients?tenant_id=' + destination['id'], headers=headers).json()
    assert [account['id'] for account in before] == [already_linked['id']]

    link_body = {'tenant_id': destination['id'], 'email': customer['email']}
    linked = client.post('/admin/clients/link', headers=headers, json=link_body)
    assert linked.status_code == 201, linked.text
    assert linked.json()['id'] == customer['id']
    assert linked.json()['membership_id'] != customer['membership_id']
    assert client.get(available_path, headers=headers).json() == []
    assert len(client.get('/admin/clients?tenant_id=' + destination['id'], headers=headers).json()) == 2
    assert connection.execute(text('SELECT password_hash FROM users WHERE id=:id'), {'id': customer['id']}).scalar_one() == original_hash
    assert connection.execute(text('SELECT count(*) FROM mailbox_grants WHERE membership_id=:id'), {'id': linked.json()['membership_id']}).scalar_one() == 0
    assert client.post('/auth/login', json={'email': customer['email'], 'password': 'private-user-password'}).status_code == 200
    assert client.post('/admin/clients/link', headers=headers, json=link_body).json()['membership_id'] == linked.json()['membership_id']
    assert connection.execute(text("SELECT count(*) FROM audit_events WHERE action='client.link'")).scalar_one() == 1


def test_available_clients_are_restricted_to_an_administrator_of_the_selected_company(api_client):
    client, _, _ = api_client
    _, headers = register(client)
    tenant = company(client, headers)
    customer = create_customer(client, headers, tenant)
    login = client.post('/auth/login', json={'email': customer['email'], 'password': 'private-user-password'}).json()
    customer_headers = {'Authorization': 'Bearer ' + login['access_token']}
    path = '/admin/clients/available?tenant_id=' + tenant['id']
    assert client.get(path).status_code == 401
    assert client.get(path, headers=customer_headers).status_code == 403
    assert client.get('/admin/clients/available?tenant_id=' + str(uuid4()), headers=headers).status_code == 404
    assert client.get('/admin/clients/available', headers=headers).status_code == 422
    assert client.patch(f"/tenants/{tenant['id']}/status", headers=headers, json={'status': 'disabled'}).status_code == 200
    assert client.get(path, headers=headers).status_code == 404


def test_duplicate_creation_explains_linking_and_link_does_not_reactivate_suspended_accounts(api_client):
    client, connection, _ = api_client
    owner, headers = register(client)
    original, destination = company(client, headers), company(client, headers)
    customer = create_customer(client, headers, original)
    body = {'tenant_id': destination['id'], 'name': 'Nombre que no debe reemplazar al cliente',
            'email': customer['email'], 'password': 'replacement-password'}
    duplicate = client.post('/admin/clients', headers=headers, json=body)
    assert duplicate.status_code == 409 and 'Vincular' in duplicate.json()['detail']
    body['tenant_id'] = original['id']
    duplicate = client.post('/admin/clients', headers=headers, json=body)
    assert duplicate.status_code == 409 and 'ya está vinculado' in duplicate.json()['detail']
    body['email'] = owner['email']
    assert 'administrador' in client.post('/admin/clients', headers=headers, json=body).json()['detail']
    assert connection.execute(text('SELECT name FROM users WHERE id=:id'), {'id': customer['id']}).scalar_one() == customer['name']
    assert client.patch(f"/admin/clients/{customer['id']}?tenant_id={original['id']}", headers=headers, json={'status': 'disabled'}).status_code == 204
    accounts = client.get('/admin/clients/available?tenant_id=' + destination['id'], headers=headers).json()
    assert accounts[0]['status'] == 'disabled'
    linked = client.post('/admin/clients/link', headers=headers, json={'tenant_id': destination['id'], 'email': customer['email']})
    assert linked.status_code == 201 and linked.json()['status'] == 'disabled'
    assert client.post('/auth/login', json={'email': customer['email'], 'password': 'private-user-password'}).status_code == 401


def test_client_username_login_is_separate_from_administrator_and_mailbox_password(api_client):
    client, connection, _ = api_client
    _, headers = register(client)
    tenant = company(client, headers)
    username = 'customer_' + uuid4().hex[:10]
    body = {'tenant_id': tenant['id'], 'name': 'Cliente de prueba', 'email': uuid4().hex + '@example.com',
            'username': ' ' + username.upper() + ' ', 'password': 'cli123'}
    result = client.post('/admin/clients', headers=headers, json=body)
    assert result.status_code == 201, result.text
    customer = result.json()
    assert customer['username'] == username
    assert 'password' not in result.text
    login = client.post('/auth/login', json={'username': username.upper(), 'password': body['password']})
    assert login.status_code == 200 and not login.json()['user']['is_platform_admin']
    customer_headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    assert client.get('/admin/clients?tenant_id=' + tenant['id'], headers=customer_headers).status_code == 403
    assert client.post('/auth/login', json={'username': username, 'password': 'private-imap-password'}).status_code == 401
    assert client.post('/auth/login', json={'email': body['email'], 'password': body['password']}).status_code == 200
    assert connection.execute(text('select password_hash from users where id=:id'), {'id': customer['id']}).scalar_one() != body['password']
    body['email'] = uuid4().hex + '@example.com'
    duplicate = client.post('/admin/clients', headers=headers, json=body)
    assert duplicate.status_code == 409 and 'usuario' in duplicate.json()['detail']
    body['username'] = 'invalid@username'
    assert client.post('/admin/clients', headers=headers, json=body).status_code == 422


def test_client_credentials_changes_revoke_oauth_in_all_companies_without_touching_mailbox_secrets(api_client):
    client, connection, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    other = company(client, headers)
    linked = client.post('/admin/clients/link', headers=headers, json={'tenant_id': other['id'], 'email': customer['email']}).json()
    other_box = mailbox(client, headers, other)
    path = f"/tenants/{other['id']}/mailboxes/{other_box['id']}"
    assert client.post(path + '/check', headers=headers).status_code == 200
    assert client.post(path + '/grants', headers=headers, json={'membership_id': linked['membership_id']}).status_code == 201
    access = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()['access_token']
    other_access = exchange(client, client_id, authorize(client, client_id, customer_headers, other)).json()['access_token']
    pending = prepare(client, client_id)
    signed = parse_qs(urlsplit(pending.headers['location']).query)['request'][0]
    pending_code = client.post('/oauth/consent', headers=customer_headers, json={'request': signed, 'tenant_id': tenant['id'], 'approve': True}).json()
    pending_code = parse_qs(urlsplit(pending_code['redirect_uri']).query)['code'][0]
    original_secret = connection.execute(text('select encrypted_secret from mailbox_credentials where mailbox_id=:id'), {'id': box['id']}).scalar_one()
    credentials_path = f"/admin/clients/{customer['id']}/credentials?tenant_id={tenant['id']}"
    username = 'customer_' + uuid4().hex[:10]
    response = client.patch(credentials_path, headers=headers, json={'username': username, 'password': 'new456'})
    assert response.status_code == 200, response.text
    assert response.json()['username'] == username and 'password' not in response.text
    assert rpc(client, access, 'tools/list').status_code == 401
    assert rpc(client, other_access, 'tools/list').status_code == 401
    assert exchange(client, client_id, pending_code).status_code == 400
    assert client.post('/auth/login', json={'email': customer['email'], 'password': 'private-client-password'}).status_code == 401
    login = client.post('/auth/login', json={'username': username, 'password': 'new456'})
    assert login.status_code == 200
    assert connection.execute(text('select encrypted_secret from mailbox_credentials where mailbox_id=:id'), {'id': box['id']}).scalar_one() == original_secret
    events = client.get('/tenants/' + tenant['id'] + '/audit', headers=headers).text
    assert 'client.credentials' in events and 'new456' not in events
    assert client.get('/auth/me', headers=customer_headers).status_code == 401
    new_headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    assert client.patch(credentials_path, headers=new_headers, json={'username': username}).status_code == 403
    assert client.patch(credentials_path.replace(tenant['id'], str(uuid4())), headers=headers, json={'username': username}).status_code == 404
    assert client.patch(credentials_path, headers=headers, json={'username': username, 'password': 'short'}).status_code == 422
    # Dejar la contraseña ausente la conserva; no hay restablecimientos implícitos.
    assert client.patch(credentials_path, headers=headers, json={'username': username}).status_code == 200
    assert client.post('/auth/login', json={'username': username, 'password': 'new456'}).status_code == 200


def test_orphaned_username_is_visible_globally_and_can_be_retired_to_allow_reuse(api_client):
    client, connection, _ = api_client
    owner, headers = register(client)
    original = company(client, headers)
    username = 'orphan_' + uuid4().hex[:12]
    email = uuid4().hex + '@example.com'
    body = {'tenant_id': original['id'], 'name': 'Cliente de prueba', 'username': username, 'email': email, 'password': 'cli123'}
    customer = client.post('/admin/clients', headers=headers, json=body).json()
    login = client.post('/auth/login', json={'username': username, 'password': 'cli123'}).json()
    old_headers = {'Authorization': 'Bearer ' + login['access_token']}
    assert client.patch('/tenants/' + original['id'] + '/status', headers=headers, json={'status': 'disabled'}).status_code == 200
    assert client.delete('/tenants/' + original['id'], headers=headers).status_code == 204
    # La vista global funciona incluso sin ninguna empresa creada.
    accounts = client.get('/admin/clients/all', headers=headers)
    assert accounts.status_code == 200, accounts.text
    assert accounts.json() == [{'id': customer['id'], 'name': customer['name'], 'username': username,
        'email': email, 'status': 'active', 'companies': []}]
    assert owner['id'] not in accounts.text and 'password' not in accounts.text
    destination = company(client, headers)
    assert client.get('/admin/clients?tenant_id=' + destination['id'], headers=headers).json() == []
    body.update(tenant_id=destination['id'], email=uuid4().hex + '@example.com')
    conflict = client.post('/admin/clients', headers=headers, json=body)
    assert conflict.status_code == 409 and 'sin empresa' in conflict.json()['detail'] and 'listado de Clientes' in conflict.json()['detail']
    path = '/admin/clients/' + customer['id']
    denied = client.delete(path, headers=headers)
    assert denied.status_code == 409 and 'suspende' in denied.json()['detail']
    assert client.patch(path + '/status', headers=headers, json={'status': 'disabled'}).status_code == 204
    assert client.get('/auth/me', headers=old_headers).status_code == 401
    original_events = connection.execute(text('SELECT count(*) FROM audit_events WHERE actor_user_id=:id'), {'id': customer['id']}).scalar_one()
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get('/admin/clients/all', headers=headers).json() == []
    assert client.get('/admin/clients/available?tenant_id=' + destination['id'], headers=headers).json() == []
    assert client.patch(path + '/status', headers=headers, json={'status': 'active'}).status_code == 404
    assert client.delete(path, headers=headers).status_code == 404
    assert client.post('/auth/login', json={'username': username, 'password': 'cli123'}).status_code == 401
    assert connection.execute(text('SELECT count(*) FROM audit_events WHERE actor_user_id=:id'), {'id': customer['id']}).scalar_one() == original_events
    body['email'] = email
    replacement = client.post('/admin/clients', headers=headers, json=body)
    assert replacement.status_code == 201 and replacement.json()['id'] != customer['id']


def test_global_client_management_is_admin_only_and_retiring_shared_accounts_hides_all_memberships(api_client):
    client, _, _ = api_client
    owner, headers = register(client)
    original, destination = company(client, headers), company(client, headers)
    customer = create_customer(client, headers, original)
    assert client.post('/admin/clients/link', headers=headers, json={'tenant_id': destination['id'], 'email': customer['email']}).status_code == 201
    login = client.post('/auth/login', json={'email': customer['email'], 'password': 'private-user-password'}).json()
    customer_headers = {'Authorization': 'Bearer ' + login['access_token']}
    path = '/admin/clients/' + customer['id']
    assert client.get('/admin/clients/all').status_code == 401
    assert client.get('/admin/clients/all', headers=customer_headers).status_code == 403
    assert client.patch(path + '/status', headers=customer_headers, json={'status': 'disabled'}).status_code == 403
    assert client.delete(path, headers=customer_headers).status_code == 403
    assert client.delete('/admin/clients/' + owner['id'], headers=headers).status_code == 403
    accounts = client.get('/admin/clients/all', headers=headers).json()
    assert {company['id'] for company in accounts[0]['companies']} == {original['id'], destination['id']}
    assert client.patch(path + '/status', headers=headers, json={'status': 'disabled'}).status_code == 204
    assert client.patch(path + '/status', headers=headers, json={'status': 'active'}).status_code == 204
    assert client.get('/auth/me', headers=customer_headers).status_code == 401
    assert client.patch(path + '/status', headers=headers, json={'status': 'disabled'}).status_code == 204
    assert client.delete(path, headers=headers).status_code == 204
    for tenant in (original, destination):
        assert client.get('/admin/clients?tenant_id=' + tenant['id'], headers=headers).json() == []
        assert client.get('/admin/clients/available?tenant_id=' + tenant['id'], headers=headers).json() == []


def test_orphan_credentials_can_be_configured_from_the_global_client_list(api_client):
    client, _, _ = api_client
    owner, headers = register(client)
    original = company(client, headers)
    customer = create_customer(client, headers, original)
    login = client.post('/auth/login', json={'email': customer['email'], 'password': 'private-user-password'}).json()
    customer_headers = {'Authorization': 'Bearer ' + login['access_token']}
    assert client.patch('/tenants/' + original['id'] + '/status', headers=headers, json={'status': 'disabled'}).status_code == 200
    assert client.delete('/tenants/' + original['id'], headers=headers).status_code == 204
    username = 'orphan_' + uuid4().hex[:12]
    path = '/admin/clients/' + customer['id'] + '/credentials'
    assert client.patch(path, json={'username': username, 'password': 'cli123'}).status_code == 401
    assert client.patch(path, headers=customer_headers, json={'username': username, 'password': 'cli123'}).status_code == 403
    assert client.patch('/admin/clients/' + owner['id'] + '/credentials', headers=headers, json={'username': username}).status_code == 403
    response = client.patch(path, headers=headers, json={'username': username, 'password': 'cli123'})
    assert response.status_code == 200, response.text
    assert response.json()['username'] == username and 'password' not in response.text
    assert client.get('/auth/me', headers=customer_headers).status_code == 401
    assert client.post('/auth/login', json={'username': username, 'password': 'cli123'}).status_code == 200
    assert client.get('/admin/clients/all', headers=headers).json()[0]['companies'] == []


def test_bulk_retirement_removes_reviewed_suspended_clients_and_revokes_connections(api_client):
    client, connection, _ = api_client
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    token = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()['access_token']
    active = create_customer(client, headers, tenant)
    original = company(client, headers)
    orphan = create_customer(client, headers, original)
    assert client.patch('/tenants/' + original['id'] + '/status', headers=headers, json={'status': 'disabled'}).status_code == 200
    assert client.delete('/tenants/' + original['id'], headers=headers).status_code == 204
    reviewed = [customer['id'], orphan['id']]
    for user_id in reviewed:
        assert client.patch('/admin/clients/' + user_id + '/status', headers=headers, json={'status': 'disabled'}).status_code == 204
    # A newly suspended account was not part of the administrator's confirmation.
    later = create_customer(client, headers, tenant)
    assert client.patch('/admin/clients/' + later['id'] + '/status', headers=headers, json={'status': 'disabled'}).status_code == 204
    grant_count = connection.execute(text('SELECT count(*) FROM mailbox_grants')).scalar_one()
    event_count = connection.execute(text('SELECT count(*) FROM audit_events')).scalar_one()
    result = client.post('/admin/clients/delete-disabled', headers=headers, json={'user_ids': reviewed, 'confirmed': True})
    assert result.status_code == 200, result.text
    assert result.json() == {'deleted_count': 2}
    accounts = client.get('/admin/clients/all', headers=headers).json()
    assert {account['id'] for account in accounts} == {active['id'], later['id']}
    assert client.get('/auth/me', headers=headers).status_code == 200
    for account in (customer, orphan):
        retired = connection.execute(text('SELECT deleted_at, email, auth_version FROM users WHERE id=:id'), {'id': account['id']}).one()
        assert retired.deleted_at is not None and retired.email is None and retired.auth_version >= 2
        assert client.post('/auth/login', json={'email': account['email'], 'password': 'private-user-password'}).status_code == 401
    assert rpc(client, token, 'tools/list').status_code == 401
    assert connection.execute(text('SELECT count(*) FROM mailbox_grants')).scalar_one() == grant_count
    assert connection.execute(text('SELECT count(*) FROM audit_events')).scalar_one() >= event_count + 2
    assert connection.execute(text("SELECT count(*) FROM audit_events WHERE action='client.delete'")).scalar_one() == 2
    assert client.get(f"/tenants/{tenant['id']}/mailboxes", headers=headers).json()[0]['id'] == box['id']


def test_bulk_retirement_rejects_stale_or_protected_accounts_without_partial_deletion(api_client):
    client, connection, _ = api_client
    owner, headers = register(client)
    tenant = company(client, headers)
    first, second = create_customer(client, headers, tenant), create_customer(client, headers, tenant)
    for account in (first, second):
        assert client.patch('/admin/clients/' + account['id'] + '/status', headers=headers, json={'status': 'disabled'}).status_code == 204
    assert client.patch('/admin/clients/' + second['id'] + '/status', headers=headers, json={'status': 'active'}).status_code == 204
    for other_id in (second['id'], owner['id'], str(uuid4())):
        result = client.post('/admin/clients/delete-disabled', headers=headers,
                             json={'user_ids': [first['id'], other_id], 'confirmed': True})
        assert result.status_code == 409 and 'No se eliminó ninguna' in result.json()['detail']
        assert connection.execute(text('SELECT deleted_at FROM users WHERE id=:id'), {'id': first['id']}).scalar_one() is None
    assert client.patch('/admin/clients/' + second['id'] + '/status', headers=headers, json={'status': 'disabled'}).status_code == 204
    assert client.delete('/admin/clients/' + second['id'], headers=headers).status_code == 204
    result = client.post('/admin/clients/delete-disabled', headers=headers,
                         json={'user_ids': [first['id'], second['id']], 'confirmed': True})
    assert result.status_code == 409
    assert connection.execute(text('SELECT deleted_at FROM users WHERE id=:id'), {'id': first['id']}).scalar_one() is None
    assert connection.execute(text("SELECT count(*) FROM audit_events WHERE action='client.delete'")).scalar_one() == 1


def test_bulk_retirement_requires_administrator_and_explicit_valid_confirmation(api_client):
    client, _, _ = api_client
    _, headers = register(client)
    tenant = company(client, headers)
    customer = create_customer(client, headers, tenant)
    login = client.post('/auth/login', json={'email': customer['email'], 'password': 'private-user-password'}).json()
    customer_headers = {'Authorization': 'Bearer ' + login['access_token']}
    path = '/admin/clients/delete-disabled'
    body = {'user_ids': [customer['id']], 'confirmed': True}
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, headers=customer_headers, json=body).status_code == 403
    for invalid in ({'user_ids': [customer['id']]}, {'user_ids': [customer['id']], 'confirmed': False},
                    {'user_ids': [], 'confirmed': True}, {'user_ids': [customer['id']] * 2, 'confirmed': True}):
        assert client.post(path, headers=headers, json=invalid).status_code == 422
