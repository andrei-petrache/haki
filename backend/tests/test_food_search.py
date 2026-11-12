from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_catalog import FETA, catalog, catalog_food_id  # noqa: F401
from tests.test_foods import create_food
from tests.test_last_logged import log

Headers = dict[str, str]


def search(client: TestClient, headers: Headers, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/foods/search", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def rows(results: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(result["origin"], result["name"]) for result in results]


def copy(client: TestClient, headers: Headers, item_id: int, language: str) -> Any:
    body = {"catalog_food_id": item_id, "language": language}
    response = client.post("/foods/from-catalog", json=body, headers=headers)
    assert response.status_code == 201
    return response.json()


@pytest.mark.usefixtures("catalog")
def test_own_foods_come_first_then_the_catalog(
    client: TestClient, auth_headers: Headers
) -> None:
    create_food(client, auth_headers, name="Brânză de vaci a bunicii")

    results = search(client, auth_headers, q="branza", language="ro")

    assert results[0] == {
        "origin": "own",
        "id": results[0]["id"],
        "name": "Brânză de vaci a bunicii",
        "calories_per_100g": 389.0,
        "protein_per_100g": 16.9,
        "carbs_per_100g": 66.3,
        "fat_per_100g": 6.9,
        "favourite": False,
        "last_logged": None,
        "catalog_food_id": None,
        "catalog_name": None,
        "catalog_name_ro": None,
    }
    catalog_rows = results[1:]
    assert catalog_rows and all(r["origin"] == "catalog" for r in catalog_rows)
    assert ("catalog", "Brânză feta") in rows(catalog_rows)
    feta = next(r for r in catalog_rows if r["name"] == "Brânză feta")
    assert feta["source_key"] == "usda-fdc-sr-legacy"


@pytest.mark.usefixtures("catalog")
def test_search_ignores_case_and_diacritics_for_both_kinds(
    client: TestClient, auth_headers: Headers
) -> None:
    create_food(client, auth_headers, name="Ciorbă de perișoare")

    own = search(client, auth_headers, q="CIORBA PERISOARE")
    catalog_hit = search(client, auth_headers, q="BRANZA feta", language="ro")

    assert rows(own)[:1] == [("own", "Ciorbă de perișoare")]
    assert ("catalog", "Brânză feta") in rows(catalog_hit)


@pytest.mark.usefixtures("catalog")
def test_catalog_names_follow_the_language(
    client: TestClient, auth_headers: Headers
) -> None:
    english = search(client, auth_headers, q="feta", language="en")
    romanian = search(client, auth_headers, q="feta", language="ro")

    assert ("catalog", "Feta cheese") in rows(english)
    assert ("catalog", "Brânză feta") in rows(romanian)


@pytest.mark.usefixtures("catalog")
def test_a_copied_catalog_food_is_listed_once_as_own(
    client: TestClient, auth_headers: Headers, session: Session
) -> None:
    feta_id = catalog_food_id(session, FETA)
    mine = copy(client, auth_headers, feta_id, "ro")

    results = search(client, auth_headers, q="feta", language="ro")

    assert results[0]["origin"] == "own"
    assert results[0]["catalog_food_id"] == feta_id
    assert feta_id not in [r["id"] for r in results if r["origin"] == "catalog"]
    assert [r["id"] for r in results if r["origin"] == "own"] == [mine["id"]]


@pytest.mark.usefixtures("catalog")
def test_a_copy_is_found_by_the_catalogs_other_name(
    client: TestClient, auth_headers: Headers, session: Session
) -> None:
    # Kept under its Romanian name, found by the English one too
    copy(client, auth_headers, catalog_food_id(session, FETA), "ro")

    results = search(client, auth_headers, q="feta cheese")

    assert rows(results)[0] == ("own", "Brânză feta")


def test_own_foods_are_ordered_by_last_use_then_name(
    client: TestClient, auth_headers: Headers
) -> None:
    ids = {
        name: create_food(client, auth_headers, name=name)["id"]
        for name in ("Rice white", "Rice brown", "Rice wild", "Rice cakes")
    }
    log(client, auth_headers, ids["Rice wild"], 50)
    log(client, auth_headers, ids["Rice brown"], 80)

    results = search(client, auth_headers, q="rice")

    assert rows(results) == [
        ("own", "Rice brown"),
        ("own", "Rice wild"),
        ("own", "Rice cakes"),
        ("own", "Rice white"),
    ]
    assert results[0]["last_logged"]["grams"] == 80.0


@pytest.mark.usefixtures("catalog")
def test_the_limit_caps_each_origin_on_its_own(
    client: TestClient, auth_headers: Headers
) -> None:
    for i in range(5):
        create_food(client, auth_headers, name=f"Cheese of mine {i}")

    results = search(client, auth_headers, q="cheese", limit=3)

    origins = [r["origin"] for r in results]
    assert origins.count("own") == 3
    assert origins.count("catalog") == 3


def test_every_word_must_match(client: TestClient, auth_headers: Headers) -> None:
    create_food(client, auth_headers, name="Chicken soup")
    create_food(client, auth_headers, name="Chicken breast")

    assert rows(search(client, auth_headers, q="chicken soup")) == [
        ("own", "Chicken soup")
    ]


def test_search_shows_only_the_users_own_foods(
    client: TestClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    create_food(client, other_auth_headers, name="Secret sauce")

    assert search(client, auth_headers, q="secret") == []


def test_a_query_of_punctuation_matches_nothing(
    client: TestClient, auth_headers: Headers
) -> None:
    create_food(client, auth_headers, name="Oats")

    assert search(client, auth_headers, q="%_ -") == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "x" * 101},
        {"q": "a", "limit": 0},
        {"q": "a", "limit": 51},
        {"q": "a", "language": "de"},
    ],
)
def test_search_rejects_invalid_parameters(
    client: TestClient, auth_headers: Headers, params: dict[str, Any]
) -> None:
    response = client.get("/foods/search", params=params, headers=auth_headers)

    assert response.status_code == 422


def test_search_requires_login(client: TestClient) -> None:
    assert client.get("/foods/search", params={"q": "oats"}).status_code == 401
