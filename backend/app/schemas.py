from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

FoodName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


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
    created_at: datetime


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
