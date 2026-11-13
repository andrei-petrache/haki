from typing import Literal

from pydantic import Field, field_validator, model_validator

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
    # Barcode lookup through Open Food Facts (app/barcode.py); off, 404
    barcode_enabled: bool = False
    # Calls to Open Food Facts per pod and minute. It allows 100 a minute
    # per address and every pod leaves through the same one: keep the sum
    # over the replicas below 100
    off_requests_per_minute: int = Field(default=45, ge=1, le=100)
    # Password reset by e-mail (app/password_reset.py). Off by default and in
    # prod until a real mail provider exists (phase 7, Andrei's choice: it
    # costs money); off, its endpoints answer 404.
    password_reset_enabled: bool = False
    # "log" writes the reset link to the server log, "smtp" sends it through
    # SMTP_HOST (locally Mailpit, from compose). The log backend hands an
    # account to whoever can read the logs, so prod refuses it (below).
    mail_backend: Literal["log", "smtp"] = "log"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    mail_from: str = "Haki <no-reply@haki.invalid>"
    # Links in e-mails are built from this, never from a request's Host
    public_base_url: str = "http://127.0.0.1:8080"
    # "prod" turns on the checks that only prod needs
    environment: Literal["dev", "staging", "prod"] = "dev"

    @model_validator(mode="after")
    def prod_never_logs_reset_links(self) -> Settings:
        """A reset link in prod's logs would let anyone who reads them take
        over an account: fail at startup instead."""
        if (
            self.environment == "prod"
            and self.password_reset_enabled
            and self.mail_backend == "log"
        ):
            raise ValueError(
                "PASSWORD_RESET_ENABLED needs MAIL_BACKEND=smtp in prod: "
                "the log backend writes reset links to the log"
            )
        return self

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
