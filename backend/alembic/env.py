"""Entorno Alembic: generar SQL offline no requiere credenciales ni conexion."""

from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.shared.infrastructure.model_registry import metadata


config = context.config
if config.config_file_name and config.get_section("loggers"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = metadata
if len(target_metadata.tables) != 11:
    raise CommandError('El registro ORM debe contener once tablas de aplicacion, incluido el envio de correo.')


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == 'table':
        return obj.schema in (None, 'public') and name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = Settings()
    url = settings.migration_database_url or settings.database_url
    engine = create_engine(
        url.get_secret_value(),
        poolclass=NullPool,
        connect_args={"connect_timeout": settings.database_connect_timeout, "options": "-c search_path=public"},
        echo=False,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                version_table_schema="public",
                compare_type=True,
                compare_server_default=True,
                include_schemas=True,
                include_object=include_object,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
