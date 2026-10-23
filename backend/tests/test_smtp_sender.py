from types import SimpleNamespace
import smtplib

import pytest

from app.modules.mail_sending.domain.entities import DeliveryFailure
from app.modules.mail_sending.infrastructure import smtp_sender as module


class SMTPProbe:
    def __init__(self):
        self.events = []
        self.failure = None
        self.quit_failure = False

    def ehlo(self):
        self.events.append('ehlo')

    def starttls(self, context):
        assert context.check_hostname and context.verify_mode
        self.events.append('tls')

    def login(self, username, password):
        assert username == 'mail@example.com' and password == 'fake-password'
        self.events.append('login')

    def send_message(self, message, from_addr, to_addrs):
        self.events.append('data')
        self.message, self.from_addr, self.to_addrs = message, from_addr, to_addrs
        if self.failure:
            raise self.failure
        return {}

    def quit(self):
        self.events.append('quit')
        if self.quit_failure:
            raise smtplib.SMTPServerDisconnected('quit')

    def close(self):
        self.events.append('close')


def configured(monkeypatch, security='tls'):
    probe = SMTPProbe()
    monkeypatch.setattr(module, 'resolve_host', lambda *args: '203.0.113.1')
    def create(host, port, address, timeout):
        assert address == '203.0.113.1' and host == 'smtp.example.com'
        return probe
    monkeypatch.setattr(module, 'PinnedSMTPSSL', create)
    monkeypatch.setattr(module, 'PinnedSMTP', create)
    mailbox = SimpleNamespace(smtp_host='smtp.example.com', smtp_port=465 if security == 'tls' else 587,
                              smtp_security=security, email='mail@example.com')
    return probe, mailbox, module.SMTPMailSender()


def deliver(sender, mailbox):
    sender.send(mailbox, 'mail@example.com', 'fake-password', {'to':'recipient@example.com', 'subject':'Prueba',
                'body':'Texto de prueba', 'in_reply_to':'<original@example.com>', 'references':'<original@example.com>'}, '<prepared@example.com>')


@pytest.mark.parametrize('security', ['tls', 'starttls'])
def test_smtp_uses_tls_authentication_fixed_sender_and_reply_headers(monkeypatch, security):
    probe, mailbox, sender = configured(monkeypatch, security)
    deliver(sender, mailbox)
    assert probe.events.index('login') < probe.events.index('data')
    if security == 'starttls':
        assert probe.events.index('tls') < probe.events.index('login')
    assert probe.from_addr == mailbox.email and probe.to_addrs == ['recipient@example.com']
    assert probe.message['From'] == mailbox.email
    assert probe.message['In-Reply-To'] == '<original@example.com>'
    assert probe.message['Message-ID'] == '<prepared@example.com>'


def test_smtp_check_does_not_issue_data_and_quit_failure_does_not_undo_acceptance(monkeypatch):
    probe, mailbox, sender = configured(monkeypatch)
    sender.check(mailbox, 'mail@example.com', 'fake-password')
    assert 'data' not in probe.events
    probe.quit_failure = True
    deliver(sender, mailbox)
    assert probe.events.count('data') == 1 and 'close' in probe.events


@pytest.mark.parametrize('failure,uncertain', [(TimeoutError(), True),
    (smtplib.SMTPServerDisconnected('disconnect'), True),
    (smtplib.SMTPRecipientsRefused({'recipient@example.com':(550,b'refused')}), False),
    (smtplib.SMTPDataError(550,b'rejected'), False)])
def test_smtp_distinguishes_rejection_from_uncertain_delivery(monkeypatch, failure, uncertain):
    probe, mailbox, sender = configured(monkeypatch)
    probe.failure = failure
    with pytest.raises(DeliveryFailure) as result:
        deliver(sender, mailbox)
    assert result.value.uncertain is uncertain
    assert probe.events.count('data') == 1


def test_starttls_failure_never_authenticates_or_sends(monkeypatch):
    probe, mailbox, sender = configured(monkeypatch, 'starttls')
    def fail(context):
        raise smtplib.SMTPNotSupportedError('STARTTLS missing')
    probe.starttls = fail
    with pytest.raises(DeliveryFailure):
        deliver(sender, mailbox)
    assert 'login' not in probe.events and 'data' not in probe.events
