from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Path
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)

FoodName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
ExerciseName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
WorkoutNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
# Must match MEAL_TYPES in app/models.py
MealType = Literal["breakfast", "lunch", "dinner", "snack"]

# Ids are PostgreSQL "integer" columns. A larger number cannot be an id, and
# sending it to the database raises an error (a 500) instead of "not found".
MAX_DB_ID = 2_147_483_647
DbId = Annotated[int, Field(ge=1, le=MAX_DB_ID)]  # in request bodies
IdPath = Annotated[int, Path(ge=1, le=MAX_DB_ID)]  # in URL paths
# Same limit as signup, so login never hashes an arbitrarily large input
PASSWORD_MAX_LENGTH = 128


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class UserResponse(BaseModel):
    """Public view of a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    daily_calorie_target: int | None
    created_at: datetime


class CalorieTargetIn(BaseModel):
    """Required field: clients send null explicitly to clear the target."""

    daily_calorie_target: int | None = Field(ge=500, le=10000)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class FoodIn(BaseModel):
    """Nutrients per 100 g. Upper bounds reject impossible values."""

    name: FoodName
    calories_per_100g: float = Field(ge=0, le=900)
    protein_per_100g: float = Field(ge=0, le=100)
    carbs_per_100g: float = Field(ge=0, le=100)
    fat_per_100g: float = Field(ge=0, le=100)


class FoodResponse(FoodIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ExerciseIn(BaseModel):
    name: ExerciseName


class ExerciseResponse(ExerciseIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


# Upper bounds on what one request may write: at most 50 x 50 sets
MAX_EXERCISES_PER_WORKOUT = 50
MAX_SETS_PER_EXERCISE = 50
EARLIEST_WORKOUT_DATE = date(2000, 1, 1)


class WorkoutSetIn(BaseModel):
    reps: int = Field(ge=1, le=1000)
    # 0 for bodyweight exercises
    weight_kg: float = Field(ge=0, le=1000)


class WorkoutExerciseIn(BaseModel):
    exercise_id: DbId
    sets: list[WorkoutSetIn] = Field(min_length=1, max_length=MAX_SETS_PER_EXERCISE)


class WorkoutIn(BaseModel):
    """A whole workout: POST creates it, PUT replaces everything in it."""

    performed_on: date
    note: WorkoutNote | None = None
    exercises: list[WorkoutExerciseIn] = Field(max_length=MAX_EXERCISES_PER_WORKOUT)

    @field_validator("performed_on")
    @classmethod
    def performed_on_is_plausible(cls, value: date) -> date:
        """From 2000-01-01 to tomorrow.

        Tomorrow because the client sends its own local day, which can be a
        day ahead of the server's.
        """
        latest = date.today() + timedelta(days=1)
        if not EARLIEST_WORKOUT_DATE <= value <= latest:
            raise ValueError(f"must be between {EARLIEST_WORKOUT_DATE} and {latest}")
        return value

    @field_validator("note")
    @classmethod
    def blank_note_is_no_note(cls, value: str | None) -> str | None:
        return value or None


class WorkoutSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reps: int
    weight_kg: float


class WorkoutExerciseResponse(BaseModel):
    exercise_id: int
    exercise_name: str
    sets: list[WorkoutSetResponse]


class WorkoutResponse(BaseModel):
    id: int
    performed_on: date
    note: str | None
    exercises: list[WorkoutExerciseResponse]


class WorkoutSummary(BaseModel):
    """One row of the workout list: counts instead of the full contents."""

    id: int
    performed_on: date
    note: str | None
    exercise_count: int
    set_count: int


class MealEntryIn(BaseModel):
    food_id: DbId
    eaten_on: date
    meal_type: MealType
    grams: float = Field(gt=0, le=5000)


class Nutrients(BaseModel):
    """Nutrients computed on the fly, never stored.

    Values stay exact while summing and are rounded only on output,
    so totals don't accumulate rounding errors.
    """

    calories: float = 0
    protein: float = 0
    carbs: float = 0
    fat: float = 0

    @field_serializer("calories", "protein", "carbs", "fat")
    def round_to_one_decimal(self, value: float) -> float:
        return round(value, 1)

    def __add__(self, other: Nutrients) -> Nutrients:
        return Nutrients(
            calories=self.calories + other.calories,
            protein=self.protein + other.protein,
            carbs=self.carbs + other.carbs,
            fat=self.fat + other.fat,
        )


class MealEntryResponse(Nutrients):
    id: int
    food_id: int
    food_name: str
    eaten_on: date
    meal_type: MealType
    grams: float


class DailySummary(BaseModel):
    eaten_on: date
    totals: Nutrients
    meals: dict[MealType, Nutrients]
    daily_calorie_target: int | None
    calories_remaining: float | None
