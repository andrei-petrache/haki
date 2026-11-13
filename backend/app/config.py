from pydantic import Field, field_validator

from app.db_config import DatabaseSettings

# HS256 signs with a 256-bit key: anything shorter is easier to brute-force
MIN_JWT_SECRET_BYTES = 32
# The placeholder in .env.example starts with this; it is public on GitHub
PLACEHOLDER_PREFIX = "change-me"
GENERATE_HINT = 'python -c "import secrets; print(secrets.token_urlsafe(32))"'


class Settings(DatabaseSettings):
    """Application settings: the database (DatabaseSettings) plus auth.

    Read from environment variables or the .env file, like DatabaseSettings.
    """

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Each Argon2 hash or check allocates 64 MiB, so at most this many run at
    # once: about 4 x 64 MiB = 256 MiB. Size the pod's memory limit from it.
    password_hash_concurrency: int = Field(default=4, ge=1, le=64)
    # How long a login or signup waits for a free slot before getting a 503
    password_hash_wait_seconds: float = Field(default=2.0, ge=0, le=30)
    # Prometheus metrics are served on this port, never on the API's (see
    # app/metrics.py). 0 turns the metrics server off (most tests).
    metrics_port: int = Field(default=9000, ge=0, le=65535)
    # Body weight and the adaptive target (app/body.py). Weight is health
    # data (GDPR Art. 9): off until users can give consent (phase 4), so
    # off by default and in prod; staging turns it on. Off, every endpoint
    # of it answers 404 as if it did not exist.
    body_weight_enabled: bool = False

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
