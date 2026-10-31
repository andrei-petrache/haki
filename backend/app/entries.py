from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentUser, SessionDep
from app.foods import get_own_food
from app.models import MEAL_TYPES, Food, MealEntry, User
from app.schemas import IdPath, MealEntryIn, MealEntryResponse, Nutrients

router = APIRouter(prefix="/entries", tags=["entries"])

# The client always sends the day: its local day may differ from the server's.
DayQuery = Annotated[date, Query(alias="date")]

# Sort meals in the order they happen in a day, not alphabetically
MEAL_ORDER = case(
    {meal: position for position, meal in enumerate(MEAL_TYPES)},
    value=MealEntry.meal_type,
)


def nutrients_for(food: Food, grams: float) -> Nutrients:
    """Nutrients in the given amount of a food."""
    factor = grams / 100
    return Nutrients(
        calories=food.calories_per_100g * factor,
        protein=food.protein_per_100g * factor,
        carbs=food.carbs_per_100g * factor,
        fat=food.fat_per_100g * factor,
    )


def to_response(entry: MealEntry) -> MealEntryResponse:
    return MealEntryResponse(
        id=entry.id,
        food_id=entry.food_id,
        food_name=entry.food.name,
        eaten_on=entry.eaten_on,
        meal_type=entry.meal_type,
        grams=entry.grams,
        **nutrients_for(entry.food, entry.grams).model_dump(),
    )


def entries_for_day(session: Session, user: User, day: date) -> list[MealEntry]:
    """The user's entries for one day, by meal then creation time."""
    query = (
        select(MealEntry)
        # Load each entry's food in the same query, instead of one query per entry
        .options(joinedload(MealEntry.food))
        .where(MealEntry.user_id == user.id, MealEntry.eaten_on == day)
        .order_by(MEAL_ORDER, MealEntry.created_at, MealEntry.id)
    )
    return list(session.scalars(query))


def get_own_entry(session: Session, user: User, entry_id: int) -> MealEntry:
    """Load one of the user's entries, or reject with 404 (see get_own_food)."""
    entry = session.get(MealEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found"
        )
    return entry


@router.get("", response_model=list[MealEntryResponse])
def list_entries(
    day: DayQuery, current_user: CurrentUser, session: SessionDep
) -> list[MealEntryResponse]:
    """Return the current user's entries for one day."""
    return [to_response(entry) for entry in entries_for_day(session, current_user, day)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MealEntryResponse)
def create_entry(
    data: MealEntryIn, current_user: CurrentUser, session: SessionDep
) -> MealEntryResponse:
    """Log an amount of one of the current user's foods."""
    # Checking only the entry isn't enough: the food must be the user's too
    food = get_own_food(session, current_user, data.food_id)
    entry = MealEntry(
        user_id=current_user.id,
        food=food,
        eaten_on=data.eaten_on,
        meal_type=data.meal_type,
        grams=data.grams,
    )
    session.add(entry)
    session.commit()
    return to_response(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's entries."""
    entry = get_own_entry(session, current_user, entry_id)
    session.delete(entry)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
