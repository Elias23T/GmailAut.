import base64
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.dependencies import get_db_session
from app.main import create_app
from app.modules.mail_access.domain.entities import MessagePage, MessageSummary, MessageDetail
from app.shared.infrastructure.database import Database
from app.shared.domain.errors import Unavailable
from app.modules.identity.domain.entities import User


class FakeMailReader:
    calls = 0
    fail = False

    def check(self, mailbox, username, password):
        assert password == 'private-imap-password'
        self.calls += 1
        if self.fail:
            raise Unavailable('El proveedor no está disponible.')

    def search(self, mailbox, username, password, query, unread, limit, offset):
        self.check(mailbox, username, password)
        return MessagePage(91, 1, [MessageSummary(7, 'Meeting', 'sender@example.com', 'Today', 150, False)])

    def read(self, mailbox, username, password, uid, uid_validity):
        self.check(mailbox, username, password)
        return MessageDetail(7, 'Meeting', 'sender@example.com', 'Today', 150, False, 'to@example.com', 'Private message body')


@pytest.fixture
def api_client():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requiere PostgreSQL de prueba; usar scripts/validate_schema.py --backend-python ...')
    settings = Settings(_env_file=None, database_url=url, jwt_secret='test-jwt-secret-' + 'x' * 48,
                        mailbox_encryption_key=base64.urlsafe_b64encode(os.urandom(32)).decode())
    database = Database(settings)
    connection = database.engine.connect()
    transaction = connection.begin()
    application = create_app(settings)

    def sessions():
        with Session(bind=connection, join_transaction_mode='create_savepoint', expire_on_commit=False, autoflush=False) as session:
            yield session

    application.dependency_overrides[get_db_session] = sessions
    try:
        with TestClient(application) as client:
            application.state.test_connection = connection
            application.state.database.session = sessions_context(connection)
            reader = FakeMailReader()
            application.state.mail_reader = reader
            yield client, connection, reader
    finally:
        transaction.rollback()
        connection.close()
        database.dispose()


def sessions_context(connection):
    from contextlib import contextmanager
    @contextmanager
    def session():
        with Session(bind=connection, join_transaction_mode='create_savepoint', expire_on_commit=False, autoflush=False) as session:
            yield session
    return session


def register(client, name='Owner', *, administrator=True):
    # Fixture privada: el registro HTTP publico esta cerrado.
    email = f'{uuid4().hex}@example.com'
    with client.app.state.database.session() as session:
        session.add(User(name=name, email=email, password_hash=client.app.state.passwords.hash('private-user-password'), is_platform_admin=administrator))
        session.commit()
    result = client.post('/auth/login', json={'email': email, 'password': 'private-user-password'})
    assert result.status_code == 200, result.text
    data = result.json()
    assert 'password_hash' not in result.text
    return data['user'], {'Authorization': 'Bearer ' + data['access_token']}


def company(client, headers):
    result = client.post('/tenants', headers=headers, json={'name': 'Test Company'})
    assert result.status_code == 201, result.text
    return result.json()


def mailbox(client, headers, tenant):
    result = client.post(f"/tenants/{tenant['id']}/mailboxes", headers=headers, json={
        'email': 'mail@example.com', 'display_name': 'Sales', 'imap_host': 'imap.example.com',
        'username': 'mail@example.com', 'password': 'private-imap-password',
    })
    assert result.status_code == 201, result.text
    assert 'private-imap-password' not in result.text and 'encrypted_secret' not in result.text
    return result.json()


