import os

# Tests must not depend on a local .env file or a running database.
# setdefault keeps a real value if one is already set (e.g. in CI).
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
