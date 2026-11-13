from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.entries import MAX_ENTRIES_PER_MEAL
from app.models import MealEntry, QuickEntry
from tests.test_entries import DAY, create_entry, create_food

COPY = {"from_day": DAY, "from_meal": "breakfast", "to_day": DAY, "to_meal": "lunch"}
BACK = {"from_day": DAY, "from_meal": "lunch", "to_day": DAY, "to_meal": "breakfast"}


def user_id(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def fill(
    session: Session, uid: int, food_id: int, meal: str, food: int, quick: int = 0
) -> None:
    """Add entries straight to the database: faster than through the API."""
    day = date.fromisoformat(DAY)
    session.add_all(
        [
            MealEntry(
                user_id=uid, food_id=food_id, eaten_on=day, meal_type=meal, grams=1
            )
            for _ in range(food)
        ]
        + [
            QuickEntry(
                user_id=uid,
                eaten_on=day,
                meal_type=meal,
                name="Quick add",
                calories=1,
                protein=0,
                carbs=0,
                fat=0,
            )
            for _ in range(quick)
        ]
    )
    session.commit()


def rows(session: Session) -> int:
    return sum(
        session.scalar(select(func.count()).select_from(model)) or 0
        for model in (MealEntry, QuickEntry)
    )


def post(client: TestClient, headers: dict[str, str], path: str, body: Any) -> int:
    return client.post(path, json=body, headers=headers).status_code


def test_copying_a_meal_back_and_forth_stops_at_the_cap(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    # The loop that doubled a user's rows with every request
    food_id = create_food(client, auth_headers)
    create_entry(client, auth_headers, food_id, meal_type="breakfast")
    statuses = []

    for _ in range(20):
        statuses.append(post(client, auth_headers, "/entries/copy", COPY))
        statuses.append(post(client, auth_headers, "/entries/copy", BACK))

    assert 409 in statuses
    assert rows(session) <= 2 * MAX_ENTRIES_PER_MEAL


def test_a_copy_that_exactly_fills_the_meal_is_accepted(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    food_id = create_food(client, auth_headers)
    uid = user_id(client, auth_headers)
    fill(session, uid, food_id, "breakfast", food=40, quick=10)
    fill(session, uid, food_id, "lunch", food=50)

    assert post(client, auth_headers, "/entries/copy", COPY) == 201
    assert post(client, auth_headers, "/entries/copy", COPY) == 409


def test_a_refused_copy_copies_nothing(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    food_id = create_food(client, auth_headers)
    uid = user_id(client, auth_headers)
    fill(session, uid, food_id, "breakfast", food=2)
    fill(session, uid, food_id, "lunch", food=MAX_ENTRIES_PER_MEAL - 1)
    before = rows(session)

    response = client.post("/entries/copy", json=COPY, headers=auth_headers)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A meal holds at most 100 entries",
        "code": "meal_full",
    }
    assert rows(session) == before


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/entries", {"eaten_on": DAY, "meal_type": "lunch", "grams": 100}),
        ("/entries/quick", {"eaten_on": DAY, "meal_type": "lunch", "calories": 100}),
    ],
)
def test_a_full_meal_refuses_one_more_entry(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    path: str,
    body: dict[str, Any],
) -> None:
    food_id = create_food(client, auth_headers)
    uid = user_id(client, auth_headers)
    # Food and quick entries count together
    fill(session, uid, food_id, "lunch", food=60, quick=MAX_ENTRIES_PER_MEAL - 60)
    if path == "/entries":
        body = {**body, "food_id": food_id}

    assert post(client, auth_headers, path, body) == 409
    # Another meal of the same day, or the same meal another day, has room
    assert post(client, auth_headers, path, {**body, "meal_type": "dinner"}) == 201
    assert post(client, auth_headers, path, {**body, "eaten_on": "2026-11-01"}) == 201


def test_the_cap_is_per_user(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    session: Session,
) -> None:
    food_id = create_food(client, auth_headers)
    fill(session, user_id(client, auth_headers), food_id, "lunch", food=100)
    body = {"eaten_on": DAY, "meal_type": "lunch", "calories": 100}

    assert post(client, other_auth_headers, "/entries/quick", body) == 201
