"""Pruebas de configuracion, respuesta HTTP y ciclo de vida de conexiones."""

import os
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.dependencies import get_db_session
from app.main import create_app
from app.shared.infrastructure.database import Database


TEST_URL = "postgresql+psycopg://test:private-test-password@127.0.0.1:5432/test"


def test_settings_environment_overrides_dotenv_without_exposing_password(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("DATABASE_URL=invalid-file-value\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    settings = Settings(_env_file=dotenv)
    assert settings.database_url.get_secret_value() == TEST_URL
    assert "private-test-password" not in repr(settings)
    assert "private-test-password" not in settings.model_dump_json()


@pytest.mark.parametrize("url", [
    "invalid-private-test-password",
    "sqlite:///private-test-password",
    "postgresql+psycopg://test:private-test-password@localhost/",
])
def test_invalid_database_settings_do_not_disclose_credentials(url):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=url)
    assert "private-test-password" not in str(error.value)


def test_migration_credentials_are_separate_and_hidden():
    migration_url = "postgresql+psycopg://owner:private-migration-password@127.0.0.1/test"
    settings = Settings(_env_file=None, database_url=TEST_URL, migration_database_url=migration_url)
    assert settings.database_url.get_secret_value() == TEST_URL
    assert settings.migration_database_url.get_secret_value() == migration_url
    assert "private-migration-password" not in settings.model_dump_json()


def test_public_configuration_rejects_unsafe_origins_and_production_http():
    for changes in ({'public_base_url': 'http://external.example.com'},
                    {'public_base_url': 'https://user:password@example.com'},
                    {'public_base_url': 'https://example.com/extra-path'},
                    {'oauth_redirect_uris': ['https://example.com/callback#fragment']},
                    {'app_env': 'production'}):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, database_url=TEST_URL, **changes)


def test_readiness_failure_is_generic_and_liveness_remains_available():
    settings = Settings(_env_file=None, database_url=TEST_URL)
    failing_session = Mock(spec=Session)
    failing_session.execute.side_effect = OperationalError(
        "SELECT 1", {}, RuntimeError("password=private-test-password"),
    )
    application = create_app(settings)
    application.dependency_overrides[get_db_session] = lambda: failing_session
    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Base de datos no disponible."}
        assert "private-test-password" not in response.text


def test_shutdown_disposes_database_pool():
    settings = Settings(_env_file=None, database_url=TEST_URL)
    with patch.object(Database, "dispose", autospec=True) as dispose:
        with TestClient(create_app(settings)):
            dispose.assert_not_called()
        dispose.assert_called_once()


@pytest.fixture
def postgres_settings():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requiere TEST_DATABASE_URL de una instancia PostgreSQL de prueba.")
    return Settings(
        _env_file=None,
        database_url=url,
        database_pool_size=1,
        database_max_overflow=0,
    )


@pytest.mark.parametrize("fail", [False, True])
def test_uncommitted_work_is_rolled_back(postgres_settings, fail):
    database = Database(postgres_settings)
    try:
        def perform_work():
            with database.session() as session:
                session.execute(text("CREATE TEMPORARY TABLE connection_rollback_probe (id INTEGER)"))
                session.execute(text("INSERT INTO connection_rollback_probe VALUES (1)"))
                if fail:
                    raise RuntimeError("Simular un caso de uso fallido")

        if fail:
            with pytest.raises(RuntimeError, match="caso de uso fallido"):
                perform_work()
        else:
            perform_work()
        with database.session() as session:
            assert session.execute(text("SELECT to_regclass('pg_temp.connection_rollback_probe')")).scalar_one() is None
    finally:
        database.dispose()


def test_real_postgres_readiness_does_not_create_tables(postgres_settings):
    database = Database(postgres_settings)
    count_tables = text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
    try:
        with database.session() as session:
            before = session.execute(count_tables).scalar_one()
        with TestClient(create_app(postgres_settings)) as client:
            response = client.get("/health/ready")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "database": "ok"}
        with database.session() as session:
            assert session.execute(count_tables).scalar_one() == before
    finally:
        database.dispose()
