"""SMTP autenticado con TLS obligatorio, DNS fijado y sin reintentos de DATA."""
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formatdate
import smtplib
import socket
import ssl
from threading import BoundedSemaphore

from app.modules.mail_access.infrastructure.imap_reader import resolve_host
from app.modules.mail_sending.domain.entities import DeliveryFailure
from app.shared.domain.errors import ApplicationError


class PinnedSMTP(smtplib.SMTP):
    def __init__(self, host, port, address, timeout):
        self.validated_address = address
        super().__init__(host, port, timeout=timeout)

    def _get_socket(self, host, port, timeout):
        return socket.create_connection((self.validated_address, port), timeout, self.source_address)


class PinnedSMTPSSL(smtplib.SMTP_SSL):
    def __init__(self, host, port, address, timeout):
        self.validated_address = address
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())

    def _get_socket(self, host, port, timeout):
        sock = socket.create_connection((self.validated_address, port), timeout, self.source_address)
        try:
            return self.context.wrap_socket(sock, server_hostname=host)
        except Exception:
            sock.close()
            raise


class SMTPMailSender:
    def __init__(self, timeout=10, allow_private=False):
        self.timeout, self.allow_private = timeout, allow_private
        self.slots = BoundedSemaphore(2)

    @contextmanager
    def connection(self, mailbox, username, password):
        if not self.slots.acquire(blocking=False):
            raise DeliveryFailure('Hay envios en curso. Intenta mas tarde con una nueva preparacion.')
        client = None
        try:
            address = resolve_host(mailbox.smtp_host, mailbox.smtp_port, self.allow_private)
            if mailbox.smtp_security == 'tls':
                client = PinnedSMTPSSL(mailbox.smtp_host, mailbox.smtp_port, address, self.timeout)
            else:
                client = PinnedSMTP(mailbox.smtp_host, mailbox.smtp_port, address, self.timeout)
                client.ehlo()
                client.starttls(context=ssl.create_default_context())
            client.ehlo()
            client.login(username, password)
            yield client
        except smtplib.SMTPAuthenticationError:
            raise DeliveryFailure('El servidor SMTP rechazo las credenciales del buzon.') from None
        except DeliveryFailure:
            raise
        except (smtplib.SMTPException, OSError, ValueError, UnicodeError, ApplicationError):
            raise DeliveryFailure('No se pudo establecer una conexion SMTP segura. Revisa servidor, puerto y credenciales.') from None
        finally:
            if client:
                # Un fallo de QUIT no cambia un DATA ya aceptado.
                try:
                    client.quit()
                except (smtplib.SMTPException, OSError):
                    try:
                        client.close()
                    except OSError:
                        pass
            self.slots.release()

    def check(self, mailbox, username, password):
        with self.connection(mailbox, username, password):
            pass

    def send(self, mailbox, username, password, payload, message_id):
        message = EmailMessage()
        message['From'] = mailbox.email
        message['To'] = payload['to']
        message['Subject'] = payload['subject']
        message['Date'] = formatdate(usegmt=True)
        message['Message-ID'] = message_id
        if payload.get('in_reply_to'):
            message['In-Reply-To'] = payload['in_reply_to']
        if payload.get('references'):
            message['References'] = payload['references']
        message.set_content(payload['body'])
        with self.connection(mailbox, username, password) as client:
            try:
                refused = client.send_message(message, from_addr=mailbox.email, to_addrs=[payload['to']])
                if refused:
                    raise DeliveryFailure('El servidor SMTP rechazo el destinatario.')
            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError, smtplib.SMTPNotSupportedError):
                raise DeliveryFailure('El servidor SMTP rechazo el envio. Revisa el destinatario y las condiciones del proveedor.') from None
            except DeliveryFailure:
                raise
            except (smtplib.SMTPException, OSError):
                raise DeliveryFailure('El servidor no confirmo el resultado del envio. No lo reintentes automaticamente; comprueba si el destinatario lo recibio.', uncertain=True) from None
