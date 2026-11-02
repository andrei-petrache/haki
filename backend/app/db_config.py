from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

# backend/app/db_config.py -> parents[2] is the repository root, where .env lives
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class DatabaseSettings(BaseSettings):
    """How to reach the database, read from environment variables or .env.

    On its own for the migrations, which need nothing else: loading it never
    asks for the JWT secret, so the migration Job does not get that secret.
    The app's Settings (app/config.py) extends it.
    """

    # hide_input_in_errors: a rejected secret must never be echoed into logs
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, extra="ignore", hide_input_in_errors=True
    )

    # Either the separate DB_* settings (any characters in the password,
    # nothing to escape) or one DATABASE_URL, whose password must be
    # percent-encoded (@ -> %40, ...). Kept for existing setups.
    db_user: str | None = None
    db_password: str | None = None
    db_host: str | None = None
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str | None = None
    database_url: str | None = None

    @model_validator(mode="after")
    def database_is_configured_once(self) -> Self:
        """Exactly one way to reach the database, so it is never ambiguous."""
        parts = (self.db_user, self.db_password, self.db_host, self.db_name)
        if self.database_url and any(parts):
            raise ValueError("set either DATABASE_URL or the DB_* settings, not both")
        if not self.database_url and not all(parts):
            raise ValueError(
                "set DB_USER, DB_PASSWORD, DB_HOST and DB_NAME (or DATABASE_URL)"
            )
        return self

    @property
    def db_url(self) -> URL:
        """The database URL as an object: the password is never escaped by hand.

        Pass this to SQLAlchemy and Alembic directly, never as a string.
        """
        if self.database_url:
            return make_url(self.database_url)
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
