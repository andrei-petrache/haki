from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db_config import DatabaseSettings
from app.models import Base

config = context.config

# The database URL comes from the environment / .env, never from alembic.ini,
# so no credentials end up in Git. Only the database settings are loaded, not
# the app's (app.config): migrations need no JWT secret, so they are not given
# one (least privilege). Never import app.config here: loading it requires
# JWT_SECRET_KEY. The URL is passed as an object, not through
# config.set_main_option: Alembic's config treats % as interpolation, which
# breaks percent-encoded passwords.
db_url = DatabaseSettings().db_url

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The models' metadata lets autogenerate compare code against the database.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL scripts without connecting to the database."""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations directly against the database."""
    connectable = create_engine(db_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
