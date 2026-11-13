"""Consent to health data (app/consent.py)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.body import server_today
from app.config import settings
from app.consent import CURRENT_VERSIONS, text_sha256
from app.models import BodyWeight, Consent, Erasure, TdeeEstimate
from tests.test_delete_account import PASSWORD

TODAY = server_today()
PATH = "/auth/me/consents/health_data"
# A text accepted must never change: a new wording that changes what is
# agreed to is a new version. Edit these only together with a new version.
PINNED = {
    ("v1", "en"): "f4e91f61eddbdfcc14962f457171c7ed0a14d129c8da71747a0978eaf5c9775f",
    ("v1", "ro"): "746dac0acd7e77deafba980131f2ed8db82acbe6ade553b1c0448792c21c6208",
}


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "body_weight_enabled", True)


def give(client: TestClient, headers: dict[str, str], **overrides: Any) -> Any:
    body = {"version": CURRENT_VERSIONS["health_data"], "locale": "en"} | overrides
    return client.put(PATH, json=body, headers=headers)


def weigh(client: TestClient, headers: dict[str, str], kg: float = 80) -> Any:
    return client.put(f"/weights/{TODAY}", json={"weight_kg": kg}, headers=headers)


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


# The texts


@pytest.mark.parametrize(("version", "locale"), list(PINNED))
def test_an_accepted_text_never_changes(version: str, locale: str) -> None:
    assert text_sha256("health_data", version, locale) == PINNED[(version, locale)]


def test_every_current_text_exists_in_every_language() -> None:
    for purpose, version in CURRENT_VERSIONS.items():
        for locale in ("en", "ro"):
            assert (version, locale) in PINNED, (purpose, version, locale)


def test_the_text_is_served_with_its_version_and_hash(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(f"{PATH}/text", params={"locale": "ro"}, headers=auth_headers)

    body = response.json()
    assert response.status_code == 200
    assert (body["version"], body["locale"]) == ("v1", "ro")
    assert body["sha256"] == PINNED[("v1", "ro")]
    assert "16 ani" in body["text"]


# Giving it


def test_off_the_consent_endpoints_do_not_exist(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "body_weight_enabled", False)

    assert client.get(PATH, headers=auth_headers).status_code == 404
    assert give(client, auth_headers).status_code == 404
    assert client.delete(PATH, headers=auth_headers).status_code == 404


def test_before_giving_it_nothing_is_valid(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = client.get(PATH, headers=auth_headers).json()

    assert body == {
        "purpose": "health_data",
        "required_version": "v1",
        "valid": False,
        "given_version": None,
        "given_at": None,
        "withdrawn_at": None,
    }


def test_giving_it_records_the_text_shown(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    response = give(client, auth_headers, locale="ro")
    again = give(client, auth_headers, locale="ro")

    assert response.status_code == again.status_code == 200
    assert response.json()["valid"] is True
    rows = session.scalars(select(Consent)).all()
    assert len(rows) == 1  # giving it again while valid adds nothing
    assert (rows[0].locale, rows[0].text_sha256) == ("ro", PINNED[("v1", "ro")])


def test_an_old_text_cannot_be_accepted(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = give(client, auth_headers, version="v0")

    assert response.status_code == 409
    assert response.json()["code"] == "consent_version_outdated"
    assert client.get(PATH, headers=auth_headers).json()["valid"] is False


# The gate


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("PUT", f"/weights/{TODAY}", {"weight_kg": 80}),
        ("GET", "/weights", None),
        ("GET", f"/targets/current?date={TODAY}", None),
        ("PUT", "/auth/me/goal", {"target_mode": "adaptive", "goal_kg_per_week": -0.5}),
    ],
)
def test_without_consent_health_data_is_refused(
    client: TestClient,
    auth_headers: dict[str, str],
    method: str,
    path: str,
    body: Any,
) -> None:
    response = client.request(method, path, json=body, headers=auth_headers)

    # 403, never 401: the session is fine and the client must not sign out
    assert response.status_code == 403
    assert response.json()["code"] == "consent_required"


def test_without_consent_the_users_own_target_and_erasing_still_work(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    manual = {"target_mode": "manual", "goal_kg_per_week": None}

    assert (
        client.put("/auth/me/goal", json=manual, headers=auth_headers).status_code
        == 200
    )
    deleted = client.delete(f"/weights/{TODAY}", headers=auth_headers)
    assert deleted.json()["code"] == "weight_not_found"


def test_the_app_works_without_the_consent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # Freely given (Art. 7(4)): refusing it costs nothing outside its purpose
    for path in ("/auth/me", "/foods", "/exercises", "/workouts", "/programs"):
        assert client.get(path, headers=auth_headers).status_code == 200, path
    summary = client.get("/summary", params={"date": str(TODAY)}, headers=auth_headers)
    assert summary.status_code == 200
    exported = client.post(
        "/auth/me/export", json={"password": PASSWORD}, headers=auth_headers
    )
    assert exported.status_code == 200


def test_an_outdated_consent_keeps_the_data_but_stops_its_use(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    give(client, auth_headers)
    assert weigh(client, auth_headers).status_code == 201

    monkeypatch.setitem(CURRENT_VERSIONS, "health_data", "v2")

    assert weigh(client, auth_headers).status_code == 403
    assert client.get(PATH, headers=auth_headers).json()["valid"] is False
    assert count(session, BodyWeight) == 1
    exported = client.post(
        "/auth/me/export", json={"password": PASSWORD}, headers=auth_headers
    ).json()
    assert len(exported["body_weights"]) == 1


def test_the_summary_uses_the_own_target_without_consent(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    client.put(
        "/auth/me/target", json={"daily_calorie_target": 2000}, headers=auth_headers
    )
    give(client, auth_headers)
    client.put(
        "/auth/me/goal",
        json={"target_mode": "adaptive", "goal_kg_per_week": None},
        headers=auth_headers,
    )
    # The consent ends while the mode is still adaptive (e.g. a new version)
    consent = session.scalars(select(Consent)).one()
    consent.version = "v0"
    session.commit()

    summary = client.get("/summary", params={"date": str(TODAY)}, headers=auth_headers)

    assert summary.json()["daily_calorie_target"] == 2000


# Withdrawing it


def test_withdrawing_deletes_the_health_data_at_once(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    give(client, auth_headers)
    weigh(client, auth_headers)
    client.put(
        "/auth/me/goal",
        json={"target_mode": "adaptive", "goal_kg_per_week": -0.5},
        headers=auth_headers,
    )
    client.get("/targets/current", params={"date": str(TODAY)}, headers=auth_headers)
    assert count(session, TdeeEstimate) == 1

    # No password: as easy as giving it
    response = client.delete(PATH, headers=auth_headers)

    assert response.status_code == 204
    assert count(session, BodyWeight) == count(session, TdeeEstimate) == 0
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["target_mode"] == "manual"
    status = client.get(PATH, headers=auth_headers).json()
    assert status["valid"] is False and status["withdrawn_at"] is not None
    erasure = session.scalars(select(Erasure)).one()
    assert (erasure.user_id, erasure.kind, erasure.purpose) == (
        me["id"],
        "consent",
        "health_data",
    )
    assert weigh(client, auth_headers).status_code == 403


def test_withdrawing_without_a_consent_is_harmless(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    response = client.delete(PATH, headers=auth_headers)

    assert response.status_code == 204
    assert count(session, Erasure) == 0


def test_it_can_be_given_again_after_withdrawing(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    give(client, auth_headers)
    client.delete(PATH, headers=auth_headers)

    response = give(client, auth_headers)

    assert response.json()["valid"] is True
    assert count(session, Consent) == 2  # the history stays
    assert weigh(client, auth_headers).status_code == 201


def test_another_users_consent_is_their_own(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    give(client, other_auth_headers)

    assert weigh(client, auth_headers).status_code == 403
    assert weigh(client, other_auth_headers).status_code == 201


def test_account_deletion_is_logged_for_restores(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    me = client.get("/auth/me", headers=auth_headers).json()

    client.request(
        "DELETE", "/auth/me", json={"password": PASSWORD}, headers=auth_headers
    )

    erasure = session.scalars(select(Erasure)).one()
    assert (erasure.user_id, erasure.kind, erasure.purpose) == (
        me["id"],
        "account",
        None,
    )
    created = datetime.fromisoformat(me["created_at"])
    stored = erasure.user_created_at
    if stored.tzinfo is None:  # SQLite drops the zone; it is UTC
        stored = stored.replace(tzinfo=UTC)
    assert stored == created.astimezone(UTC) or stored == created.replace(tzinfo=UTC)
