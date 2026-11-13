"""Idempotency-Key on POST /entries and POST /entries/quick (app/entries.py)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.entries import MAX_ENTRIES_PER_MEAL
from app.models import MealEntry, QuickEntry

DAY = "2026-11-14"
QUICK = {"eaten_on": DAY, "meal_type": "snack", "calories": 200, "name": "Apple"}


@pytest.fixture
def food_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    food = {
        "name": "Oats",
        "calories_per_100g": 389,
        "protein_per_100g": 17,
        "carbs_per_100g": 66,
        "fat_per_100g": 7,
    }
    return client.post("/foods", json=food, headers=auth_headers).json()["id"]


def entry_body(food_id: int, grams: float = 80) -> dict[str, Any]:
    return {
        "food_id": food_id,
        "eaten_on": DAY,
        "meal_type": "breakfast",
        "grams": grams,
    }


def send(
    client: TestClient,
    headers: dict[str, str],
    path: str,
    body: dict[str, Any],
    key: str | None,
) -> Any:
    extra = {} if key is None else {"Idempotency-Key": key}
    return client.post(path, json=body, headers=headers | extra)


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture(params=["food", "quick"])
def kind(
    request: pytest.FixtureRequest, food_id: int
) -> tuple[str, dict[str, Any], type]:
    if request.param == "food":
        return "/entries", entry_body(food_id), MealEntry
    return "/entries/quick", QUICK, QuickEntry


def test_the_same_request_sent_again_returns_the_first_entry(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    kind: tuple[str, dict[str, Any], type],
) -> None:
    path, body, model = kind
    key = str(uuid.uuid4())

    first = send(client, auth_headers, path, body, key)
    again = send(client, auth_headers, path, body, key)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert count(session, model) == 1


def test_the_same_key_with_another_body_is_a_conflict(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    kind: tuple[str, dict[str, Any], type],
) -> None:
    path, body, model = kind
    key = str(uuid.uuid4())
    send(client, auth_headers, path, body, key)
    changed = body | {"meal_type": "dinner"}

    response = send(client, auth_headers, path, changed, key)

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_key_reused"
    assert count(session, model) == 1


def test_without_a_key_nothing_changes(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    kind: tuple[str, dict[str, Any], type],
) -> None:
    path, body, model = kind

    statuses = [send(client, auth_headers, path, body, None).status_code for _ in "ab"]

    assert statuses == [201, 201]
    assert count(session, model) == 2


@pytest.mark.parametrize("key", ["not-a-uuid", "", "1234"])
def test_a_key_that_is_not_a_uuid_is_refused(
    client: TestClient, auth_headers: dict[str, str], session: Session, key: str
) -> None:
    response = send(client, auth_headers, "/entries/quick", QUICK, key)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_idempotency_key"
    assert count(session, QuickEntry) == 0


def test_keys_belong_to_their_user(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    session: Session,
) -> None:
    key = str(uuid.uuid4())

    mine = send(client, auth_headers, "/entries/quick", QUICK, key)
    theirs = send(client, other_auth_headers, "/entries/quick", QUICK, key)

    assert (mine.status_code, theirs.status_code) == (201, 201)
    assert mine.json()["id"] != theirs.json()["id"]
    assert count(session, QuickEntry) == 2


def test_a_deleted_entry_takes_its_key_with_it(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    key = str(uuid.uuid4())
    first = send(client, auth_headers, "/entries/quick", QUICK, key).json()
    client.delete(f"/entries/quick/{first['id']}", headers=auth_headers)

    again = send(client, auth_headers, "/entries/quick", QUICK, key)

    assert again.status_code == 201
    assert count(session, QuickEntry) == 1


def test_a_replay_into_a_full_meal_returns_the_entry(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    key = str(uuid.uuid4())
    send(client, auth_headers, "/entries/quick", QUICK, key)
    for _ in range(MAX_ENTRIES_PER_MEAL - 1):
        send(client, auth_headers, "/entries/quick", QUICK, None)

    again = send(client, auth_headers, "/entries/quick", QUICK, key)
    new = send(client, auth_headers, "/entries/quick", QUICK, str(uuid.uuid4()))

    assert again.status_code == 200
    assert new.status_code == 409 and new.json()["code"] == "meal_full"
    assert count(session, QuickEntry) == MAX_ENTRIES_PER_MEAL
