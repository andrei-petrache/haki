"""The catalog's constraints and links, against the migrated schema.

Same pattern as test_constraints.py: each violation runs in a savepoint.
"""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CatalogExercise, CatalogFood, CatalogSource, Exercise, Food, User

pytestmark = pytest.mark.integration

MakeUser = Callable[[str], User]


def add_source(db: Session, key: str = "usda-fdc-sr-legacy") -> CatalogSource:
    source = CatalogSource(
        key=key,
        name="USDA FoodData Central, SR Legacy",
        url="https://fdc.nal.usda.gov/",
        license="CC0-1.0",
        attribution="U.S. Department of Agriculture, FoodData Central",
        attribution_required=False,
        share_alike=False,
        version="2018-04",
    )
    db.add(source)
    db.flush()
    return source


def add_catalog_food(
    db: Session, source: CatalogSource, ref: str = "171077", **overrides: Any
) -> CatalogFood:
    food = CatalogFood(
        source_id=source.id,
        source_ref=ref,
        **{
            "name": "Chicken breast, skinless, raw",
            "name_ro": "Piept de pui fără piele, crud",
            "search_text": " chicken breast skinless raw piept de pui fara piele crud ",
            "calories_per_100g": 120,
            "protein_per_100g": 22.5,
            "carbs_per_100g": 0,
            "fat_per_100g": 2.62,
            **overrides,
        },
    )
    db.add(food)
    db.flush()
    return food


def add_catalog_exercise(
    db: Session, source: CatalogSource, ref: str = "Barbell_Squat"
) -> CatalogExercise:
    exercise = CatalogExercise(
        source_id=source.id,
        source_ref=ref,
        name="Barbell Squat",
        name_ro="Genuflexiuni cu bara",
        search_text=" barbell squat genuflexiuni cu bara ",
        category="strength",
        equipment="barbell",
        primary_muscles=["quadriceps"],
        secondary_muscles=["glutes", "hamstrings"],
        image_refs=["Barbell_Squat/0.jpg"],
    )
    db.add(exercise)
    db.flush()
    return exercise


def add_copy(db: Session, user: User, catalog_food: CatalogFood | None) -> Food:
    """A user's food, copied from `catalog_food` or typed in (None)."""
    food = Food(
        user_id=user.id,
        name=f"Food {count(db, Food) + 1}",
        calories_per_100g=120,
        protein_per_100g=22.5,
        carbs_per_100g=0,
        fat_per_100g=2.62,
        catalog_food_id=catalog_food.id if catalog_food else None,
    )
    db.add(food)
    db.flush()
    return food


def count(db: Session, model: type, **filters: Any) -> int:
    query = select(func.count()).select_from(model).filter_by(**filters)
    return db.scalar(query) or 0


def test_source_keys_are_unique(db: Session) -> None:
    add_source(db)

    with (
        pytest.raises(IntegrityError, match="catalog_sources_key_key"),
        db.begin_nested(),
    ):
        add_source(db)


def test_a_source_item_is_imported_once(db: Session) -> None:
    usda = add_source(db)
    other = add_source(db, "another-source")
    add_catalog_food(db, usda, "171077")

    with (
        pytest.raises(IntegrityError, match="uq_catalog_foods_source_id_source_ref"),
        db.begin_nested(),
    ):
        add_catalog_food(db, usda, "171077")

    add_catalog_food(db, other, "171077")  # the same ref at another source
    assert count(db, CatalogFood, source_ref="171077") == 2


def test_a_source_exercise_is_imported_once(db: Session) -> None:
    source = add_source(db, "free-exercise-db")
    add_catalog_exercise(db, source)

    with (
        pytest.raises(
            IntegrityError, match="uq_catalog_exercises_source_id_source_ref"
        ),
        db.begin_nested(),
    ):
        add_catalog_exercise(db, source)


@pytest.mark.parametrize(
    "nutrient",
    ["calories_per_100g", "protein_per_100g", "carbs_per_100g", "fat_per_100g"],
)
def test_catalog_foods_reject_negative_nutrients(db: Session, nutrient: str) -> None:
    source = add_source(db)

    with (
        pytest.raises(IntegrityError, match="ck_catalog_foods_non_negative"),
        db.begin_nested(),
    ):
        add_catalog_food(db, source, **{nutrient: -1})


