from datetime import timedelta
from email.utils import getaddresses
import hashlib
import hmac
import json
import re
from uuid import UUID

from pydantic import ValidationError
from app.modules.audit.application.service import record
from app.modules.authorization.application.service import AuthorizationService
from app.modules.mail_access.application.service import MailAccessService
from app.modules.mail_sending.application.schemas import EmailContent, PrepareEmail
from app.modules.mail_sending.domain.entities import DeliveryFailure, OutgoingMessage
from app.shared.domain.entities import utcnow
from app.shared.domain.errors import Conflict, InvalidInput, NotFound, Unavailable


def content_digest(content):
    raw = json.dumps({key: content[key] for key in ('to', 'subject', 'body')}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class MailSendingService:
    def __init__(self, uow, cipher, reader, sender):
        self.uow, self.cipher, self.reader, self.sender = uow, cipher, reader, sender
        self.authorization = AuthorizationService(uow)

    def _credentials(self, mailbox):
        credential = self.uow.mailboxes.credential(mailbox.id)
        if not credential:
            raise Unavailable('El buzon no tiene credenciales configuradas.')
        return credential.username, self.cipher.decrypt(credential.encrypted_secret, mailbox.id, credential.key_version)

    def check(self, actor, tenant_id, mailbox_id):
        self.authorization.member(actor, tenant_id, admin=True)
        mailbox = self.authorization.mailbox(actor, tenant_id, mailbox_id, require_active=False)
        if not mailbox.smtp_enabled or not mailbox.smtp_host:
            raise InvalidInput('Primero habilita y configura SMTP en el buzon.')
        username, password = self._credentials(mailbox)
        self.uow.commit()
        try:
            self.sender.check(mailbox, username, password)
        except DeliveryFailure as error:
            record(self.uow, actor, 'smtp.check', tenant_id=tenant_id, mailbox_id=mailbox_id, outcome='error')
            self.uow.commit()
            raise Unavailable(str(error)) from None
        record(self.uow, actor, 'smtp.check', tenant_id=tenant_id, mailbox_id=mailbox_id)
        self.uow.commit()
        return {'status': 'ok', 'message': 'Conexion SMTP verificada; no se envio ningun correo.'}

    def prepare(self, actor, tenant_id, mailbox_id, request: PrepareEmail):
        mailbox = self.authorization.sending_mailbox(actor, tenant_id, mailbox_id)
        in_reply_to, references = '', ''
        recipient, subject = request.to, request.subject
        if request.reply_uid is not None:
            original = MailAccessService(self.uow, self.cipher, self.reader).read(
                actor, tenant_id, mailbox_id, request.reply_uid, request.uid_validity)
            mailbox = self.authorization.sending_mailbox(actor, tenant_id, mailbox_id)
            if recipient is None:
                addresses = getaddresses([original.reply_to or original.sender])
                if len(addresses) != 1 or not addresses[0][1]:
                    raise InvalidInput('El correo original no tiene un unico remitente valido. Indica el destinatario.')
                recipient = addresses[0][1]
            subject = subject or (original.subject if original.subject.lower().startswith('re:') else 'Re: ' + original.subject)[:200]
            if re.fullmatch(r'<[^<>\s]{1,250}>', original.message_id):
                in_reply_to = original.message_id
                history = re.findall(r'<[^<>\s]{1,250}>', original.references)[-19:]
                references = ' '.join([*history, in_reply_to])
        try:
            content = EmailContent(to=recipient, subject=subject, body=request.body).model_dump(mode='json')
        except ValidationError:
            raise InvalidInput('Revisa el destinatario, asunto (hasta 200 caracteres) y mensaje (hasta 16000 caracteres). No se admiten saltos de linea en el asunto.') from None
        if not mailbox.email.isascii():
            raise InvalidInput('El envio requiere una direccion de remitente sin caracteres internacionales.')
        member = self.uow.memberships.for_user(tenant_id, actor.user_id)
        self.uow.outgoing.expire(tenant_id)
        if self.uow.outgoing.pending(tenant_id, member.id) >= 20:
            raise Conflict('Ya tienes veinte mensajes preparados. Envia los pendientes o espera a que expiren en diez minutos.')
        payload = {**content, 'in_reply_to': in_reply_to, 'references': references}
        draft = OutgoingMessage(tenant_id=tenant_id, mailbox_id=mailbox_id, membership_id=member.id,
            encrypted_payload=None, key_version=self.cipher.version, payload_hash=content_digest(content),
            message_id='', expires_at=utcnow() + timedelta(minutes=10))
        draft.message_id = f'<{draft.id.hex}@{mailbox.email.split("@", 1)[1]}>'
        draft.encrypted_payload = self.cipher.encrypt(json.dumps(payload, ensure_ascii=False), draft.id)
        self.uow.outgoing.add(draft)
        record(self.uow, actor, 'mail.prepare_reply' if request.reply_uid is not None else 'mail.prepare', tenant_id=tenant_id, mailbox_id=mailbox_id)
        self.uow.commit()
        return {'preparation_id': str(draft.id), 'mailbox_id': str(mailbox_id), 'from': mailbox.email,
                **content, 'expires_at': draft.expires_at.isoformat(), 'is_reply': request.reply_uid is not None,
                'requires_confirmation': True, 'message': 'Mensaje preparado, todavia no enviado. Muestra remitente, destinatario, asunto y texto completos; solicita confirmacion antes de usar send_email.'}

    def send(self, actor, tenant_id, preparation_id: UUID, content: EmailContent):
        member = self.authorization.member(actor, tenant_id)
        draft = self.uow.outgoing.get(tenant_id, member.id, preparation_id)
        if not draft:
            raise NotFound('Preparacion no disponible para esta cuenta y empresa.')
        mailbox = self.authorization.sending_mailbox(actor, tenant_id, draft.mailbox_id)
        if not hmac.compare_digest(draft.payload_hash, content_digest(content.model_dump(mode='json'))):
            raise Conflict('El destinatario, asunto o mensaje cambio. Prepara y confirma nuevamente el correo.')
        if draft.status == 'sent':
            return {'status': 'sent', 'preparation_id': str(draft.id), 'message_id': draft.message_id,
                    'already_sent': True, 'message': 'El servidor SMTP ya acepto este correo; no se volvio a enviar.'}
        if draft.status != 'prepared':
            raise Conflict('Esta preparacion ya se proceso o su resultado esta pendiente. No se repetira el envio automaticamente.')
        if draft.expires_at <= utcnow():
            draft.status, draft.encrypted_payload = 'expired', None
            self.uow.commit()
            raise Conflict('La preparacion expiro. Prepara y confirma un nuevo correo.')
        payload = json.loads(self.cipher.decrypt(draft.encrypted_payload, draft.id, draft.key_version))
        username, password = self._credentials(mailbox)
        if not self.uow.outgoing.claim(draft):
            self.uow.rollback()
            raise Conflict('Otro proceso ya esta enviando este correo. No se repetira el envio.')
        # La reserva se confirma antes de SMTP: una caida no permite duplicar DATA.
        self.uow.commit()
        try:
            self.sender.send(mailbox, username, password, payload, draft.message_id)
        except DeliveryFailure as error:
            draft.status = 'unknown' if error.uncertain else 'failed'
            draft.encrypted_payload = None
            record(self.uow, actor, 'mail.send', tenant_id=tenant_id, mailbox_id=mailbox.id, outcome='error')
            self.uow.commit()
            raise Unavailable(str(error)) from None
        draft.status, draft.sent_at, draft.encrypted_payload = 'sent', utcnow(), None
        record(self.uow, actor, 'mail.send', tenant_id=tenant_id, mailbox_id=mailbox.id)
        self.uow.commit()
        return {'status': 'sent', 'preparation_id': str(draft.id), 'message_id': draft.message_id,
                'already_sent': False, 'message': 'Correo aceptado por el servidor SMTP para su entrega.'}
