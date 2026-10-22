import base64
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import jwt
import pytest

from app.shared.domain.errors import Unauthorized, Unavailable, InvalidInput
from app.shared.infrastructure.security import AESMailboxCipher, JWTokens, ArgonPasswords
from app.modules.mail_access.infrastructure.imap_reader import resolve_host, TLSMailReader
from app.modules.mailboxes.domain.entities import Mailbox


def test_unknown_password_hash_is_rejected_without_crashing():
    assert ArgonPasswords().verify('test-password', 'unsupported-hash') is False


def test_credentials_are_randomized_and_bound_to_the_mailbox():
    cipher = AESMailboxCipher(base64.urlsafe_b64encode(os.urandom(32)).decode(), 1)
    mailbox = uuid4()
    first = cipher.encrypt('private-mail-password', mailbox)
    second = cipher.encrypt('private-mail-password', mailbox)
    assert first != second
    assert b'private-mail-password' not in first
    assert cipher.decrypt(first, mailbox, 1) == 'private-mail-password'
    with pytest.raises(Unavailable):
        cipher.decrypt(first, uuid4(), 1)
    with pytest.raises(Unavailable):
        cipher.decrypt(first, mailbox, 2)


def test_tokens_reject_expiration_and_tampering():
    secret = 'test-secret-' + 'x' * 40
    tokens = JWTokens(secret, 30)
    user = uuid4()
    assert tokens.subject(tokens.issue(user)) == user
    expired = jwt.encode({'sub': str(user), 'iat': datetime.now(UTC) - timedelta(hours=2),
                          'exp': datetime.now(UTC) - timedelta(hours=1), 'jti': str(uuid4()),
                          'iss': 'corporate-mail-ai', 'aud': 'corporate-mail-api'}, secret, algorithm='HS256')
    with pytest.raises(Unauthorized):
        tokens.subject(expired)
    with pytest.raises(Unauthorized):
        JWTokens('different-secret-' + 'y' * 40, 30).subject(tokens.issue(user))


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'])
def test_imap_blocks_private_and_metadata_addresses(monkeypatch, address):
    monkeypatch.setattr('socket.getaddrinfo', lambda *args, **kwargs: [(None, None, None, None, (address, 993))])
    with pytest.raises(InvalidInput):
        resolve_host('mail.example.com', 993, False)


def test_imap_reads_use_examine_and_peek_without_writing(monkeypatch):
    import app.modules.mail_access.infrastructure.imap_reader as module
    calls = []
    raw = b'From: sender@example.com\r\nTo: reader@example.com\r\nSubject: Safe message\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Hello</p><script>secret_script()</script><img src="http://tracking.example.com">'

    class Connection:
        def __init__(self, *args):
            calls.append(('connect', args))
        def login(self, username, password):
            calls.append(('login',))
        def select(self, folder, readonly):
            calls.append(('select', folder, readonly))
            return 'OK', [b'1']
        def response(self, name):
            return name, [b'19']
        def uid(self, operation, *args):
            calls.append((operation, *args))
            if operation == 'SEARCH':
                return 'OK', [b'7']
            return 'OK', [(b'1 (UID 7 FLAGS () RFC822.SIZE 220', raw), b')']
        def logout(self):
            calls.append(('logout',))

    monkeypatch.setattr(module, 'resolve_host', lambda *args: '93.184.216.34')
    monkeypatch.setattr(module, 'PinnedTLSIMAP', Connection)
    box = Mailbox(tenant_id=uuid4(), email='read@example.com', display_name='Read', imap_host='imap.example.com')
    reader = TLSMailReader()
    page = reader.search(box, 'read@example.com', 'not-logged', 'sales', True, 20, 0)
    message = reader.read(box, 'read@example.com', 'not-logged', 7, page.uid_validity)
    assert 'Hello' in message.body and 'secret_script' not in message.body
    assert 'http://tracking' not in message.body
    assert all(call[2] is True for call in calls if call[0] == 'select')
    assert all('BODY.PEEK[' in call[-1] for call in calls if call[0] == 'FETCH')
    assert not any(call[0] in ('STORE', 'APPEND', 'EXPUNGE', 'COPY', 'MOVE') for call in calls)


def test_imap_rejects_command_injection_in_credentials_before_connecting(monkeypatch):
    import app.modules.mail_access.infrastructure.imap_reader as module
    monkeypatch.setattr(module, 'resolve_host', lambda *args: pytest.fail('No debe abrir una conexion'))
    box = Mailbox(tenant_id=uuid4(), email='read@example.com', display_name='Read', imap_host='imap.example.com')
    with pytest.raises(InvalidInput):
        TLSMailReader().check(box, 'user\r\nA1 STORE 1 +FLAGS \\Deleted', 'password')
