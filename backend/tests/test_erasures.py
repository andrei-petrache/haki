"""The erasure log a restore applies again (app/erasures.py).

A restore is simulated by putting rows back as an older dump would hold
them, after the erasure happened through the API."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import erasures
from app.body import server_today
from app.config import settings
from app.consent import CURRENT_VERSIONS
from app.models import BodyWeight, Consent, Erasure, Food, User
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
