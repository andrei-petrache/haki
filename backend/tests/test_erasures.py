"""The erasure log a restore applies again (app/erasures.py).

A restore is simulated by putting rows back as an older dump would hold
them, after the erasure happened through the API."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import erasures
from app.body import server_today
from app.config import settings
from app.consent import CURRENT_VERSIONS
from app.models import Base, BodyWeight, Consent, Erasure, Food, User
from tests.conftest import register_and_login
from tests.test_delete_account import PASSWORD

PATH = "/auth/me/consents/health_data"


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "body_weight_enabled", True)


def me(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    return client.get("/auth/me", headers=headers).json()


def as_stored(value: str) -> datetime:
    """A created_at from the API as the database holds it (SQLite: naive UTC).
    A time without a zone is UTC already, never the machine's local time."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment


def restore_user(session: Session, user: dict[str, Any]) -> None:
    session.add(
        User(
            id=user["id"],
            email=user["email"],
            password_hash="from-the-dump",
            created_at=as_stored(user["created_at"]),
        )
    )
    session.flush()


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_a_deleted_account_is_deleted_again_after_a_restore(
    client: TestClient, session: Session
) -> None:
    headers = register_and_login(client, "gone@example.com")
    user = me(client, headers)
    client.request("DELETE", "/auth/me", json={"password": PASSWORD}, headers=headers)
    log = erasures.read_log(session)
    # The restored dump still has the account and its food
    restore_user(session, user)
    session.add(
        Food(
            user_id=user["id"],
            name="Oats",
            calories_per_100g=389,
            protein_per_100g=17,
            carbs_per_100g=66,
            fat_per_100g=7,
        )
    )
    session.commit()

    counts = erasures.reapply(session, log)

    assert counts.accounts == 1
    assert session.get(User, user["id"]) is None
    assert count(session, Food) == 0


def test_an_id_given_out_again_after_a_restore_is_left_alone(
    client: TestClient, session: Session
) -> None:
    headers = register_and_login(client, "gone@example.com")
    user = me(client, headers)
    client.request("DELETE", "/auth/me", json={"password": PASSWORD}, headers=headers)
    log = erasures.read_log(session)
    # The restore reset the id sequence: someone new got the same id
    newcomer = user | {
        "email": "new@example.com",
        "created_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }
    restore_user(session, newcomer)
    session.commit()

    counts = erasures.reapply(session, log)

    assert counts.accounts == 0
    assert session.get(User, user["id"]) is not None


def test_a_withdrawal_is_applied_again_after_a_restore(
    client: TestClient, session: Session
) -> None:
    headers = register_and_login(client, "weighed@example.com")
    user_id = me(client, headers)["id"]
    body = {"version": CURRENT_VERSIONS["health_data"], "locale": "en"}
    client.put(PATH, json=body, headers=headers)
    client.put(f"/weights/{server_today()}", json={"weight_kg": 80}, headers=headers)
    before = datetime.now(UTC) - timedelta(minutes=1)
    client.delete(PATH, headers=headers)
    log = erasures.read_log(session)
    # The older dump: the consent still standing, the weigh-in still there
    session.add(
        Consent(
            user_id=user_id,
            purpose="health_data",
            version="v1",
            locale="en",
            text_sha256="x" * 64,
            given_at=before,
        )
    )
    session.add(
        BodyWeight(
            user_id=user_id,
            measured_on=server_today(),
            weight_kg=80,
            created_at=before,
        )
    )
    session.get(User, user_id).target_mode = "adaptive"
    session.commit()

    counts = erasures.reapply(session, log)

    assert (counts.consents, counts.health_rows) == (1, 1)
    assert count(session, BodyWeight) == 0
    status = client.get(PATH, headers=headers).json()
    assert status["valid"] is False
    assert me(client, headers)["target_mode"] == "manual"


def test_applying_the_log_twice_changes_nothing_the_second_time(
    client: TestClient, session: Session
) -> None:
    headers = register_and_login(client, "gone@example.com")
    client.request("DELETE", "/auth/me", json={"password": PASSWORD}, headers=headers)
    log = erasures.read_log(session)

    first = erasures.reapply(session, log)
    second = erasures.reapply(session, log)

    assert first.logged == second.logged == 0  # already in the log
    assert (second.accounts, second.consents, second.health_rows) == (0, 0, 0)
    assert count(session, Erasure) == 1


def test_a_restored_log_gets_the_newer_entries_back(
    client: TestClient, session: Session
) -> None:
    headers = register_and_login(client, "gone@example.com")
    client.request("DELETE", "/auth/me", json={"password": PASSWORD}, headers=headers)
    log = erasures.read_log(session)
    # The dump predates the deletion: its log does not have it
    session.query(Erasure).delete()
    session.commit()

    counts = erasures.reapply(session, log)

    assert counts.logged == 1
    assert count(session, Erasure) == 1


def test_a_malformed_entry_stops_everything(session: Session) -> None:
    with pytest.raises(ValueError, match="fields"):
        erasures.reapply(session, [{"user_id": 1, "kind": "account"}])


def test_the_command_needs_a_verb_and_a_file() -> None:
    assert erasures.main([]) == 2
    assert erasures.main(["vacuum", "x.jsonl"]) == 2


def run_command(*args: str, database: Path) -> subprocess.CompletedProcess[str]:
    """`python -m app.erasures` as the CronJob runs it: the database settings
    only. JWT_SECRET_KEY is set empty, so loading the app's settings would
    fail even where a local .env has a key; the DB_* are emptied too, so a
    local .env cannot add a second database setting."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DB_", "DATABASE_URL", "JWT_"))
    }
    env |= {"DATABASE_URL": f"sqlite:///{database}", "JWT_SECRET_KEY": ""}
    env |= dict.fromkeys(("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_NAME"), "")
    return subprocess.run(
        [sys.executable, "-m", "app.erasures", *args],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_command_runs_with_the_database_settings_alone(tmp_path: Path) -> None:
    database = tmp_path / "haki.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Erasure(
                user_id=7,
                user_created_at=datetime(2026, 11, 1, tzinfo=UTC),
                kind="account",
                erased_at=datetime(2026, 11, 13, tzinfo=UTC),
            )
        )
        session.commit()
    engine.dispose()
    log = tmp_path / "erasures.jsonl"

    exported = run_command("export", str(log), database=database)
    reapplied = run_command("reapply", str(log), database=database)

    assert exported.returncode == 0, exported.stderr
    assert reapplied.returncode == 0, reapplied.stderr
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(e["user_id"], e["kind"]) for e in entries] == [(7, "account")]
