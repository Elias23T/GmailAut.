"""Prepara secretos locales sin sobrescribir las claves existentes ni mostrarlas."""

import base64
import os
from pathlib import Path
import secrets

from dotenv import dotenv_values, set_key


def main() -> None:
    backend = Path(__file__).resolve().parents[1] / 'backend'
    env = backend / '.env'
    if not env.exists():
        with env.open('x', encoding='utf-8') as output:
            output.write((backend / '.env.example').read_text(encoding='utf-8'))
    values = dotenv_values(env)
    factories = {
        'JWT_SECRET': lambda: secrets.token_urlsafe(48),
        'MAILBOX_ENCRYPTION_KEY': lambda: base64.urlsafe_b64encode(os.urandom(32)).decode('ascii'),
    }
    changed = []
    for key, generate in factories.items():
        if not values.get(key) or values[key].startswith('CHANGE_ME'):
            set_key(env, key, generate())
            changed.append(key)
    print('Claves configuradas: ' + ', '.join(changed) if changed else 'Se conservan las claves existentes.')


if __name__ == '__main__':
    main()
