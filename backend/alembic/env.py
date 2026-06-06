"""Alembic migration environment for finsight.

The database URL is read from the application settings
(``app.config.get_settings().database_url``) rather than a hardcoded value in
``alembic.ini`` so migrations always target the database the app uses.
``Base.metadata`` is imported from ``app.db.database`` and the models module is
imported for its registration side effects, giving autogenerate the full schema.
SQLite ``ALTER`` support is enabled via batch mode (``render_as_batch=True``).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.config import get_settings
from app.db import models  # noqa: F401  (register models via import side effect)
from app.db.database import Base
from sqlalchemy import engine_from_config, pool

# Alembic Config object, providing access to values within alembic.ini.
config = context.config

# Resolve the database URL from application settings (not the ini file), unless a
# caller already supplied one programmatically (e.g. tests passing a temp URL).
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an Engine and live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
