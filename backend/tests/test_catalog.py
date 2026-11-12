from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_import import import_catalog
from app.models import CatalogExercise, CatalogFood

Headers = dict[str, str]


@pytest.fixture
def catalog(session: Session) -> None:
    """The shipped catalog, imported into the test's database."""
    import_catalog(session)


def catalog_food_id(session: Session, ref: str) -> int:
    query = select(CatalogFood.id).where(CatalogFood.source_ref == ref)
    return session.scalars(query).one()


def catalog_exercise_id(session: Session, ref: str) -> int:
    query = select(CatalogExercise.id).where(CatalogExercise.source_ref == ref)
    return session.scalars(query).one()


def search(
    client: TestClient, headers: Headers, kind: str, **params: Any
) -> list[dict[str, Any]]:
    response = client.get(f"/catalog/{kind}", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def names(items: list[dict[str, Any]], field: str = "name") -> list[str]:
    return [item[field] for item in items]


CHICKEN = "171077"  # Chicken breast, skinless, raw
FETA = "173420"  # Feta cheese / Brânză feta
SQUAT = "Barbell_Squat"


# Authentication


@pytest.mark.parametrize(
    "path",
    [
        "/catalog/sources",
        "/catalog/foods",
        "/catalog/foods/1",
        "/catalog/exercises",
        "/catalog/exercises/1",
    ],
)
def test_catalog_requires_authentication(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/foods/from-catalog", "/exercises/from-catalog"])
def test_copying_requires_authentication(client: TestClient, path: str) -> None:
    response = client.post(path, json={"catalog_food_id": 1, "catalog_exercise_id": 1})

    assert response.status_code == 401


# Sources


def test_sources_carry_licence_and_credit(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    response = client.get("/catalog/sources", headers=auth_headers)

    assert response.status_code == 200
    sources = {source["key"]: source for source in response.json()}
    assert sources["usda-fdc-sr-legacy"]["license"] == "CC0-1.0"
    assert sources["free-exercise-db"]["license"] == "Unlicense"
    assert "FoodData Central" in sources["usda-fdc-sr-legacy"]["attribution"]
    assert sources["free-exercise-db"]["version"]


# Searching foods


def test_search_finds_romanian_names_without_diacritics(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    found = search(client, auth_headers, "foods", q="branza feta")

    assert names(found, "name_ro") == ["Brânză feta"]
    assert found[0]["name"] == "Feta cheese"
    assert found[0]["source"]["key"] == "usda-fdc-sr-legacy"


def test_search_matches_every_word_in_any_order(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    found = search(client, auth_headers, "foods", q="PUI piept crud")

    assert names(found, "name_ro") == ["Piept de pui fără piele, crud"]


def test_search_with_diacritics_finds_the_same(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    plain = search(client, auth_headers, "foods", q="varza")
    with_marks = search(client, auth_headers, "foods", q="Varză")

    assert with_marks == plain
    assert "Varză murată" in names(plain, "name_ro")


def test_matches_at_the_start_of_a_word_come_first(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    # "rice" starts a word in the rices, and could sit inside another word
    found = search(client, auth_headers, "foods", q="rice")

    assert names(found)[:4] == [
        "Rice, brown, long-grain, cooked",
        "Rice, brown, long-grain, raw",
        "Rice, white, long-grain, cooked",
        "Rice, white, long-grain, raw",
    ]


def test_search_without_a_match_is_empty(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    assert search(client, auth_headers, "foods", q="sarmale") == []


def test_like_wildcards_in_the_query_match_nothing_special(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    # % and _ are not letters: they separate words, never act as wildcards
    everything = search(client, auth_headers, "foods", limit=100)

    assert search(client, auth_headers, "foods", q="%_%", limit=100) == everything
    assert search(client, auth_headers, "foods", q="_", limit=100) == everything


def test_romanian_order_sorts_by_romanian_name(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    found = search(client, auth_headers, "foods", language="ro", limit=5)

    ro_names = names(found, "name_ro")
    assert ro_names == sorted(ro_names, key=str.lower)
    assert ro_names[0] == "Afine"


def test_pages_cover_the_catalog_without_overlap(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    total = len(session.scalars(select(CatalogFood.id)).all())

    seen: list[int] = []
    offset = 0
    while page := search(client, auth_headers, "foods", limit=40, offset=offset):
        seen += [item["id"] for item in page]
        offset += 40

    assert len(seen) == total
    assert len(set(seen)) == total


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 2_147_483_648},
        {"q": "x" * 101},
        {"language": "de"},
    ],
)
def test_search_rejects_invalid_parameters(
    client: TestClient, auth_headers: Headers, params: dict[str, Any]
) -> None:
    response = client.get("/catalog/foods", params=params, headers=auth_headers)

    assert response.status_code == 422


def test_a_users_own_food_never_appears_in_the_catalog(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    own = {
        "name": "Zacusca de casa",
        "calories_per_100g": 90,
        "protein_per_100g": 1.5,
        "carbs_per_100g": 8,
        "fat_per_100g": 6,
    }
    client.post("/foods", json=own, headers=auth_headers)

    assert search(client, auth_headers, "foods", q="zacusca") == []


# One catalog item


def test_read_catalog_food(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    food_id = catalog_food_id(session, CHICKEN)

    response = client.get(f"/catalog/foods/{food_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Chicken breast, skinless, raw"
    assert body["protein_per_100g"] == 22.5
    assert body["source"]["license"] == "CC0-1.0"


@pytest.mark.parametrize("kind", ["foods", "exercises"])
def test_unknown_catalog_item_is_404(
    client: TestClient, auth_headers: Headers, catalog: None, kind: str
) -> None:
    response = client.get(f"/catalog/{kind}/999999", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.parametrize("item_id", [0, 2_147_483_648])
def test_out_of_range_catalog_id_is_422(
    client: TestClient, auth_headers: Headers, item_id: int
) -> None:
    response = client.get(f"/catalog/foods/{item_id}", headers=auth_headers)

    assert response.status_code == 422


# Exercises


def test_search_exercises_in_romanian(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    found = search(client, auth_headers, "exercises", q="genuflexiuni bara")

    assert "Barbell Squat" in names(found)
    squat = next(item for item in found if item["name"] == "Barbell Squat")
    assert squat["name_ro"] == "Genuflexiuni cu bara"
    assert squat["primary_muscles"] == ["quadriceps"]
    assert squat["equipment"] == "barbell"
    assert squat["source"]["key"] == "free-exercise-db"


def test_filter_exercises_by_primary_muscle(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    found = search(client, auth_headers, "exercises", muscle="chest", limit=100)

    assert "Barbell Bench Press - Medium Grip" in names(found)
    assert all("chest" in item["primary_muscles"] for item in found)


def test_muscle_filter_combines_with_the_search(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    found = search(
        client, auth_headers, "exercises", q="impins", muscle="shoulders", limit=100
    )

    assert "Împins Arnold cu gantere" in names(found, "name_ro")
    assert all("shoulders" in item["primary_muscles"] for item in found)
    assert all(item["name_ro"].startswith("Împins") for item in found)


def test_a_secondary_muscle_is_not_a_match(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    # The bench press works the triceps second: a triceps filter skips it
    found = search(client, auth_headers, "exercises", muscle="triceps", limit=100)

    assert "Barbell Bench Press - Medium Grip" not in names(found)


def test_a_muscle_with_two_words(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    found = search(client, auth_headers, "exercises", muscle="lower back", limit=100)

    assert "Barbell Deadlift" in names(found)


def test_an_unknown_muscle_finds_nothing(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    assert search(client, auth_headers, "exercises", muscle="wings") == []


@pytest.mark.parametrize("muscle", ["Chest", "chest%", '"chest"', "", "x" * 31])
def test_muscle_must_be_lower_case_words(
    client: TestClient, auth_headers: Headers, muscle: str
) -> None:
    response = client.get(
        "/catalog/exercises", params={"muscle": muscle}, headers=auth_headers
    )

    assert response.status_code == 422


def test_exercise_images_are_not_returned(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    # Kept as references only, until their origin and hosting are decided
    exercise_id = catalog_exercise_id(session, SQUAT)

    response = client.get(f"/catalog/exercises/{exercise_id}", headers=auth_headers)

    assert response.status_code == 200
    assert "image_refs" not in response.json()
    assert "images" not in response.text


# Copying a food


def copy_food(
    client: TestClient, headers: Headers, item_id: int, language: str = "en"
) -> Any:
    return client.post(
        "/foods/from-catalog",
        json={"catalog_food_id": item_id, "language": language},
        headers=headers,
    )


def test_copy_a_catalog_food(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    item_id = catalog_food_id(session, CHICKEN)

    response = copy_food(client, auth_headers, item_id)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "Chicken breast, skinless, raw",
        "calories_per_100g": 120,
        "protein_per_100g": 22.5,
        "carbs_per_100g": 0,
        "fat_per_100g": 2.62,
        "catalog_food_id": item_id,
        "favourite": False,
        "last_logged": None,
    }
    own = client.get("/foods", headers=auth_headers).json()
    assert own == [body]


def test_copy_in_romanian_takes_the_romanian_name(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    response = copy_food(client, auth_headers, catalog_food_id(session, FETA), "ro")

    assert response.status_code == 201
    assert response.json()["name"] == "Brânză feta"


def test_copying_twice_returns_the_same_copy(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    item_id = catalog_food_id(session, CHICKEN)
    first = copy_food(client, auth_headers, item_id)

    second = copy_food(client, auth_headers, item_id, "ro")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(client.get("/foods", headers=auth_headers).json()) == 1


def test_each_user_gets_their_own_copy(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    catalog: None,
    session: Session,
) -> None:
    # The "already copied" lookup is per user: the other user's request must
    # never be answered with this user's copy
    item_id = catalog_food_id(session, CHICKEN)
    mine = copy_food(client, auth_headers, item_id).json()

    response = copy_food(client, other_auth_headers, item_id)

    assert response.status_code == 201
    theirs = response.json()
    assert theirs["id"] != mine["id"]
    assert client.get("/foods", headers=other_auth_headers).json() == [theirs]
    assert client.get("/foods", headers=auth_headers).json() == [mine]


def test_another_users_copy_is_404_and_stays_unchanged(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    catalog: None,
    session: Session,
) -> None:
    mine = copy_food(client, auth_headers, catalog_food_id(session, CHICKEN)).json()
    changes = {k: mine[k] for k in mine if k not in ("id", "catalog_food_id")}

    updated = client.put(
        f"/foods/{mine['id']}",
        json={**changes, "name": "Hacked"},
        headers=other_auth_headers,
    )
    deleted = client.delete(f"/foods/{mine['id']}", headers=other_auth_headers)

    assert updated.status_code == 404
    assert deleted.status_code == 404
    assert client.get("/foods", headers=auth_headers).json() == [mine]


def test_copy_of_an_unknown_catalog_food_is_404(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    response = copy_food(client, auth_headers, 999999)

    assert response.status_code == 404
    assert client.get("/foods", headers=auth_headers).json() == []


def test_copy_whose_name_is_taken_is_409(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    typed = {
        "name": "Brânză feta",
        "calories_per_100g": 260,
        "protein_per_100g": 15,
        "carbs_per_100g": 4,
        "fat_per_100g": 21,
    }
    client.post("/foods", json=typed, headers=auth_headers)

    response = copy_food(client, auth_headers, catalog_food_id(session, FETA), "ro")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A food with this name already exists",
        "code": "food_name_taken",
    }
    assert len(client.get("/foods", headers=auth_headers).json()) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"catalog_food_id": 0},
        {"catalog_food_id": "abc"},
        {"catalog_food_id": 1, "language": "de"},
    ],
)
def test_copy_rejects_invalid_body(
    client: TestClient, auth_headers: Headers, body: dict[str, Any]
) -> None:
    response = client.post("/foods/from-catalog", json=body, headers=auth_headers)

    assert response.status_code == 422


def test_a_copy_can_be_logged_and_copied_again_once_deleted(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    item_id = catalog_food_id(session, CHICKEN)
    copy = copy_food(client, auth_headers, item_id).json()

    entry = client.post(
        "/entries",
        json={
            "food_id": copy["id"],
            "eaten_on": "2026-11-11",
            "meal_type": "lunch",
            "grams": 200,
        },
        headers=auth_headers,
    )
    assert entry.status_code == 201
    assert entry.json()["calories"] == 240
    client.delete(f"/entries/{entry.json()['id']}", headers=auth_headers)
    assert client.delete(f"/foods/{copy['id']}", headers=auth_headers).status_code == (
        204
    )

    again = copy_food(client, auth_headers, item_id)

    assert again.status_code == 201  # a new copy, not the deleted one
    assert again.json()["catalog_food_id"] == item_id
    assert client.get("/foods", headers=auth_headers).json() == [again.json()]


# Copying an exercise


def copy_exercise(
    client: TestClient, headers: Headers, item_id: int, language: str = "en"
) -> Any:
    return client.post(
        "/exercises/from-catalog",
        json={"catalog_exercise_id": item_id, "language": language},
        headers=headers,
    )


def test_copy_a_catalog_exercise(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    item_id = catalog_exercise_id(session, SQUAT)

    response = copy_exercise(client, auth_headers, item_id, "ro")

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "Genuflexiuni cu bara",
        "catalog_exercise_id": item_id,
    }
    again = copy_exercise(client, auth_headers, item_id)
    assert again.status_code == 200
    assert again.json() == body


def test_exercise_copy_name_conflict_ignores_case(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    client.post("/exercises", json={"name": "barbell squat"}, headers=auth_headers)

    response = copy_exercise(client, auth_headers, catalog_exercise_id(session, SQUAT))

    assert response.status_code == 409


def test_exercise_copies_are_per_user(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    catalog: None,
    session: Session,
) -> None:
    item_id = catalog_exercise_id(session, SQUAT)
    mine = copy_exercise(client, auth_headers, item_id).json()

    theirs = copy_exercise(client, other_auth_headers, item_id)
    renamed = client.put(
        f"/exercises/{mine['id']}", json={"name": "Mine"}, headers=other_auth_headers
    )

    assert theirs.status_code == 201
    assert theirs.json()["id"] != mine["id"]
    assert renamed.status_code == 404
    assert client.get("/exercises", headers=auth_headers).json() == [mine]


def test_copy_of_an_unknown_catalog_exercise_is_404(
    client: TestClient, auth_headers: Headers, catalog: None
) -> None:
    response = copy_exercise(client, auth_headers, 999999)

    assert response.status_code == 404


def test_a_copied_exercise_can_be_used_in_a_workout(
    client: TestClient, auth_headers: Headers, catalog: None, session: Session
) -> None:
    copy = copy_exercise(client, auth_headers, catalog_exercise_id(session, SQUAT))

    response = client.post(
        "/workouts",
        json={
            "performed_on": "2026-11-11",
            "exercises": [
                {
                    "exercise_id": copy.json()["id"],
                    "sets": [{"reps": 5, "weight_kg": 100}],
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["exercises"][0]["exercise_name"] == "Barbell Squat"