def test_complete_flow_encrypts_credentials_and_audits_reads(api_client):
    client, connection, reader = api_client
    user, headers = register(client)
    tenant = company(client, headers)
    box = mailbox(client, headers, tenant)
    path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    encrypted = connection.execute(text('SELECT encrypted_secret FROM public.mailbox_credentials WHERE mailbox_id = :id'), {'id': box['id']}).scalar_one()
    assert b'private-imap-password' not in bytes(encrypted)
    assert client.get('/auth/me', headers=headers).json()['id'] == user['id']
    assert client.post(path + '/check', headers=headers).status_code == 200
    renamed = client.patch(path, headers=headers, json={'display_name': 'Renamed', 'imap_host': 'imap.example.com', 'imap_port': 993})
    assert renamed.status_code == 200 and renamed.json()['status'] == 'active'
    assert renamed.json()['updated_at'] != box['updated_at']
    result = client.get(path + '/messages?query=meeting', headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()['uid_validity'] == 91
    result = client.get(path + '/messages/7?uid_validity=91', headers=headers)
    assert result.status_code == 200 and result.json()['body'] == 'Private message body'
    audit = client.get(f"/tenants/{tenant['id']}/audit", headers=headers)
    assert audit.status_code == 200
    assert {'mailbox.create', 'mailbox.check', 'mail.search', 'mail.read'} <= {item['action'] for item in audit.json()}
    assert 'Private message body' not in audit.text and 'private-imap-password' not in audit.text
    assert reader.calls == 3


def test_tenant_isolation_and_no_implicit_owner_mailbox_access(api_client):
    client, _, reader = api_client
    user1, headers1 = register(client)
    user2, headers2 = register(client, administrator=False)
    tenant1, tenant2 = company(client, headers1), company(client, headers1)
    box1, box2 = mailbox(client, headers1, tenant1), mailbox(client, headers1, tenant2)
    path1 = f"/tenants/{tenant1['id']}/mailboxes/{box1['id']}"
    assert client.get(f"/tenants/{tenant2['id']}/mailboxes", headers=headers2).status_code == 403
    assert client.patch(f"/tenants/{tenant1['id']}/mailboxes/{box2['id']}", headers=headers1, json={'display_name': 'Hacked'}).status_code == 404
    assert client.post(path1 + '/grants', headers=headers1, json={'membership_id': tenant2['membership_id']}).status_code == 404
    assert client.delete(path1 + '/grants/' + tenant1['membership_id'], headers=headers1).status_code == 204
    assert client.post(path1 + '/check', headers=headers1).status_code == 403
    assert reader.calls == 0


def test_clients_cannot_administer_and_suspension_is_rechecked(api_client):
    client, _, reader = api_client
    owner, owner_headers = register(client)
    tenant = company(client, owner_headers)
    box = mailbox(client, owner_headers, tenant)
    email = uuid4().hex + '@example.com'
    result = client.post('/admin/clients', headers=owner_headers, json={'tenant_id': tenant['id'], 'name': 'Cliente de prueba', 'email': email, 'password': 'private-user-password'})
    assert result.status_code == 201, result.text
    member = result.json()
    login = client.post('/auth/login', json={'email': email, 'password': 'private-user-password'}).json()
    member_headers = {'Authorization': 'Bearer ' + login['access_token']}
    assert not login['user']['is_platform_admin']
    assert client.post('/tenants', headers=member_headers, json={'name': 'Escalation', 'slug': 'unauthorized'}).status_code == 403
    assert client.get('/admin/clients?tenant_id=' + tenant['id'], headers=member_headers).status_code == 403
    assert client.post('/admin/clients', headers=owner_headers, json={'tenant_id': tenant['id'], 'name': 'Escalation', 'email': uuid4().hex + '@example.com', 'password': 'private-user-password', 'is_platform_admin': True}).status_code == 422
    path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    assert client.post(path + '/check', headers=member_headers).status_code == 403
    assert client.post(path + '/grants', headers=owner_headers, json={'membership_id': member['membership_id']}).status_code == 201
    assert client.post(path + '/check', headers=owner_headers).status_code == 200
    assert client.get(path + '/messages', headers=member_headers).status_code == 200
    assert client.patch('/admin/clients/' + member['id'] + '?tenant_id=' + tenant['id'], headers=owner_headers, json={'status': 'disabled'}).status_code == 204
    assert client.get(path + '/messages', headers=member_headers).status_code == 401
    assert reader.calls == 2


def test_validation_authentication_and_provider_errors_are_safe(api_client):
    client, _, reader = api_client
    assert client.get('/tenants').status_code == 401
    invalid = client.post('/auth/register', json={'name': 'X', 'email': 'x@example.com', 'password': 'secret'})
    assert invalid.status_code == 404 and 'secret' not in invalid.text
    user, headers = register(client)
    bad_login = client.post('/auth/login', json={'email': user['email'], 'password': 'wrong-private-password'})
    assert bad_login.status_code == 401 and 'wrong-private-password' not in bad_login.text
    assert client.get('/tenants', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    tenant = company(client, headers)
    box = mailbox(client, headers, tenant)
    reader.fail = True
    result = client.post(f"/tenants/{tenant['id']}/mailboxes/{box['id']}/check", headers=headers)
    assert result.status_code == 503 and 'private-imap-password' not in result.text
    events = client.get(f"/tenants/{tenant['id']}/audit", headers=headers).json()
    assert any(event['action'] == 'mailbox.check' and event['outcome'] == 'error' for event in events)


def test_mappings_match_the_migrated_schema_without_changes(api_client):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.shared.infrastructure.model_registry import metadata
    _, connection, _ = api_client
    context = MigrationContext.configure(connection, opts={'include_schemas': True})
    differences = compare_metadata(context, metadata)
    assert differences == []


def test_database_allows_only_one_administrator(api_client):
    from sqlalchemy.exc import IntegrityError
    client, _, _ = api_client
    register(client)
    with client.app.state.database.session() as session:
        session.add(User(name='Second admin', email=uuid4().hex + '@example.com', password_hash='not-a-real-hash', is_platform_admin=True))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_administrator_can_login_by_username_without_an_email(api_client):
    client, _, _ = api_client
    with client.app.state.database.session() as session:
        session.add(User(name='Test Administrator', username='test_admin',
                         password_hash=client.app.state.passwords.hash('private-test-password'), is_platform_admin=True))
        session.commit()
    result = client.post('/auth/login', json={'username': ' TEST_ADMIN ', 'password': 'private-test-password'})
    assert result.status_code == 200, result.text
    user = result.json()['user']
    assert user['username'] == 'test_admin' and user['email'] is None and user['is_platform_admin'] is True
    assert 'password_hash' not in result.text
    assert client.get('/auth/me', headers={'Authorization': 'Bearer ' + result.json()['access_token']}).json()['username'] == 'test_admin'
    denied = client.post('/auth/login', json={'username': 'test_admin', 'password': 'wrong-private-password'})
    assert denied.status_code == 401 and 'wrong-private-password' not in denied.text
    assert client.post('/auth/login', json={'password': 'private-test-password'}).status_code == 422
