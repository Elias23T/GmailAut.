from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations

from test_api import api_client, register, company, mailbox
from app.main import create_app
from app.modules.identity.domain.entities import User
from app.shared.infrastructure.database import Database


def create_administrator(client, headers, **changes):
    body = {'name': 'Administrador de prueba', 'username': 'admin_' + uuid4().hex[:12],
            'password': 'adm123', **changes}
    return client.post('/admin/administrators', headers=headers, json=body)


def admin_login(client, user):
    response = client.post('/auth/login', json={'username': user['username'], 'password': 'adm123'})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_new_administrators_manage_existing_and_future_companies_and_mailboxes(api_client):
    client, connection, _ = api_client
    owner, headers = register(client)
    tenant = company(client, headers)
    box = mailbox(client, headers, tenant)
    result = create_administrator(client, headers, email='admin_' + uuid4().hex + '@example.com')
    assert result.status_code == 201, result.text
    admin = result.json()
    assert admin['is_platform_admin'] and admin['status'] == 'active'
    assert 'password' not in result.text and 'auth_version' not in result.text
    other_headers = admin_login(client, admin)
    assert len(client.get('/admin/administrators', headers=other_headers).json()) == 2
    companies = client.get('/tenants', headers=other_headers).json()
    assert companies[0]['id'] == tenant['id']
    listed = client.get('/tenants/' + tenant['id'] + '/mailboxes', headers=other_headers).json()
    assert listed[0]['id'] == box['id'] and listed[0]['can_read'] is True
    assert client.post(f"/tenants/{tenant['id']}/mailboxes/{box['id']}/check", headers=other_headers).status_code == 200
    future = company(client, other_headers)
    assert future['id'] in [item['id'] for item in client.get('/tenants', headers=headers).json()]
    future_box = mailbox(client, headers, future)
    boxes = client.get('/tenants/' + future['id'] + '/mailboxes', headers=other_headers).json()
    assert boxes[0]['id'] == future_box['id'] and boxes[0]['can_read'] is True
    assert client.patch('/tenants/' + tenant['id'], headers=other_headers, json={'name': 'Empresa administrada'}).status_code == 200
    assert create_administrator(client, other_headers).status_code == 201
    assert connection.execute(text("select count(*) from audit_events where action='administrator.create'")).scalar_one() == 2
    events = client.get('/tenants/' + tenant['id'] + '/audit', headers=headers).text
    assert 'adm123' not in events


def test_only_administrators_can_create_manage_and_list_administrators(api_client):
    client, _, _ = api_client
    owner, headers = register(client)
    tenant = company(client, headers)
    customer = client.post('/admin/clients', headers=headers, json={'tenant_id': tenant['id'],
        'name': 'Cliente de prueba', 'email': uuid4().hex + '@example.com', 'password': 'private-client-password'}).json()
    login = client.post('/auth/login', json={'email': customer['email'], 'password': 'private-client-password'}).json()
    customer_headers = {'Authorization': 'Bearer ' + login['access_token']}
    assert client.get('/admin/administrators').status_code == 401
    assert client.get('/admin/administrators', headers=customer_headers).status_code == 403
    assert create_administrator(client, customer_headers).status_code == 403
    assert client.patch('/admin/administrators/' + owner['id'] + '/status', headers=customer_headers, json={'status': 'disabled'}).status_code == 403
    assert client.patch('/admin/administrators/' + owner['id'], headers=customer_headers, json={'name': 'No permitido'}).status_code == 403
    assert client.delete('/admin/administrators/' + owner['id'], headers=customer_headers).status_code == 403
    assert client.patch('/admin/administrators/' + customer['id'] + '/status', headers=headers, json={'status': 'disabled'}).status_code == 404
    username = 'admin_' + uuid4().hex[:12]
    first = create_administrator(client, headers, username=username)
    assert first.status_code == 201
    duplicate = create_administrator(client, headers, username=username.upper())
    assert duplicate.status_code == 409 and 'usuario' in duplicate.json()['detail']
    assert create_administrator(client, headers, email=owner['email']).status_code == 409
    assert create_administrator(client, headers, username='bad@name').status_code == 422
    assert create_administrator(client, headers, password='short').status_code == 422
    assert create_administrator(client, headers, is_platform_admin=False).status_code == 422


