"""Adaptador IMAP TLS: EXAMINE y BODY.PEEK, sin operaciones de escritura."""

from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import imaplib
import ipaddress
import re
import socket
import ssl
from threading import BoundedSemaphore

from app.modules.mail_access.domain.entities import MessageDetail, MessagePage, MessageSummary
from app.modules.mailboxes.domain.entities import Mailbox
from app.shared.domain.errors import Conflict, InvalidInput, NotFound, TooLarge, Unavailable


def resolve_host(host: str, port: int, allow_private: bool) -> str:
    try:
        addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    except OSError:
        raise Unavailable('No se pudo resolver el servidor IMAP.') from None
    if not addresses or (not allow_private and any(not ipaddress.ip_address(addr).is_global for addr in addresses)):
        raise InvalidInput('El servidor IMAP debe resolver a una dirección pública permitida.')
    return addresses[0]


class PinnedTLSIMAP(imaplib.IMAP4_SSL):
    def __init__(self, host: str, port: int, address: str, timeout: int):
        self.validated_address = address
        super().__init__(host=host, port=port, ssl_context=ssl.create_default_context(), timeout=timeout)

    def _create_socket(self, timeout):
        sock = socket.create_connection((self.validated_address, self.port), timeout)
        try:
            return self.ssl_context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head'):
            self.hidden += 1
        elif tag in ('br', 'p', 'div', 'li') and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class TLSMailReader:
    def __init__(self, timeout: int = 10, max_bytes: int = 1048576, allow_private: bool = False):
        self.timeout, self.max_bytes, self.allow_private = timeout, max_bytes, allow_private
        self._slots = BoundedSemaphore(4)

    @contextmanager
    def _connection(self, mailbox: Mailbox, username: str, password: str):
        if any(ord(char) < 32 or ord(char) == 127 for char in username + password):
            raise InvalidInput('Las credenciales contienen caracteres no permitidos.')
        if not self._slots.acquire(blocking=False):
            raise Unavailable('Hay varias consultas de correo en curso. Intenta nuevamente en un momento.')
        connection = None
        try:
            address = resolve_host(mailbox.imap_host, mailbox.imap_port, self.allow_private)
            connection = PinnedTLSIMAP(mailbox.imap_host, mailbox.imap_port, address, self.timeout)
            # Python 3.12/3.13 no citan el usuario de LOGIN; 3.14+ usa _astring.
            login_user = username if hasattr(imaplib.IMAP4, '_astring') else '"' + username.replace('\\', '\\\\').replace('"', '\\"') + '"'
            connection.login(login_user, password)
            status, _ = connection.select('INBOX', readonly=True)
            if status != 'OK':
                raise Unavailable('El proveedor no permitió abrir INBOX en modo de lectura.')
            yield connection
        except (imaplib.IMAP4.error, OSError, ValueError, UnicodeError, LookupError):
            raise Unavailable('No se pudo acceder al buzón. Revisa el servidor y sus credenciales.') from None
        finally:
            if connection:
                try:
                    connection.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass
            self._slots.release()

    @staticmethod
    def _validity(connection) -> int:
        _, values = connection.response('UIDVALIDITY')
        if not values or not values[0] or not values[0].isdigit():
            raise Unavailable('El servidor no proporcionó UIDVALIDITY para identificar los mensajes.')
        return int(values[0])

    @staticmethod
    def _fetch(connection, uid: int, fields: str) -> tuple[bytes, bytes]:
        status, data = connection.uid('FETCH', str(uid), fields)
        if status != 'OK':
            raise NotFound('Mensaje no disponible.')
        for item in data or []:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bytes):
                return item[0], item[1]
        raise NotFound('El proveedor no devolvió el mensaje solicitado.')

    @staticmethod
    def _summary(uid: int, metadata: bytes, payload: bytes) -> MessageSummary:
        message = BytesParser(policy=policy.default).parsebytes(payload, headersonly=True)
        size = re.search(rb'RFC822.SIZE\s+(\d+)', metadata)
        return MessageSummary(uid=uid, subject=str(message.get('subject', '(Sin asunto)'))[:1000],
                              sender=str(message.get('from', ''))[:1000], date=str(message.get('date', ''))[:200],
                              size=int(size.group(1)) if size else 0, seen=b'\\Seen' in metadata)

    def check(self, mailbox: Mailbox, username: str, password: str) -> None:
        with self._connection(mailbox, username, password):
            pass

    def search(self, mailbox: Mailbox, username: str, password: str, query: str, unread: bool, limit: int, offset: int) -> MessagePage:
        if any(char in query for char in ('\r', '\n', '\x00')):
            raise InvalidInput('La búsqueda contiene caracteres no permitidos.')
        with self._connection(mailbox, username, password) as connection:
            validity = self._validity(connection)
            criteria = 'UNSEEN' if unread else 'ALL'
            if query:
                term = '"' + query.replace('\\', '\\\\').replace('"', '\\"') + '"'
                criteria += ' OR SUBJECT ' + term + ' FROM ' + term
                status, data = connection.uid('SEARCH', 'CHARSET', 'UTF-8', criteria.encode('utf-8'))
            else:
                status, data = connection.uid('SEARCH', None, criteria)
            if status != 'OK':
                raise Unavailable('El proveedor no pudo ejecutar la búsqueda.')
            raw_uids = data[0] if data and isinstance(data[0], bytes) else b''
            uids = [int(item) for item in raw_uids.split() if item.isdigit()]
            selected = list(reversed(uids))[offset:offset + limit]
            items = []
            for uid in selected:
                try:
                    metadata, headers = self._fetch(connection, uid, '(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)]<0.16384>)')
                    items.append(self._summary(uid, metadata, headers))
                except NotFound:
                    continue
            return MessagePage(uid_validity=validity, total=len(uids), items=items)

    def read(self, mailbox: Mailbox, username: str, password: str, uid: int, uid_validity: int) -> MessageDetail:
        with self._connection(mailbox, username, password) as connection:
            if self._validity(connection) != uid_validity:
                raise Conflict('El buzón cambió. Actualiza la lista antes de abrir el mensaje.')
            metadata, raw = self._fetch(connection, uid, f'(UID FLAGS RFC822.SIZE BODY.PEEK[]<0.{self.max_bytes}>)')
            summary = self._summary(uid, metadata, raw)
            if summary.size > self.max_bytes or len(raw) >= self.max_bytes:
                raise TooLarge('El mensaje supera el tamaño máximo de lectura configurado.')
            message = BytesParser(policy=policy.default).parsebytes(raw)
            part = message.get_body(preferencelist=('plain', 'html'))
            content = part.get_content() if part else ''
            if not isinstance(content, str):
                content = ''
            if part and part.get_content_type() == 'text/html':
                parser = PlainHTML()
                parser.feed(content)
                content = ''.join(parser.parts)
            attachments = [str(part.get_filename())[:200] for part in message.walk() if part.get_filename()][:100]
            return MessageDetail(**vars(summary), recipients=str(message.get('to', ''))[:2000], body=content[:200000],
                attachments=attachments, truncated=len(content) > 200000,
                message_id=str(message.get('message-id', ''))[:1000],
                reply_to=str(message.get('reply-to', ''))[:1000], references=str(message.get('references', ''))[:4000])
