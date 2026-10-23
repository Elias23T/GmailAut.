"""Inicializacion local: python -m app.cli create-admin --username admin"""
import argparse
from getpass import getpass
import re
from pydantic import TypeAdapter, EmailStr
from app.core.config import Settings
from app.modules.identity.domain.entities import User
from app.modules.identity.application.administrator_access import attach_administrator
from app.shared.domain.entities import utcnow
from app.shared.infrastructure.database import Database
from app.shared.infrastructure.unit_of_work import SQLUnitOfWork
from app.shared.infrastructure.security import ArgonPasswords


def create_admin(session, email, name, password, username=None):
    if len(password) < 6:
        raise ValueError('La contraseña debe tener al menos 6 caracteres.')
    if bool(email) == bool(username):
        raise ValueError('Indica exactamente uno: correo o nombre de usuario.')
    if email:
        email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
    if username:
        username = username.strip().lower()
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{2,31}', username):
            raise ValueError('El usuario debe tener entre 3 y 32 caracteres y comenzar con una letra.')
    uow = SQLUnitOfWork(session)
    uow.users.lock_administration()
    identifier = email or username
    user = uow.users.by_login(identifier)
    if user:
        raise ValueError('Esa cuenta ya existe. Usa promote-admin para promoverla sin cambiar su contraseña.')
    user = User(
        name=name,
        email=email,
        username=username,
        password_hash=ArgonPasswords().hash(password),
        is_platform_admin=True,
    )
    uow.users.add(user)
    uow.flush()
    attach_tenants(session, uow, user)
    uow.commit()


def attach_tenants(session, uow, user):
    attach_administrator(uow, user)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create-admin', 'promote-admin'])
    identifier_group = parser.add_mutually_exclusive_group(required=True)
    identifier_group.add_argument('--email')
    identifier_group.add_argument('--username')
    parser.add_argument('--name', default='Administrador')
    args = parser.parse_args()
    database = Database(Settings())
    try:
        with database.session() as session:
            if args.command == 'create-admin':
                password = getpass('Contraseña del administrador (mínimo 6 caracteres): ')
                if password != getpass('Repetir contraseña: '):
                    parser.error('Las contraseñas no coinciden.')
                create_admin(session, args.email, args.name, password, args.username)
            else:
                uow = SQLUnitOfWork(session)
                uow.users.lock_administration()
                user = uow.users.by_login(args.email or args.username)
                if not user or user.status != 'active':
                    parser.error('No existe una cuenta activa con ese correo o usuario.')
                user.is_platform_admin = True
                user.auth_version += 1
                for member in uow.memberships.all_for_user(user.id):
                    uow.oauth.revoke_member(member.id, utcnow())
                attach_tenants(session, uow, user)
                uow.commit()
        print('Administrador configurado. Inicia sesión desde la interfaz.')
    except ValueError as error:
        parser.error(str(error))
    finally:
        database.dispose()


if __name__ == '__main__':
    main()