def test_last_administrator_and_self_deactivation_are_protected_and_old_sessions_stay_revoked(api_client):
    client, _, _ = api_client
    owner, headers = register(client)
    owner_path = '/admin/administrators/' + owner['id'] + '/status'
    denied = client.patch(owner_path, headers=headers, json={'status': 'disabled'})
    assert denied.status_code == 409 and 'último administrador' in denied.json()['detail']
    admin = create_administrator(client, headers).json()
    other_headers = admin_login(client, admin)
    denied = client.patch(owner_path, headers=headers, json={'status': 'disabled'})
    assert denied.status_code == 403 and 'propia cuenta' in denied.json()['detail']
    assert client.patch(owner_path, headers=other_headers, json={'status': 'disabled'}).status_code == 200
    assert client.get('/admin/administrators', headers=headers).status_code == 401
    assert client.post('/auth/login', json={'email': owner['email'], 'password': 'private-user-password'}).status_code == 401
    denied = client.patch('/admin/administrators/' + admin['id'] + '/status', headers=other_headers, json={'status': 'disabled'})
    assert denied.status_code == 409
    assert client.patch(owner_path, headers=other_headers, json={'status': 'active'}).status_code == 200
    assert client.get('/admin/administrators', headers=headers).status_code == 401
    assert client.post('/auth/login', json={'email': owner['email'], 'password': 'private-user-password'}).status_code == 200


def test_migration_backfills_missing_administrator_company_and_mailbox_access(api_client):
    client, connection, _ = api_client
    owner, headers = register(client)
    tenant = company(client, headers)
    box = mailbox(client, headers, tenant)
    connection.execute(text('DELETE FROM mailbox_grants'))
    connection.execute(text('DELETE FROM memberships'))
    # Recrea solamente los elementos de esquema que cambia la revision.
    connection.execute(text('ALTER TABLE users DROP CONSTRAINT ck_users_auth_version'))
    connection.execute(text('ALTER TABLE users DROP COLUMN auth_version'))
    connection.execute(text('CREATE UNIQUE INDEX uq_users_single_platform_admin ON users(is_platform_admin) WHERE is_platform_admin IS TRUE'))
    revision = Path(__file__).parents[1] / 'alembic/versions/20261022_0006_multiple_administrators.py'
    spec = importlib.util.spec_from_file_location('administrator_migration', revision)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
    assert client.get('/tenants', headers=headers).json()[0]['id'] == tenant['id']
    boxes = client.get('/tenants/' + tenant['id'] + '/mailboxes', headers=headers).json()
    assert boxes[0]['id'] == box['id'] and boxes[0]['can_read'] is True
    assert connection.execute(text('SELECT auth_version FROM users WHERE id=:id'), {'id': owner['id']}).scalar_one() == 1


def test_concurrent_deactivation_cannot_remove_both_active_administrators(api_client):
    fixture_client, _, _ = api_client
    settings = fixture_client.app.state.settings
    database = Database(settings)
    users = [User(name='Administrador de prueba', username='race_' + uuid4().hex[:12],
        password_hash=fixture_client.app.state.passwords.hash('adm123'), is_platform_admin=True) for _ in range(2)]
    try:
        with database.session() as session:
            session.add_all(users)
            session.commit()
        tokens = [fixture_client.app.state.tokens.issue(user.id, user.credential_stamp) for user in users]
        barrier = Barrier(2)
        with TestClient(create_app(settings)) as client:
            def deactivate(index):
                barrier.wait(timeout=10)
                return client.patch('/admin/administrators/' + str(users[1-index].id) + '/status',
                    headers={'Authorization': 'Bearer ' + tokens[index]}, json={'status': 'disabled'}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(deactivate, (0, 1)))
        assert results.count(200) == 1 and all(code in (200, 401) for code in results), results
        with database.session() as session:
            assert session.execute(text('SELECT count(*) FROM users WHERE is_platform_admin AND status=\'active\'')).scalar_one() == 1
    finally:
        with database.session() as session:
            for user in users:
                session.execute(text('DELETE FROM audit_events WHERE actor_user_id=:id'), {'id': user.id})
                session.execute(text('DELETE FROM users WHERE id=:id'), {'id': user.id})
            session.commit()
        database.dispose()


def test_editing_preserves_password_when_omitted_and_invalidates_old_credentials_when_changed(api_client):
    client, connection, _ = api_client
    _, headers = register(client)
    admin = create_administrator(client, headers, email='edit_' + uuid4().hex + '@example.com').json()
    admin_headers = admin_login(client, admin)
    path = '/admin/administrators/' + admin['id']
    password_hash = connection.execute(text('SELECT password_hash FROM users WHERE id=:id'), {'id': admin['id']}).scalar_one()
    result = client.patch(path, headers=headers, json={'name': 'Nombre actualizado'})
    assert result.status_code == 200 and result.json()['name'] == 'Nombre actualizado'
    assert connection.execute(text('SELECT password_hash FROM users WHERE id=:id'), {'id': admin['id']}).scalar_one() == password_hash
    assert client.get('/auth/me', headers=admin_headers).status_code == 200
    new_username = 'edited_' + uuid4().hex[:12]
    result = client.patch(path, headers=headers, json={'username': new_username.upper(), 'email': None, 'password': 'new123'})
    assert result.status_code == 200, result.text
    assert result.json()['username'] == new_username and result.json()['email'] is None
    assert 'password' not in result.text and 'deleted_at' not in result.text
    assert client.get('/auth/me', headers=admin_headers).status_code == 401
    assert client.post('/auth/login', json={'username': admin['username'], 'password': 'adm123'}).status_code == 401
    assert client.post('/auth/login', json={'username': new_username, 'password': 'adm123'}).status_code == 401
    assert client.post('/auth/login', json={'username': new_username, 'password': 'new123'}).status_code == 200


