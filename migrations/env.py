"""Alembic migration environment.

The database URL and target metadata come from the application itself, so
migrations always run against the same configuration the app uses. As domain
models are added in later phases they must be imported here (directly or via a
package) so ``Base.metadata`` sees them and autogenerate/`alembic check` work.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import modules that define ORM models so they register on ``Base.metadata``
# and autogenerate / ``alembic check`` can see them. Importing the events
# package pulls in every kernel model (event store, raw store). Add new model
# modules here as bounded contexts are introduced.
from mylife.core import events as _events  # noqa: F401
from mylife.core.config import get_settings
from mylife.db.base import Base
from mylife.finance import models as _finance_models  # noqa: F401
from mylife.goals import models as _goals_models  # noqa: F401
from mylife.identity import audit as _identity_audit  # noqa: F401
from mylife.identity import consent as _identity_consent  # noqa: F401
from mylife.identity import models as _identity_models  # noqa: F401
from mylife.timeline import entities as _timeline_entities  # noqa: F401

# Alembic Config object (values from alembic.ini).
config = context.config

# Inject the application's database URL (env-driven, local default = SQLite).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata the autogenerate/`check` commands compare against. Domain models
# register on this Base as they are introduced (T1.2 onward).
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DBAPI connection)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
