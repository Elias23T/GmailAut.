"""Valida el SQL en un cluster PostgreSQL temporal sin tocar servicios existentes."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, help="Directorio con initdb, pg_ctl y psql")
    parser.add_argument("--include-oauth", action="store_true", help="Validar tambien las restricciones OAuth del esquema completo")
    parser.add_argument("--backend-python", type=Path, help="Python del backend para ejecutar sus pruebas contra el cluster temporal")
    args = parser.parse_args()
    suffix = ".exe" if os.name == "nt" else ""
    binaries: dict[str, str] = {}
    for name in ("initdb", "pg_ctl", "psql"):
        candidate = args.pg_bin / f"{name}{suffix}" if args.pg_bin else None
        executable = str(candidate) if candidate and candidate.is_file() else shutil.which(name)
        if not executable:
            parser.error(f"No se encontro {name}; indicar --pg-bin.")
        binaries[name] = executable

    validation_root = PROJECT_ROOT / ".local-validation"
    validation_root.mkdir(exist_ok=True)
    cluster_root = Path(tempfile.mkdtemp(prefix="schema-", dir=validation_root)).resolve()
    if not cluster_root.is_relative_to(validation_root.resolve()):
        raise RuntimeError("El cluster temporal debe permanecer dentro del proyecto.")
    data_dir = cluster_root / "data"
    log_path = cluster_root / "postgres.log"
    password_file = cluster_root / "password.txt"
    password = secrets.token_urlsafe(32)
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("PG")}
    environment["PGPASSWORD"] = password
    environment["PGCONNECT_TIMEOUT"] = "10"
    def run(command: list[str]) -> str:
        # pg_ctl puede heredar sus salidas al servidor en Windows. Un archivo
        # evita esperar indefinidamente al EOF de una tuberia del proceso hijo.
        output_path = cluster_root / f"command-{secrets.token_hex(4)}.log"
        with output_path.open("w", encoding="utf-8") as output:
            result = subprocess.run(
                command,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        result_text = output_path.read_text(encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError(result_text)
        return result_text

    stop_required = False
    try:
        password_file.write_text(password + "\n", encoding="utf-8")
        run([
            binaries["initdb"], "-D", str(data_dir), "-U", "schema_validator",
            "--auth=scram-sha-256", "--pwfile", str(password_file),
            "--no-locale", "--encoding=UTF8",
        ])
        password_file.unlink()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = str(listener.getsockname()[1])
        stop_required = True
        run([
            binaries["pg_ctl"], "-D", str(data_dir), "-l", str(log_path),
            "-o", f"-h 127.0.0.1 -p {port}", "-w", "start",
        ])
        psql = [
            binaries["psql"], "-X", "-w", "-h", "127.0.0.1", "-p", port,
            "-U", "schema_validator", "-v", "ON_ERROR_STOP=1",
        ]
        # La base real se crea manualmente; esta solo pertenece al cluster de prueba.
        run(psql + [
            "-d", "postgres", "-c",
            "CREATE DATABASE corporate_mail_ai WITH ENCODING = 'UTF8' TEMPLATE = template0",
        ])
        run(psql + ["-d", "corporate_mail_ai", "-f", str(PROJECT_ROOT / "seeder/01_schema.sql")])
        if args.backend_python:
            run(psql + ["-d", "postgres", "-c", "CREATE DATABASE corporate_mail_migrations WITH ENCODING = 'UTF8' TEMPLATE = template0"])
            environment['DATABASE_URL'] = f'postgresql+psycopg://schema_validator:{password}@127.0.0.1:{port}/corporate_mail_migrations'
            environment['MIGRATION_DATABASE_URL'] = environment['DATABASE_URL']
            alembic = [str(args.backend_python.resolve()), '-m', 'alembic', '-c', str(PROJECT_ROOT / 'backend/alembic.ini')]
            print(run(alembic + ['upgrade', 'head']).strip())
            # Comparar columnas, valores predeterminados, restricciones e indices
            # del SQL real con una instalacion Alembic desde cero.
            signature_sql = """
                SELECT jsonb_build_object(
                    'columns', (SELECT jsonb_agg(jsonb_build_array(table_name, column_name,
                        data_type, udt_name, is_nullable, column_default, ordinal_position)
                        ORDER BY table_name, ordinal_position)
                        FROM information_schema.columns WHERE table_schema = 'public'),
                    'constraints', (SELECT jsonb_agg(jsonb_build_array(t.relname, c.conname,
                        pg_get_constraintdef(c.oid)) ORDER BY t.relname, c.conname)
                        FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
                        JOIN pg_namespace n ON n.oid = t.relnamespace WHERE n.nspname = 'public'),
                    'indexes', (SELECT jsonb_agg(jsonb_build_array(tablename, indexname, indexdef)
                        ORDER BY tablename, indexname) FROM pg_indexes WHERE schemaname = 'public')
                )::text
            """
            snapshot = run(psql + ['-d', 'corporate_mail_ai', '-Atc', signature_sql]).strip()
            migrated = run(psql + ['-d', 'corporate_mail_migrations', '-Atc', signature_sql]).strip()
            if snapshot != migrated:
                raise RuntimeError('El SQL consolidado y las migraciones no producen el mismo esquema.')
            print('OK: el SQL consolidado coincide con las migraciones completas.')
            environment['DATABASE_URL'] = f'postgresql+psycopg://schema_validator:{password}@127.0.0.1:{port}/corporate_mail_ai'
            environment['MIGRATION_DATABASE_URL'] = environment['DATABASE_URL']
            print(run(alembic + ['check']).strip())
        # Rol exclusivo del cluster temporal para comprobar la proteccion de
        # auditoria. No se crea ni modifica ningun rol en la base del usuario.
        run(psql + ['-d', 'corporate_mail_ai', '-c', """
            CREATE ROLE corporate_mail_app LOGIN
                NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
            REVOKE CREATE ON SCHEMA public FROM PUBLIC;
            GRANT CONNECT ON DATABASE corporate_mail_ai TO corporate_mail_app;
            GRANT USAGE ON SCHEMA public TO corporate_mail_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON
                public.users, public.tenants, public.memberships, public.mailboxes,
                public.mailbox_credentials, public.mailbox_grants, public.oauth_clients,
                public.oauth_authorization_codes, public.oauth_tokens, public.outgoing_messages TO corporate_mail_app;
            GRANT SELECT, INSERT ON public.audit_events TO corporate_mail_app;
        """])
        if args.include_oauth:
            run(psql + [
                "-d", "corporate_mail_ai", "-f",
                str(PROJECT_ROOT / "backend/tests/sql/oauth_constraints.sql"),
            ])
        result = run(psql + [
            "-d", "corporate_mail_ai", "-f",
            str(PROJECT_ROOT / "backend/tests/sql/schema_constraints.sql"),
        ])
        print(result.strip())
        count = run(psql + [
            "-d", "corporate_mail_ai", "-Atc",
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'",
        ]).strip()
        expected_tables = 12
        if count != str(expected_tables):
            raise RuntimeError(f"Se esperaban {expected_tables} tablas, se encontraron {count}.")
        trigger_count = run(psql + [
            "-d", "corporate_mail_ai", "-Atc",
            "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND NOT t.tgisinternal",
        ]).strip()
        if trigger_count != "0":
            raise RuntimeError("El esquema no debe contener triggers de aplicacion.")
        rows = run(psql + ["-d", "corporate_mail_ai", "-Atc", "SELECT count(*) FROM users"]).strip()
        if rows != "0":
            raise RuntimeError("La prueba dejo usuarios residuales.")
        print(f"OK: {expected_tables} tablas, sin triggers de aplicacion ni datos de prueba residuales.")
        if args.backend_python:
            environment["TEST_DATABASE_URL"] = (
                f"postgresql+psycopg://schema_validator:{password}@127.0.0.1:{port}/corporate_mail_ai"
            )
            print(run([
                str(args.backend_python.resolve()), "-m", "pytest",
                str(PROJECT_ROOT / "backend/tests"), "-q", "-p", "no:cacheprovider",
            ]).strip())
    finally:
        if stop_required and (data_dir / "postmaster.pid").exists():
            run([binaries["pg_ctl"], "-D", str(data_dir), "-m", "fast", "-w", "stop"])
        # Solo se elimina el directorio unico creado arriba, dentro del proyecto.
        if cluster_root.is_relative_to(validation_root.resolve()):
            shutil.rmtree(cluster_root)


if __name__ == "__main__":
    main()
