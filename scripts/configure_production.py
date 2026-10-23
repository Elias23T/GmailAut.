"""Genera un entorno de produccion sin mostrar secretos ni reemplazar archivos."""
import argparse
import base64
from getpass import getpass
import json
import os
from pathlib import Path
import secrets
import sys

from dotenv import dotenv_values
from sqlalchemy.engine import URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import Settings


def create_environment(output: Path, origin: str, database_url: str, callbacks: list[str], reuse_key_file: Path | None = None):
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii')
    version = 1
    if reuse_key_file:
        values = dotenv_values(reuse_key_file, interpolate=False)
        key = values.get('MAILBOX_ENCRYPTION_KEY') or ''
        version = int(values.get('MAILBOX_ENCRYPTION_KEY_VERSION') or 1)
    settings = Settings(_env_file=None, app_env='production', database_url=database_url,
        public_base_url=origin, frontend_url=origin, cors_origins=[origin], oauth_redirect_uris=callbacks,
        jwt_secret=secrets.token_urlsafe(48), mailbox_encryption_key=key, mailbox_encryption_key_version=version)
    environment = {
        'APP_ENV': 'production', 'PUBLIC_BASE_URL': settings.public_base_url, 'FRONTEND_URL': settings.frontend_url,
        'CORS_ORIGINS': json.dumps([settings.public_base_url]), 'OAUTH_REDIRECT_URIS': json.dumps(callbacks),
        'DATABASE_URL': database_url, 'JWT_SECRET': settings.jwt_secret.get_secret_value(), 'JWT_MINUTES': '30',
        'MAILBOX_ENCRYPTION_KEY': key, 'MAILBOX_ENCRYPTION_KEY_VERSION': str(version),
        'DATABASE_POOL_SIZE': '2', 'DATABASE_MAX_OVERFLOW': '3', 'DATABASE_POOL_TIMEOUT': '10',
        'DATABASE_CONNECT_TIMEOUT': '5', 'IMAP_TIMEOUT': '10', 'IMAP_MAX_MESSAGE_BYTES': '1048576',
        'IMAP_ALLOW_PRIVATE_HOSTS': 'false', 'SMTP_TIMEOUT': '10', 'SMTP_ALLOW_PRIVATE_HOSTS': 'false',
    }
    # Doble comilla y escapes compatibles con python-dotenv y EnvironmentFile de systemd.
    content = ''.join(f'{name}={json.dumps(value)}\n' for name, value in environment.items())
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--origin', required=True, help='Origen HTTPS, por ejemplo https://correo.example.com')
    parser.add_argument('--database', default='CorreoCorpAut')
    parser.add_argument('--db-user', default='corporate_mail_app')
    parser.add_argument('--db-host', default='127.0.0.1')
    parser.add_argument('--db-port', type=int, default=5432)
    parser.add_argument('--callback', action='append', help='Callback exacto de ChatGPT; admite varios')
    parser.add_argument('--reuse-encryption-key-file', type=Path, help='Entorno anterior, si se trasladan buzones cifrados')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('El archivo ya existe. Se conserva sin cambios; editalo para actualizarlo.')
    password = getpass('Contraseña PostgreSQL del rol de la aplicacion: ')
    if not password:
        parser.error('La contraseña PostgreSQL es obligatoria.')
    database_url = URL.create('postgresql+psycopg', username=args.db_user, password=password,
        host=args.db_host, port=args.db_port, database=args.database).render_as_string(hide_password=False)
    try:
        create_environment(args.output, args.origin.rstrip('/'), database_url,
            args.callback or ['https://chatgpt.com/connector_platform_oauth_redirect'], args.reuse_encryption_key_file)
    except (ValueError, OSError):
        parser.error('No se genero el archivo. Revisa el origen HTTPS, permisos y la clave de cifrado anterior si la indicaste.')
    print(f'Entorno de produccion creado en {args.output}. No se mostraron las claves.')


if __name__ == '__main__':
    main()
