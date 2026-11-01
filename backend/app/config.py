from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

# backend/app/config.py -> parents[2] is the repository root, where .env lives
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# HS256 signs with a 256-bit key: anything shorter is easier to brute-force
MIN_JWT_SECRET_BYTES = 32
# The placeholder in .env.example starts with this; it is public on GitHub
PLACEHOLDER_PREFIX = "change-me"
GENERATE_HINT = 'python -c "import secrets; print(secrets.token_urlsafe(32))"'


class Settings(BaseSettings):
    """Application settings, read from environment variables or the .env file."""

    # hide_input_in_errors: a rejected secret must never be echoed into logs
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, extra="ignore", hide_input_in_errors=True
    )

    # The database: either the separate DB_* settings (any characters in the
    # password, nothing to escape) or one DATABASE_URL, whose password must
    # be percent-encoded (@ -> %40, ...). Kept for existing setups.
    db_user: str | None = None
    db_password: str | None = None
    db_host: str | None = None
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str | None = None
    database_url: str | None = None
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Each Argon2 hash or check allocates 64 MiB, so at most this many run at
    # once: about 4 x 64 MiB = 256 MiB. Size the pod's memory limit from it.
    password_hash_concurrency: int = Field(default=4, ge=1, le=64)
    # How long a login or signup waits for a free slot before getting a 503
    password_hash_wait_seconds: float = Field(default=2.0, ge=0, le=30)

    @field_validator("jwt_secret_key")
    @classmethod
    def jwt_secret_key_must_be_strong(cls, value: str) -> str:
        """Refuse keys anyone could know or guess, so the app fails at startup.

        Whoever knows the key can sign a token for any user id.
        """
        if value.startswith(PLACEHOLDER_PREFIX):
            raise ValueError(
                "JWT_SECRET_KEY is still the placeholder from .env.example; "
                f"generate one with: {GENERATE_HINT}"
            )
        if len(value.encode()) < MIN_JWT_SECRET_BYTES:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_BYTES} bytes; "
                f"generate one with: {GENERATE_HINT}"
            )
        return value

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


settings = Settings()
