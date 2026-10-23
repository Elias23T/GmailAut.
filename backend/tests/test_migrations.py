"""Validacion exclusivamente offline; estas pruebas no aplican migraciones."""

import argparse
import ast
from io import StringIO
from pathlib import Path
import re
import shutil

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util import CommandError
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
INITIAL_REVISION = "20261021_0001"
HEAD_REVISION = '20261023_0008'
TABLES = [
    "users", "tenants", "memberships", "mailboxes", "mailbox_credentials",
    "mailbox_grants", "audit_events",
]


def alembic_config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=StringIO())


@pytest.fixture(autouse=True)
def forbid_database_connections(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Las pruebas de migraciones deben ejecutarse sin conexion ni credenciales.")

    monkeypatch.setattr("sqlalchemy.create_engine", fail)
    monkeypatch.setattr("app.core.config.Settings", fail)


def test_initial_revision_has_one_head_and_no_parent():
    scripts = ScriptDirectory.from_config(alembic_config())
    assert scripts.get_heads() == [HEAD_REVISION]
    assert scripts.get_revision(INITIAL_REVISION).down_revision is None


def test_offline_upgrade_preserves_the_seven_table_schema():
    config = alembic_config()
    command.upgrade(config, INITIAL_REVISION, sql=True)
    sql = config.output_buffer.getvalue()
    created = re.findall(r"CREATE TABLE public\.(\w+)\s*\(", sql)
    assert created == ["alembic_version", *TABLES]
    assert "oauth_" not in sql
    assert "CREATE TRIGGER" not in sql.upper()
    assert "CREATE FUNCTION" not in sql.upper()
    assert "CREATE ROLE" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "BYTEA" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    for table, constraint, reference in [
        ("mailbox_grants", "fk_mailbox_grants_membership", "memberships"),
        ("mailbox_grants", "fk_mailbox_grants_mailbox", "mailboxes"),
        ("mailbox_grants", "fk_mailbox_grants_grantor", "memberships"),
        ("audit_events", "fk_audit_events_mailbox", "mailboxes"),
    ]:
        table_sql = sql.split(f"CREATE TABLE public.{table} (", 1)[1].split(";", 1)[0]
        assert f"CONSTRAINT {constraint} FOREIGN KEY(tenant_id," in table_sql
        assert f"REFERENCES public.{reference} (tenant_id, id) ON DELETE RESTRICT" in table_sql
    assert "CHECK (mailbox_id IS NULL OR tenant_id IS NOT NULL)" in sql
    assert "CREATE UNIQUE INDEX uq_users_email_normalized ON public.users (lower(email))" in sql
    assert "CREATE UNIQUE INDEX uq_mailboxes_tenant_email_normalized ON public.mailboxes (tenant_id, lower(email))" in sql
    assert "CREATE INDEX ix_audit_events_tenant_created_at ON public.audit_events (tenant_id, created_at DESC)" in sql


def test_offline_downgrade_drops_tables_in_reverse_dependency_order():
    config = alembic_config()
    command.downgrade(config, f"{INITIAL_REVISION}:base", sql=True)
    sql = config.output_buffer.getvalue()
    dropped = re.findall(r"DROP TABLE public\.(\w+)", sql)
    assert dropped == list(reversed(TABLES))
    assert "DELETE FROM public.alembic_version" in sql


def test_metadata_registers_core_oauth_and_outgoing_tables():
    from app.shared.infrastructure.model_registry import metadata
    assert set(metadata.tables) == set(TABLES + ['oauth_clients', 'oauth_authorization_codes', 'oauth_tokens', 'outgoing_messages'])


def test_template_creates_a_valid_manual_revision_without_connecting(tmp_path):
    script_directory = tmp_path / "alembic"
    shutil.copytree(BACKEND_ROOT / "alembic", script_directory, ignore=shutil.ignore_patterns("__pycache__"))
    config = alembic_config()
    config.set_main_option("script_location", str(script_directory))
    generated = command.revision(config, message="future change", rev_id="test_future")
    assert generated.down_revision == HEAD_REVISION
    ast.parse(Path(generated.path).read_text(encoding="utf-8"))


def test_oauth_revision_is_additive_and_has_no_triggers():
    config = alembic_config()
    command.upgrade(config, f'{INITIAL_REVISION}:20261021_0002', sql=True)
    sql = config.output_buffer.getvalue()
    assert 'ADD COLUMN is_platform_admin BOOLEAN' in sql
    assert 'uq_users_single_platform_admin' in sql
    assert re.findall(r'CREATE TABLE public\.(\w+)', sql) == ['oauth_clients', 'oauth_authorization_codes', 'oauth_tokens']
    assert 'DROP TABLE' not in sql and 'CREATE TRIGGER' not in sql and 'CREATE FUNCTION' not in sql


def test_cascade_revision_only_changes_foreign_keys():
    config = alembic_config()
    command.upgrade(config, '20261021_0003:20261021_0004', sql=True)
    sql = config.output_buffer.getvalue()
    assert sql.count('ON DELETE CASCADE') == 13
    for statement in ('DELETE FROM', 'DROP TABLE', 'CREATE TABLE', 'CREATE TRIGGER', 'CREATE FUNCTION'):
        assert statement not in sql
    assert 'REFERENCES public.users' not in sql


def test_webmail_revision_adds_only_an_optional_column_and_constraint():
    config = alembic_config()
    command.upgrade(config, '20261022_0007:20261023_0008', sql=True)
    sql = config.output_buffer.getvalue()
    assert 'ADD COLUMN webmail_url TEXT' in sql
    assert 'ck_mailboxes_webmail_url' in sql
    for statement in ('DROP TABLE', 'DELETE FROM', 'CREATE TABLE', 'CREATE TRIGGER'):
        assert statement not in sql
