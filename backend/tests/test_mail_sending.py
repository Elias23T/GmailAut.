from datetime import timedelta
import json
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from test_api import api_client, register, company, mailbox
from test_oauth_mcp import setup_client, authorize, exchange, call, rpc
from app.modules.mail_sending.domain.entities import DeliveryFailure, OutgoingMessage
from app.modules.mail_sending.infrastructure.repository import SQLOutgoingRepository
from app.shared.domain.entities import utcnow


class FakeSender:
    def __init__(self):
        self.calls = []
        self.checks = 0
        self.failure = None

    def check(self, mailbox, username, password):
        assert password == 'private-imap-password'
        self.checks += 1

    def send(self, mailbox, username, password, payload, message_id):
        assert password == 'private-imap-password'
        self.calls.append({'from': mailbox.email, **payload, 'message_id': message_id})
        if self.failure:
            raise self.failure


def enabled(client):
    headers, tenant, box, customer, customer_headers, client_id = setup_client(client)
    client.app.state.mail_sender = sender = FakeSender()
    path = f"/tenants/{tenant['id']}/mailboxes/{box['id']}"
    assert client.patch(path, headers=headers, json={'smtp_enabled': True, 'smtp_host': 'smtp.example.com'}).status_code == 200
    assert client.patch(path + '/grants/' + customer['membership_id'], headers=headers, json={'can_send': True}).status_code == 200
    return headers, tenant, box, customer, customer_headers, client_id, sender


def content():
    return {'to': 'contacto@example.com', 'subject': 'Consulta de prueba', 'body': 'Contenido privado de la respuesta.'}


def rest_prepare(client, tenant, box, headers, **changes):
    return client.post(f"/tenants/{tenant['id']}/mailboxes/{box['id']}/outgoing/prepare", headers=headers, json={**content(), **changes})


def rest_send(client, tenant, draft, headers, **changes):
    return client.post(f"/tenants/{tenant['id']}/outgoing/{draft['preparation_id']}/send", headers=headers,
                       json={**content(), 'confirmed': True, **changes})


def test_preparation_is_encrypted_requires_confirmation_and_replay_does_not_send_twice(api_client):
    client, connection, _ = api_client
    headers, tenant, box, _, customer_headers, _, sender = enabled(client)
    check = client.post(f"/tenants/{tenant['id']}/mailboxes/{box['id']}/smtp-check", headers=headers)
    assert check.status_code == 200 and sender.checks == 1 and not sender.calls
    prepared = rest_prepare(client, tenant, box, customer_headers)
    assert prepared.status_code == 201, prepared.text
    preview = prepared.json()
    assert preview['from'] == box['email'] and preview['requires_confirmation'] is True
    assert not sender.calls
    encrypted = connection.execute(text('SELECT encrypted_payload FROM outgoing_messages')).scalar_one()
    assert content()['body'].encode() not in encrypted
    assert rest_send(client, tenant, preview, customer_headers, confirmed=False).status_code == 422
    assert rest_send(client, tenant, preview, customer_headers, to='otra@example.com').status_code == 409
    assert rest_send(client, tenant, preview, customer_headers, body='Texto cambiado').status_code == 409
    sent = rest_send(client, tenant, preview, customer_headers)
    assert sent.status_code == 200, sent.text
    assert sent.json()['status'] == 'sent' and len(sender.calls) == 1
    assert sender.calls[0]['from'] == box['email']
    replay = rest_send(client, tenant, preview, customer_headers)
    assert replay.status_code == 200 and replay.json()['already_sent'] is True and len(sender.calls) == 1
    assert connection.execute(text('SELECT encrypted_payload FROM outgoing_messages')).scalar_one() is None
    events = client.get(f"/tenants/{tenant['id']}/audit", headers=headers)
    assert content()['body'] not in events.text and 'private-imap-password' not in events.text
    assert connection.execute(text("SELECT count(*) FROM audit_events WHERE action='mail.send' AND outcome='success'")).scalar_one() == 1


def test_send_permission_is_separate_and_checked_again_after_preparation(api_client):
    client, _, _ = api_client
    headers, tenant, box, customer, customer_headers, _, sender = enabled(client)
    grant = f"/tenants/{tenant['id']}/mailboxes/{box['id']}/grants/{customer['membership_id']}"
    assert client.patch(grant, headers=headers, json={'can_send': False}).status_code == 200
    assert rest_prepare(client, tenant, box, customer_headers).status_code == 403
    assert client.patch(grant, headers=headers, json={'can_send': True}).status_code == 200
    draft = rest_prepare(client, tenant, box, customer_headers).json()
    assert client.patch(grant, headers=headers, json={'can_send': False}).status_code == 200
    assert rest_send(client, tenant, draft, customer_headers).status_code == 403
    assert not sender.calls


def test_other_user_and_other_tenant_cannot_use_a_preparation(api_client):
    client, _, _ = api_client
    headers, tenant, box, _, customer_headers, _, sender = enabled(client)
    draft = rest_prepare(client, tenant, box, customer_headers).json()
    assert rest_send(client, tenant, draft, headers).status_code == 404
    other_tenant = company(client, headers)
    assert rest_send(client, other_tenant, draft, headers).status_code == 404
    assert rest_send(client, tenant, {'preparation_id': str(uuid4())}, customer_headers).status_code == 404
    assert not sender.calls


