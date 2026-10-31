from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_serializer,
)

FoodName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
# Must match MEAL_TYPES in app/models.py
MealType = Literal["breakfast", "lunch", "dinner", "snack"]


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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


class MealEntryIn(BaseModel):
    food_id: int
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

    def __add__(self, other: "Nutrients") -> "Nutrients":
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
