"""A migration blocked by an open transaction gives up after the lock
timeout set in migrations/env.py, instead of waiting while every request on
the table queues behind it.

The test runs a real `alembic downgrade -1` against the test database while
another transaction holds every table. With the timeout it fails and the
schema stays at head. Without it the downgrade would wait: the test then
cancels the waiting backend before letting go of the tables, so no
migration ever runs on the test database.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text

from app.models import Base

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
# Well above the 10 s timeout, well below "the line is gone"
GIVE_UP_AFTER = 25


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def test_a_blocked_migration_gives_up_and_changes_nothing(pg_engine: Engine) -> None:
    head = ScriptDirectory.from_config(
        Config(str(BACKEND / "alembic.ini"))
    ).get_current_head()
    env = {key: value for key, value in os.environ.items() if not key.startswith("DB_")}
    env["DATABASE_URL"] = pg_engine.url.render_as_string(hide_password=False)

    with pg_engine.connect() as holder:
        transaction = holder.begin()
        # Reading a table takes a lock that any ALTER or DROP on it waits for
        for table in Base.metadata.sorted_tables:
            holder.execute(select(text("1")).select_from(table).limit(1))
        start = time.monotonic()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "downgrade", "-1"],
                cwd=BACKEND,
                env=env,
                capture_output=True,
                text=True,
                timeout=GIVE_UP_AFTER,
            )
        except subprocess.TimeoutExpired:
            # Cancel the waiting migration before the lock is released
            holder.execute(
                text(
                    "SELECT pg_cancel_backend(pid) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            transaction.rollback()
            pytest.fail(f"The migration still waited after {GIVE_UP_AFTER} s")
        elapsed = time.monotonic() - start
        transaction.rollback()

    assert result.returncode != 0
    assert "lock timeout" in result.stderr
    assert elapsed < GIVE_UP_AFTER
    assert current_revision(pg_engine) == head
