"""Configuracion de produccion y generacion de entornos sin secretos visibles."""
import base64
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError
from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings


def generator():
    path = Path(__file__).resolve().parents[2] / 'scripts/configure_production.py'
    spec = importlib.util.spec_from_file_location('configure_production', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_production_rejects_missing_keys_placeholders_and_private_mail_hosts():
    values = dict(_env_file=None, app_env='production',
        database_url='postgresql+psycopg://app:private-db-password@127.0.0.1/test',
        public_base_url='https://correo.example.com', frontend_url='https://correo.example.com',
        jwt_secret='production-test-secret-' + 'x' * 40,
        mailbox_encryption_key=base64.urlsafe_b64encode(b'x' * 32).decode())
    assert Settings(**values).app_env == 'production'
    for change in ({'jwt_secret': None}, {'jwt_secret': 'short'}, {'jwt_secret': 'CHANGE_ME' + 'x' * 40},
                   {'mailbox_encryption_key': None}, {'mailbox_encryption_key': 'invalid'},
                   {'imap_allow_private_hosts': True}, {'smtp_allow_private_hosts': True}):
        with pytest.raises(ValidationError) as error:
            Settings(**(values | change))
        assert 'private-db-password' not in str(error.value)


def test_production_environment_round_trips_complex_passwords_and_refuses_overwrite(tmp_path, capsys, monkeypatch):
    module = generator()
    password = 'private@:#$"\\ password'
    url = URL.create('postgresql+psycopg', username='corporate_mail_app', password=password,
                     host='127.0.0.1', database='CorreoCorpAut').render_as_string(hide_password=False)
    output = tmp_path / 'backend.env'
    module.create_environment(output, 'https://correo.example.com', url, ['https://chatgpt.com/connector_platform_oauth_redirect'])
    for name in dotenv_values(output):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=output)
    assert settings.app_env == 'production'
    assert settings.public_base_url == settings.frontend_url == 'https://correo.example.com'
    assert settings.cors_origins == ['https://correo.example.com']
    assert make_url(settings.database_url.get_secret_value()).password == password
    assert len(base64.urlsafe_b64decode(settings.mailbox_encryption_key.get_secret_value())) == 32
    assert not capsys.readouterr().out
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        module.create_environment(output, 'https://correo.example.com', url, settings.oauth_redirect_uris)
    assert output.read_bytes() == original


def test_production_generator_preserves_existing_mailbox_key_and_version(tmp_path, monkeypatch):
    key = base64.urlsafe_b64encode(b'y' * 32).decode()
    previous = tmp_path / 'previous.env'
    previous.write_text('MAILBOX_ENCRYPTION_KEY=' + key + '\nMAILBOX_ENCRYPTION_KEY_VERSION=3\n', encoding='utf-8')
    output = tmp_path / 'production.env'
    generator().create_environment(output, 'https://correo.example.com',
        'postgresql+psycopg://app:private-db-password@127.0.0.1/test',
        ['https://chatgpt.com/connector_platform_oauth_redirect'], previous)
    for name in dotenv_values(output):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=output)
    assert settings.mailbox_encryption_key.get_secret_value() == key
    assert settings.mailbox_encryption_key_version == 3


def test_production_https_discovery_and_readiness_use_own_domain_without_tunnel():
    import os
    from fastapi.testclient import TestClient
    from app.main import create_app

    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requiere PostgreSQL temporal de validacion.')
    origin = 'https://correo.example.com'
    settings = Settings(_env_file=None, app_env='production', database_url=url,
        public_base_url=origin, frontend_url=origin, cors_origins=[origin],
        jwt_secret='production-test-secret-' + 'x' * 40,
        mailbox_encryption_key=base64.urlsafe_b64encode(b'z' * 32).decode())
    with TestClient(create_app(settings), base_url=origin) as client:
        assert client.get('/health/ready').json() == {'status': 'ok', 'database': 'ok'}
        discovery = client.get('/.well-known/oauth-authorization-server').json()
        assert discovery['issuer'] == origin
        assert discovery['authorization_endpoint'] == origin + '/oauth/authorize'
        assert discovery['token_endpoint'] == origin + '/oauth/token'
        resource = client.get('/.well-known/oauth-protected-resource/mcp').json()
        assert resource['resource'] == origin + '/mcp'
        assert resource['authorization_servers'] == [origin]
        challenge = client.get('/mcp')
        assert challenge.status_code == 401
        assert origin + '/.well-known/oauth-protected-resource/mcp' in challenge.headers['www-authenticate']
        assert 'scope="mail:read mail:send"' in challenge.headers['www-authenticate']
