"""Inicializacion local: python -m app.cli create-admin --username admin"""
import argparse
from getpass import getpass
import re
from sqlalchemy import select
from pydantic import TypeAdapter, EmailStr
from app.core.config import Settings
from app.modules.identity.domain.entities import User
from app.modules.memberships.domain.entities import Membership
from app.modules.tenants.domain.entities import Tenant
from app.shared.infrastructure.database import Database
from app.shared.infrastructure.unit_of_work import SQLUnitOfWork
from app.shared.infrastructure.security import ArgonPasswords


def create_admin(session, email, name, password, username=None):
    if len(password) < 12:
        raise ValueError('La contraseña debe tener al menos 12 caracteres.')
    if session.scalar(select(User).where(User.is_platform_admin.is_(True))):
        raise ValueError('Ya existe el administrador. No se creará una segunda cuenta administradora.')
    if bool(email) == bool(username):
        raise ValueError('Indica exactamente uno: correo o nombre de usuario.')
    if email:
        email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
    if username:
        username = username.strip().lower()
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{2,31}', username):
            raise ValueError('El usuario debe tener entre 3 y 32 caracteres y comenzar con una letra.')
    uow = SQLUnitOfWork(session)
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
    for tenant in session.scalars(select(Tenant)):
        member = uow.memberships.for_user(tenant.id, user.id)
        if member:
            member.role, member.status = 'owner', 'active'
        else:
            uow.memberships.add(Membership(tenant_id=tenant.id, user_id=user.id, role='owner'))


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
                password = getpass('Contraseña del administrador (mínimo 12 caracteres): ')
                if password != getpass('Repetir contraseña: '):
                    parser.error('Las contraseñas no coinciden.')
                create_admin(session, args.email, args.name, password, args.username)
            else:
                if session.scalar(select(User).where(User.is_platform_admin.is_(True))):
                    parser.error('Ya existe el administrador.')
                uow = SQLUnitOfWork(session)
                user = uow.users.by_login(args.email or args.username)
                if not user or user.status != 'active':
                    parser.error('No existe una cuenta activa con ese correo o usuario.')
                user.is_platform_admin = True
                attach_tenants(session, uow, user)
                uow.commit()
        print('Administrador configurado. Inicia sesión desde la interfaz.')
    except ValueError as error:
        parser.error(str(error))
    finally:
        database.dispose()


if __name__ == '__main__':
    main()
