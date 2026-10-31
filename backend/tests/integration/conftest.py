import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.models import User
from tests.integration.database import check_test_database_url

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    """Engine for the migrated test database; skips when none is configured."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    # Checked before connecting: a wrong URL never reaches the database
    engine = create_engine(check_test_database_url(url))

    # The schema must come from the migrations, not from create_all
    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        pytest.fail(
            f"Test database is at revision {current}, expected {head}: "
            "run `alembic upgrade head` against it first"
        )

    yield engine
    engine.dispose()


@pytest.fixture
def db(pg_engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after each test.

    Nothing a test writes is ever committed, so tests cannot see each other's
    data and the database stays empty.
    """
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()


@pytest.fixture
def make_user(db: Session) -> Callable[[str], User]:
    def make(email: str) -> User:
        user = User(email=email, password_hash="not-a-real-hash")
        db.add(user)
        db.flush()
        return user

    return make


@pytest.fixture
def pg_client(db: Session) -> Iterator[TestClient]:
    """The API running on the rolled-back session of the `db` fixture."""
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
