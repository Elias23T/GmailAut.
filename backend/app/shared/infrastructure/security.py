import base64
from datetime import UTC, datetime, timedelta
import os
from uuid import UUID, uuid4

import jwt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.shared.domain.errors import Unauthorized, Unavailable


class ArgonPasswords:
    def __init__(self):
        self.hasher = PasswordHash.recommended()
        self.dummy_hash = self.hasher.hash(os.urandom(24).hex())

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, password: str, encoded: str) -> bool:
        try:
            return self.hasher.verify(password, encoded)
        except (ValueError, TypeError, UnknownHashError):
            return False


class JWTokens:
    def __init__(self, secret: str | None, minutes: int):
        self.secret = secret
        self.minutes = minutes

    def _key(self) -> str:
        if not self.secret or len(self.secret) < 32 or self.secret.startswith('CHANGE_ME'):
            raise Unavailable('Falta configurar JWT_SECRET con al menos 32 caracteres.')
        return self.secret

    def issue(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        return jwt.encode({
            'sub': str(user_id), 'iat': now, 'exp': now + timedelta(minutes=self.minutes),
            'jti': str(uuid4()), 'iss': 'corporate-mail-ai', 'aud': 'corporate-mail-api',
        }, self._key(), algorithm='HS256')

    def subject(self, token: str) -> UUID:
        try:
            payload = jwt.decode(token, self._key(), algorithms=['HS256'], issuer='corporate-mail-ai',
                                 audience='corporate-mail-api', options={'require': ['sub', 'exp', 'iat', 'jti', 'iss', 'aud']})
            return UUID(payload['sub'])
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            raise Unauthorized('La sesión no es válida o expiró. Inicia sesión nuevamente.') from None


class AESMailboxCipher:
    def __init__(self, encoded_key: str | None, version: int):
        self.encoded_key = encoded_key
        self.version = version

    def _cipher(self) -> AESGCM:
        try:
            key = base64.b64decode(self.encoded_key or '', altchars=b'-_', validate=True)
            if len(key) != 32:
                raise ValueError()
            return AESGCM(key)
        except (ValueError, TypeError):
            raise Unavailable('Falta configurar una clave válida de cifrado de buzones.') from None

    def encrypt(self, value: str, mailbox_id: UUID) -> bytes:
        nonce = os.urandom(12)
        return b'CM1' + nonce + self._cipher().encrypt(nonce, value.encode('utf-8'), mailbox_id.bytes)

    def decrypt(self, value: bytes, mailbox_id: UUID, version: int) -> str:
        if version != self.version or not value.startswith(b'CM1') or len(value) < 32:
            raise Unavailable('La credencial no se puede descifrar con la clave configurada.')
        try:
            return self._cipher().decrypt(value[3:15], value[15:], mailbox_id.bytes).decode('utf-8')
        except (InvalidTag, UnicodeDecodeError):
            raise Unavailable('La credencial cifrada no es válida para este buzón.') from None
