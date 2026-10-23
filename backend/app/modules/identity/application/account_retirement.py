"""Retirada de una cuenta sin romper referencias de auditoria o permisos."""
import secrets
from app.shared.domain.entities import utcnow


def retire_account(uow, passwords, oauth, user):
    user.deleted_at = utcnow()
    user.auth_version += 1
    user.email = None
    user.username = 'removed_' + user.id.hex[:24]
    user.password_hash = passwords.hash(secrets.token_urlsafe(48))
    for member in sorted(uow.memberships.all_for_user(user.id), key=lambda item: str(item.id)):
        oauth.revoke_member(member.id, utcnow())