def test_one_copy_of_a_catalog_food_per_user(db: Session, make_user: MakeUser) -> None:
    andrei = make_user("andrei@example.com")
    other = make_user("other@example.com")
    chicken = add_catalog_food(db, add_source(db))
    add_copy(db, andrei, chicken)

    with (
        pytest.raises(IntegrityError, match="uq_foods_user_id_catalog_food_id"),
        db.begin_nested(),
    ):
        add_copy(db, andrei, chicken)

    add_copy(db, other, chicken)  # every user gets their own copy
    assert count(db, Food, catalog_food_id=chicken.id) == 2


def test_foods_typed_in_by_hand_are_not_limited(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user("andrei@example.com")

    add_copy(db, user, None)
    add_copy(db, user, None)  # NULLs never conflict

    assert count(db, Food, user_id=user.id, catalog_food_id=None) == 2


def test_one_copy_of_a_catalog_exercise_per_user(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user("andrei@example.com")
    squat = add_catalog_exercise(db, add_source(db, "free-exercise-db"))
    db.add(Exercise(user_id=user.id, name="Squat", catalog_exercise_id=squat.id))
    db.flush()

    with (
        pytest.raises(IntegrityError, match="uq_exercises_user_id_catalog_exercise_id"),
        db.begin_nested(),
    ):
        db.add(Exercise(user_id=user.id, name="Squat 2", catalog_exercise_id=squat.id))
        db.flush()


def test_a_copy_must_point_at_an_existing_catalog_food(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user("andrei@example.com")

    with (
        pytest.raises(IntegrityError, match="fk_foods_catalog_food_id"),
        db.begin_nested(),
    ):
        db.add(
            Food(
                user_id=user.id,
                name="Ghost",
                calories_per_100g=1,
                protein_per_100g=0,
                carbs_per_100g=0,
                fat_per_100g=0,
                catalog_food_id=2_000_000_000,
            )
        )
        db.flush()


def test_a_catalog_food_with_copies_cannot_be_deleted(
    db: Session, make_user: MakeUser
) -> None:
    # The import never deletes; by hand, the database refuses while a copy
    # points at it, so no user's food loses where it came from
    chicken = add_catalog_food(db, add_source(db))
    add_copy(db, make_user("andrei@example.com"), chicken)

    with (
        pytest.raises(IntegrityError, match="fk_foods_catalog_food_id"),
        db.begin_nested(),
    ):
        db.execute(delete(CatalogFood).where(CatalogFood.id == chicken.id))

    assert count(db, CatalogFood, id=chicken.id) == 1


def test_deleting_a_user_keeps_the_catalog(db: Session, make_user: MakeUser) -> None:
    andrei = make_user("andrei@example.com")
    chicken = add_catalog_food(db, add_source(db))
    add_copy(db, andrei, chicken)

    db.execute(delete(User).where(User.id == andrei.id))

    assert count(db, Food, user_id=andrei.id) == 0
    assert count(db, CatalogFood, id=chicken.id) == 1


def test_the_previous_version_still_inserts_foods_and_exercises(
    db: Session, make_user: MakeUser
) -> None:
    # Expand-only: the previous image's INSERTs name only the old columns
    user = make_user("andrei@example.com")

    db.execute(
        text(
            "INSERT INTO foods (user_id, name, calories_per_100g, "
            "protein_per_100g, carbs_per_100g, fat_per_100g) "
            "VALUES (:user_id, 'Rice', 130, 2.7, 28, 0.3)"
        ),
        {"user_id": user.id},
    )
    db.execute(
        text("INSERT INTO exercises (user_id, name) VALUES (:user_id, 'Squat')"),
        {"user_id": user.id},
    )

    assert count(db, Food, user_id=user.id, catalog_food_id=None) == 1
    assert count(db, Exercise, user_id=user.id, catalog_exercise_id=None) == 1
