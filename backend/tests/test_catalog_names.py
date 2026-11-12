from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogExercise
from tests.test_catalog import FETA, catalog, catalog_food_id  # noqa: F401
from tests.test_foods import create_food
from tests.test_last_logged import log
from tests.test_workouts import count_queries

Headers = dict[str, str]
FETA_NAMES = {"catalog_name": "Feta cheese", "catalog_name_ro": "Brânză feta"}


def copy_food(
    client: TestClient, headers: Headers, item_id: int, language: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"catalog_food_id": item_id}
    if language is not None:
        body["language"] = language
    response = client.post("/foods/from-catalog", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def set_language(client: TestClient, headers: Headers, language: str | None) -> None:
    response = client.put("/auth/me", json={"language": language}, headers=headers)
    assert response.status_code == 200


def names(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item[key] for key in ("catalog_name", "catalog_name_ro")}


pytestmark = pytest.mark.usefixtures("catalog")


def test_a_copy_carries_both_catalog_names_everywhere(
    client: TestClient, auth_headers: Headers, session: Session
) -> None:
    food = copy_food(client, auth_headers, catalog_food_id(session, FETA), "en")
    log(client, auth_headers, food["id"], 40)

    foods = client.get("/foods", headers=auth_headers).json()
    recent = client.get("/foods/recent", headers=auth_headers).json()
    found = client.get(
        "/foods/search", params={"q": "feta"}, headers=auth_headers
    ).json()
    entries = client.get(
        "/entries", params={"date": "2026-11-12"}, headers=auth_headers
    ).json()

    # Stored in English, as copied; the client can show the Romanian name
    assert food["name"] == "Feta cheese"
    assert names(food) == FETA_NAMES
    assert names(foods[0]) == FETA_NAMES
    assert names(recent[0]) == FETA_NAMES
    assert found[0]["origin"] == "own" and names(found[0]) == FETA_NAMES
    assert entries[0]["food_name"] == "Feta cheese"
    assert names(entries[0]) == FETA_NAMES


def test_a_food_typed_by_hand_and_a_quick_entry_have_no_catalog_names(
    client: TestClient, auth_headers: Headers
) -> None:
    food = create_food(client, auth_headers)
    log(client, auth_headers, food["id"], 40)
    quick = {"eaten_on": "2026-11-12", "meal_type": "snack", "calories": 100}
    client.post("/entries/quick", json=quick, headers=auth_headers)

    entries = client.get(
        "/entries", params={"date": "2026-11-12"}, headers=auth_headers
    ).json()

    assert names(food) == {"catalog_name": None, "catalog_name_ro": None}
    assert [names(e) for e in entries] == [
        {"catalog_name": None, "catalog_name_ro": None}
    ] * 2


def test_a_renamed_copy_keeps_its_name_and_still_shows_the_catalogs(
    client: TestClient, auth_headers: Headers, session: Session
) -> None:
    # The client sees `name` differ from both and shows the user's own
    food = copy_food(client, auth_headers, catalog_food_id(session, FETA), "en")
    changes = {**{k: food[k] for k in food if k.endswith("_per_100g")}}
    client.put(
        f"/foods/{food['id']}",
        json={"name": "Feta de la piață", **changes},
        headers=auth_headers,
    )

    listed = client.get("/foods", headers=auth_headers).json()[0]

    assert listed["name"] == "Feta de la piață"
    assert names(listed) == FETA_NAMES


def test_reading_never_rewrites_the_stored_name(
    client: TestClient, auth_headers: Headers, session: Session
) -> None:
    food = copy_food(client, auth_headers, catalog_food_id(session, FETA), "en")
    set_language(client, auth_headers, "ro")

    for _ in range(2):
        client.get("/foods", headers=auth_headers)
        client.get("/foods/search", params={"q": "feta"}, headers=auth_headers)

    assert client.get("/foods", headers=auth_headers).json()[0]["name"] == food["name"]


@pytest.mark.parametrize(
    ("account", "asked", "expected"),
    [
        ("ro", None, "Brânză feta"),
        ("en", None, "Feta cheese"),
        (None, None, "Feta cheese"),
        ("ro", "en", "Feta cheese"),
        ("en", "ro", "Brânză feta"),
    ],
)
def test_a_copy_without_a_language_takes_the_accounts(
    client: TestClient,
    auth_headers: Headers,
    session: Session,
    account: str | None,
    asked: str | None,
    expected: str,
) -> None:
    set_language(client, auth_headers, account)

    food = copy_food(client, auth_headers, catalog_food_id(session, FETA), asked)

    assert food["name"] == expected


def test_an_exercise_copy_without_a_language_takes_the_accounts(
    client: TestClient, auth_headers: Headers, session: Session
) -> None:
    item = session.scalars(
        select(CatalogExercise).where(CatalogExercise.name_ro.is_not(None)).limit(1)
    ).one()
    set_language(client, auth_headers, "ro")

    response = client.post(
        "/exercises/from-catalog",
        json={"catalog_exercise_id": item.id},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["name"] == item.name_ro


def test_listing_entries_takes_the_same_queries_however_many_copies(
    client: TestClient, auth_headers: Headers, session: Session
) -> None:
    def queries_for_entries() -> int:
        with count_queries() as statements:
            client.get("/entries", params={"date": "2026-11-12"}, headers=auth_headers)
        return len(statements)

    feta = copy_food(client, auth_headers, catalog_food_id(session, FETA), "en")
    log(client, auth_headers, feta["id"], 40)
    one = queries_for_entries()
    for i in range(4):
        food = create_food(client, auth_headers, name=f"Food {i}")
        log(client, auth_headers, food["id"], 10 + i)

    assert queries_for_entries() == one