@pytest.mark.parametrize('uncertain', [False, True])
def test_failed_or_uncertain_delivery_is_not_automatically_retried(api_client, uncertain):
    client, connection, _ = api_client
    _, tenant, box, _, customer_headers, _, sender = enabled(client)
    sender.failure = DeliveryFailure('Fallo SMTP simulado sin secretos.', uncertain=uncertain)
    draft = rest_prepare(client, tenant, box, customer_headers).json()
    response = rest_send(client, tenant, draft, customer_headers)
    assert response.status_code == 503
    assert connection.execute(text('SELECT status FROM outgoing_messages')).scalar_one() == ('unknown' if uncertain else 'failed')
    assert connection.execute(text('SELECT encrypted_payload FROM outgoing_messages')).scalar_one() is None
    assert rest_send(client, tenant, draft, customer_headers).status_code == 409
    assert len(sender.calls) == 1


def test_expired_preparation_and_atomic_reservation_block_sending(api_client):
    client, connection, _ = api_client
    _, tenant, box, _, customer_headers, _, sender = enabled(client)
    draft = rest_prepare(client, tenant, box, customer_headers).json()
    connection.execute(text('UPDATE outgoing_messages SET created_at=:created,expires_at=:expired'),
                       {'created': utcnow() - timedelta(hours=1), 'expired': utcnow() - timedelta(minutes=1)})
    assert rest_send(client, tenant, draft, customer_headers).status_code == 409
    assert connection.execute(text('SELECT encrypted_payload FROM outgoing_messages')).scalar_one() is None
    next_draft = rest_prepare(client, tenant, box, customer_headers).json()
    with client.app.state.database.session() as session:
        row = session.get(OutgoingMessage, next_draft['preparation_id'])
        repository = SQLOutgoingRepository(session)
        assert repository.claim(row) is True
        assert repository.claim(row) is False
        session.commit()
    assert rest_send(client, tenant, next_draft, customer_headers).status_code == 409
    assert not sender.calls


def test_expiry_cleanup_removes_abandoned_content_without_reopening_an_uncertain_send(api_client):
    client, connection, _ = api_client
    _, tenant, box, _, customer_headers, _, sender = enabled(client)
    old = rest_prepare(client, tenant, box, customer_headers).json()
    connection.execute(text("UPDATE outgoing_messages SET status='sending',created_at=:created,expires_at=:expired"),
                       {'created': utcnow() - timedelta(hours=1), 'expired': utcnow() - timedelta(minutes=1)})
    assert rest_prepare(client, tenant, box, customer_headers).status_code == 201
    row = connection.execute(text('SELECT status,encrypted_payload FROM outgoing_messages WHERE id=:id'),
                             {'id': old['preparation_id']}).one()
    assert row.status == 'unknown' and row.encrypted_payload is None
    assert rest_send(client, tenant, old, customer_headers).status_code == 409
    assert not sender.calls


def test_reply_uses_reply_to_and_keeps_thread_headers(api_client):
    client, _, reader = api_client
    _, tenant, box, _, customer_headers, _, sender = enabled(client)
    original_read = reader.read
    def read(*args):
        message = original_read(*args)
        message.reply_to = 'soporte@example.com'
        message.message_id = '<original@example.com>'
        message.references = '<anterior@example.com>'
        return message
    reader.read = read
    response = client.post(f"/tenants/{tenant['id']}/mailboxes/{box['id']}/outgoing/prepare", headers=customer_headers,
                           json={'body': content()['body'], 'reply_uid': 7, 'uid_validity': 91})
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft['to'] == 'soporte@example.com' and draft['subject'] == 'Re: Meeting' and draft['is_reply'] is True
    assert rest_send(client, tenant, draft, customer_headers, to=draft['to'], subject=draft['subject']).status_code == 200
    assert sender.calls[0]['in_reply_to'] == '<original@example.com>'
    assert sender.calls[0]['references'] == '<anterior@example.com> <original@example.com>'


def unpack(response):
    result = response.json()['result']
    return result.get('structuredContent') or json.loads(result['content'][0]['text'])


def test_mcp_sending_requires_new_oauth_scope_and_exposes_reviewable_content(api_client):
    client, _, _ = api_client
    _, tenant, box, _, customer_headers, client_id, sender = enabled(client)
    read_access = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()['access_token']
    args = {'mailbox_id': box['id'], **content()}
    denied = call(client, read_access, 'prepare_email', args).json()['result']
    assert denied['isError'] is True and 'mail:send' in str(denied['_meta'])
    access = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant, scope='mail:read mail:send')).json()['access_token']
    assert rpc(client, access, 'tools/list').status_code == 200
    preview = unpack(call(client, access, 'prepare_email', args))
    confirm_args = {'preparation_id': preview['preparation_id'], **content(), 'confirmed': True}
    sent = unpack(call(client, access, 'send_email', confirm_args))
    assert sent['status'] == 'sent' and len(sender.calls) == 1
    assert unpack(call(client, access, 'send_email', confirm_args))['already_sent'] is True


def test_read_refresh_cannot_gain_sending_scope(api_client):
    client, _, _ = api_client
    _, tenant, _, _, customer_headers, client_id, _ = enabled(client)
    token = exchange(client, client_id, authorize(client, client_id, customer_headers, tenant)).json()
    upgraded = client.post('/oauth/token', data={'grant_type': 'refresh_token', 'client_id': client_id,
        'resource': 'http://127.0.0.1:8000/mcp', 'refresh_token': token['refresh_token'], 'scope': 'mail:read mail:send'})
    assert upgraded.status_code == 400


@pytest.mark.parametrize('changes', [{'subject': 'Asunto\r\nBcc: intruso@example.com'}, {'to': 'a@example.com,b@example.com'},
                                     {'body': 'hola\x00mundo'}, {'body': 'x' * 16001}, {'from': 'falso@example.com'}])
def test_invalid_or_injected_email_is_never_sent(api_client, changes):
    client, _, _ = api_client
    _, tenant, box, _, customer_headers, _, sender = enabled(client)
    assert rest_prepare(client, tenant, box, customer_headers, **changes).status_code == 422
    assert not sender.calls