def test_administrator_edit_validates_uniqueness_and_self_edits_require_new_login(api_client):
    client, _, _ = api_client
    owner, headers = register(client)
    admin = create_administrator(client, headers).json()
    path = '/admin/administrators/' + admin['id']
    other = create_administrator(client, headers).json()
    assert client.patch(path, headers=headers, json={'username': other['username']}).status_code == 409
    assert client.patch(path, headers=headers, json={'email': owner['email']}).status_code == 409
    for body in ({}, {'name': ''}, {'username': None}, {'password': None}, {'password': 'short'}, {'is_platform_admin': False}, {'status': 'disabled'}):
        assert client.patch(path, headers=headers, json=body).status_code == 422
    self_path = '/admin/administrators/' + owner['id']
    assert client.patch(self_path, headers=headers, json={'email': None}).status_code == 422
    assert client.patch(self_path, headers=headers, json={'name': 'Nombre de prueba'}).status_code == 200
    assert client.get('/auth/me', headers=headers).json()['name'] == 'Nombre de prueba'
    assert client.patch(self_path, headers=headers, json={'password': 'own123'}).status_code == 200
    assert client.get('/auth/me', headers=headers).status_code == 401
    assert client.post('/auth/login', json={'email': owner['email'], 'password': 'own123'}).status_code == 200


def test_admin_deletion_requires_deactivation_and_preserves_audit_companies_and_client_grants(api_client):
    client, connection, _ = api_client
    owner, headers = register(client)
    admin = create_administrator(client, headers, email='removed_' + uuid4().hex + '@example.com').json()
    admin_headers = admin_login(client, admin)
    tenant = company(client, admin_headers)
    box = mailbox(client, admin_headers, tenant)
    box_path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    assert client.post(box_path + '/check', headers=admin_headers).status_code == 200
    customer = client.post('/admin/clients', headers=admin_headers, json={'tenant_id': tenant['id'], 'name': 'Cliente de prueba',
        'email': uuid4().hex + '@example.com', 'password': 'private-client-password'}).json()
    assert client.post(box_path + '/grants', headers=admin_headers, json={'membership_id': customer['membership_id']}).status_code == 201
    original_events = connection.execute(text('SELECT count(*) FROM audit_events WHERE actor_user_id=:id'), {'id': admin['id']}).scalar_one()
    secret = connection.execute(text('SELECT encrypted_secret FROM mailbox_credentials WHERE mailbox_id=:id'), {'id': box['id']}).scalar_one()
    path = '/admin/administrators/' + admin['id']
    denied = client.delete(path, headers=headers)
    assert denied.status_code == 409 and 'desactiva' in denied.json()['detail']
    assert client.delete('/admin/administrators/' + owner['id'], headers=headers).status_code == 403
    assert client.delete('/admin/administrators/' + customer['id'], headers=headers).status_code == 404
    assert client.patch(path + '/status', headers=headers, json={'status': 'disabled'}).status_code == 200
    assert client.delete(path, headers=headers).status_code == 204
    assert admin['id'] not in [item['id'] for item in client.get('/admin/administrators', headers=headers).json()]
    retired = connection.execute(text('SELECT status,deleted_at,email,username FROM users WHERE id=:id'), {'id': admin['id']}).mappings().one()
    assert retired['status'] == 'disabled' and retired['deleted_at'] and retired['email'] is None and retired['username'] != admin['username']
    assert client.get('/auth/me', headers=admin_headers).status_code == 401
    assert client.post('/auth/login', json={'username': admin['username'], 'password': 'adm123'}).status_code == 401
    assert client.patch(path + '/status', headers=headers, json={'status': 'active'}).status_code == 404
    assert client.patch(path, headers=headers, json={'name': 'No recuperable'}).status_code == 404
    assert client.delete(path, headers=headers).status_code == 404
    assert connection.execute(text('SELECT count(*) FROM audit_events WHERE actor_user_id=:id'), {'id': admin['id']}).scalar_one() == original_events
    assert connection.execute(text('SELECT encrypted_secret FROM mailbox_credentials WHERE mailbox_id=:id'), {'id': box['id']}).scalar_one() == secret
    assert client.get('/tenants', headers=headers).json()[0]['id'] == tenant['id']
    login = client.post('/auth/login', json={'email': customer['email'], 'password': 'private-client-password'}).json()
    customer_headers = {'Authorization': 'Bearer ' + login['access_token']}
    assert client.get(box_path + '/messages', headers=customer_headers).status_code == 200
    replacement = create_administrator(client, headers, username=admin['username'], email=admin['email'])
    assert replacement.status_code == 201 and replacement.json()['id'] != admin['id']
