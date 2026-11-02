"""Database constraints, checked against the schema the migrations create.

Each constraint violation runs inside a savepoint (begin_nested): PostgreSQL
aborts a transaction after an error, and rolling back to the savepoint keeps
the test's transaction usable. A deferred constraint is only checked at
COMMIT, which these rolled-back tests never reach: SET CONSTRAINTS ALL
IMMEDIATE runs that check on the spot.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Exercise,
    Food,
    MealEntry,
    User,
    Workout,
    WorkoutExercise,
    WorkoutSet,
)

pytestmark = pytest.mark.integration

MakeUser = Callable[[str], User]


def add_food(db: Session, user: User, name: str = "Rice", **overrides: Any) -> Food:
    food = Food(
        user_id=user.id,
        name=name,
        **{
            "calories_per_100g": 130,
            "protein_per_100g": 2.6,
            "carbs_per_100g": 28,
            "fat_per_100g": 0.34,
            **overrides,
        },
    )
    db.add(food)
    db.flush()
    return food


def add_entry(db: Session, user: User, food: Food, **overrides: Any) -> MealEntry:
    entry = MealEntry(
        user_id=user.id,
        food_id=food.id,
        **{
            "eaten_on": date(2026, 11, 1),
            "meal_type": "lunch",
            "grams": 150,
            **overrides,
        },
    )
    db.add(entry)
    db.flush()
    return entry


def add_exercise(db: Session, user: User, name: str = "Squat") -> Exercise:
    exercise = Exercise(user_id=user.id, name=name)
    db.add(exercise)
    db.flush()
    return exercise


def add_workout(
    db: Session,
    user: User,
    exercise: Exercise,
    sets: tuple[tuple[int, float], ...] = ((8, 60), (8, 60)),
) -> Workout:
    workout = Workout(
        user_id=user.id,
        performed_on=date(2026, 11, 1),
        exercises=[
            WorkoutExercise(
                exercise_id=exercise.id,
                sets=[WorkoutSet(reps=reps, weight_kg=kg) for reps, kg in sets],
            )
        ],
    )
    db.add(workout)
    db.flush()
    return workout


def check_deferred_constraints(db: Session) -> None:
    """Run the checks that COMMIT would run, now."""
    db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def count(db: Session, model: type, **filters: Any) -> int:
    query = select(func.count()).select_from(model).filter_by(**filters)
    return db.scalar(query) or 0


def test_food_names_are_unique_per_user(db: Session, make_user: MakeUser) -> None:
    andrei = make_user("andrei@example.com")
    other = make_user("other@example.com")
    add_food(db, andrei, "Rice")

    with (
        pytest.raises(IntegrityError, match="uq_foods_user_id_name"),
        db.begin_nested(),
    ):
        add_food(db, andrei, "Rice")

    add_food(db, other, "Rice")  # the same name for another user is fine
    assert count(db, Food, name="Rice") == 2


def test_food_used_by_entries_cannot_be_deleted(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user("andrei@example.com")
    food = add_food(db, user)
    add_entry(db, user, food)

    with (
        pytest.raises(IntegrityError, match="meal_entries_food_id_fkey"),
        db.begin_nested(),
    ):
        db.execute(delete(Food).where(Food.id == food.id))

    assert count(db, Food, id=food.id) == 1


def test_unused_food_can_be_deleted(db: Session, make_user: MakeUser) -> None:
    user = make_user("andrei@example.com")
    food = add_food(db, user)

    db.execute(delete(Food).where(Food.id == food.id))

    assert count(db, Food, id=food.id) == 0


def test_deleting_a_user_deletes_their_foods_and_entries(
    db: Session, make_user: MakeUser
) -> None:
    andrei = make_user("andrei@example.com")
    other = make_user("other@example.com")
    food = add_food(db, andrei)
    add_entry(db, andrei, food)
    other_food = add_food(db, other)
    add_entry(db, other, other_food)

    db.execute(delete(User).where(User.id == andrei.id))

    assert count(db, Food, user_id=andrei.id) == 0
    assert count(db, MealEntry, user_id=andrei.id) == 0
    assert count(db, Food, user_id=other.id) == 1
    assert count(db, MealEntry, user_id=other.id) == 1


@pytest.mark.parametrize(
    "nutrient",
    ["calories_per_100g", "protein_per_100g", "carbs_per_100g", "fat_per_100g"],
)
def test_foods_reject_negative_nutrients(
    db: Session, make_user: MakeUser, nutrient: str
) -> None:
    user = make_user("andrei@example.com")

    with (
        pytest.raises(IntegrityError, match="ck_foods_non_negative_nutrients"),
        db.begin_nested(),
    ):
        add_food(db, user, **{nutrient: -1})


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"grams": 0}, "ck_meal_entries_positive_grams"),
        ({"grams": -10}, "ck_meal_entries_positive_grams"),
        ({"meal_type": "brunch"}, "ck_meal_entries_meal_type"),
    ],
)
def test_meal_entries_check_constraints(
    db: Session, make_user: MakeUser, overrides: dict[str, Any], constraint: str
) -> None:
    user = make_user("andrei@example.com")
    food = add_food(db, user)

    with pytest.raises(IntegrityError, match=constraint), db.begin_nested():
        add_entry(db, user, food, **overrides)


def test_exercise_names_are_unique_per_user_ignoring_case(
    db: Session, make_user: MakeUser
) -> None:
    andrei = make_user("andrei@example.com")
    other = make_user("other@example.com")
    add_exercise(db, andrei, "Squat")

    with (
        pytest.raises(IntegrityError, match="uq_exercises_user_id_lower_name"),
        db.begin_nested(),
    ):
        add_exercise(db, andrei, "squat")

    add_exercise(db, other, "SQUAT")  # the same name for another user is fine
    assert count(db, Exercise, user_id=andrei.id) == 1
    assert count(db, Exercise, user_id=other.id) == 1


def test_exercise_used_by_a_workout_cannot_be_deleted(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user("andrei@example.com")
    exercise = add_exercise(db, user)
    add_workout(db, user, exercise)

    with (
        pytest.raises(IntegrityError, match="workout_exercises_exercise_id_fkey"),
        db.begin_nested(),
    ):
        db.execute(delete(Exercise).where(Exercise.id == exercise.id))
        check_deferred_constraints(db)

    assert count(db, Exercise, id=exercise.id) == 1


def test_unused_exercise_can_be_deleted(db: Session, make_user: MakeUser) -> None:
    user = make_user("andrei@example.com")
    exercise = add_exercise(db, user)

    db.execute(delete(Exercise).where(Exercise.id == exercise.id))
    check_deferred_constraints(db)

    assert count(db, Exercise, id=exercise.id) == 0


def test_deleting_a_workout_deletes_its_exercises_and_sets(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user("andrei@example.com")
    exercise = add_exercise(db, user)
    workout = add_workout(db, user, exercise)
    workout_exercise_id = workout.exercises[0].id

    db.execute(delete(Workout).where(Workout.id == workout.id))
    check_deferred_constraints(db)

    assert count(db, WorkoutExercise, workout_id=workout.id) == 0
    assert count(db, WorkoutSet, workout_exercise_id=workout_exercise_id) == 0
    assert count(db, Exercise, id=exercise.id) == 1  # the catalog keeps it


def test_deleting_a_user_deletes_their_workouts_and_exercises(
    db: Session, make_user: MakeUser
) -> None:
    # The case the deferred foreign key exists for: the user's exercises are
    # still used by the user's workouts when the user is deleted
    andrei = make_user("andrei@example.com")
    other = make_user("other@example.com")
    workout = add_workout(db, andrei, add_exercise(db, andrei))
    workout_exercise_id = workout.exercises[0].id
    add_workout(db, other, add_exercise(db, other))

    db.execute(delete(User).where(User.id == andrei.id))
    check_deferred_constraints(db)

    assert count(db, Workout, user_id=andrei.id) == 0
    assert count(db, Exercise, user_id=andrei.id) == 0
    assert count(db, WorkoutExercise, workout_id=workout.id) == 0
    assert count(db, WorkoutSet, workout_exercise_id=workout_exercise_id) == 0
    assert count(db, Workout, user_id=other.id) == 1
    assert count(db, Exercise, user_id=other.id) == 1


@pytest.mark.parametrize(
    ("reps", "weight_kg", "constraint"),
    [
        (0, 60, "ck_workout_sets_positive_reps"),
        (-1, 60, "ck_workout_sets_positive_reps"),
        (8, -0.5, "ck_workout_sets_non_negative_weight"),
    ],
)
def test_workout_sets_check_constraints(
    db: Session,
    make_user: MakeUser,
    reps: int,
    weight_kg: float,
    constraint: str,
) -> None:
    user = make_user("andrei@example.com")
    exercise = add_exercise(db, user)

    with pytest.raises(IntegrityError, match=constraint), db.begin_nested():
        add_workout(db, user, exercise, sets=((reps, weight_kg),))


def test_bodyweight_sets_are_allowed(db: Session, make_user: MakeUser) -> None:
    user = make_user("andrei@example.com")

    workout = add_workout(db, user, add_exercise(db, user, "Pull-up"), ((10, 0),))

    assert workout.exercises[0].sets[0].weight_kg == 0
