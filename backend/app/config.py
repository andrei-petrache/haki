from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    database_url: str
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


settings = Settings()
