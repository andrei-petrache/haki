from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentUser, SessionDep
from app.foods import get_own_food
from app.models import MEAL_TYPES, Food, MealEntry, QuickEntry, User
from app.schemas import (
    IdPath,
    MealCopyIn,
    MealEntryIn,
    MealEntryResponse,
    Nutrients,
    QuickEntryIn,
)

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


def quick_to_response(entry: QuickEntry) -> MealEntryResponse:
    return MealEntryResponse(
        id=entry.id,
        food_id=None,
        food_name=entry.name,
        eaten_on=entry.eaten_on,
        meal_type=entry.meal_type,
        grams=None,
        quick=True,
        calories=entry.calories,
        protein=entry.protein,
        carbs=entry.carbs,
        fat=entry.fat,
    )


def entries_for_day(session: Session, user: User, day: date) -> list[MealEntry]:
    """The user's food entries for one day, by meal then creation time."""
    query = (
        select(MealEntry)
        # Load each entry's food in the same query, instead of one query per entry
        .options(joinedload(MealEntry.food))
        .where(MealEntry.user_id == user.id, MealEntry.eaten_on == day)
        .order_by(MEAL_ORDER, MealEntry.created_at, MealEntry.id)
    )
    return list(session.scalars(query))


def quick_entries_for(
    session: Session, user: User, day: date, meal: str | None = None
) -> list[QuickEntry]:
    """The user's quick entries for one day, or for one meal of it."""
    query = select(QuickEntry).where(
        QuickEntry.user_id == user.id, QuickEntry.eaten_on == day
    )
    if meal is not None:
        query = query.where(QuickEntry.meal_type == meal)
    return list(session.scalars(query.order_by(QuickEntry.created_at, QuickEntry.id)))


def day_entries(session: Session, user: User, day: date) -> list[MealEntryResponse]:
    """Every entry of one day, food and quick ones together: by meal, then
    in the order they were added. What /entries lists and /summary adds."""
    rows = [
        (entry.created_at, False, entry.id, to_response(entry))
        for entry in entries_for_day(session, user, day)
    ] + [
        (entry.created_at, True, entry.id, quick_to_response(entry))
        for entry in quick_entries_for(session, user, day)
    ]
    rows.sort(key=lambda row: (MEAL_TYPES.index(row[3].meal_type), *row[:3]))
    return [response for *_, response in rows]


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
    """Return the current user's entries for one day, quick ones included."""
    return day_entries(session, current_user, day)


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


@router.post(
    "/quick", status_code=status.HTTP_201_CREATED, response_model=MealEntryResponse
)
def create_quick_entry(
    data: QuickEntryIn, current_user: CurrentUser, session: SessionDep
) -> MealEntryResponse:
    """Log calories (and maybe macros) without a food."""
    entry = QuickEntry(user_id=current_user.id, **data.model_dump())
    session.add(entry)
    session.commit()
    return quick_to_response(entry)


@router.post(
    "/copy",
    status_code=status.HTTP_201_CREATED,
    response_model=list[MealEntryResponse],
)
def copy_meal(
    data: MealCopyIn, current_user: CurrentUser, session: SessionDep
) -> list[MealEntryResponse]:
    """Copy every entry of one of the current user's meals, quick ones
    included, to another meal or day, in one transaction, and return the new
    entries in their order.

    An empty meal copies nothing and returns an empty list. Copying twice
    logs the meal twice, as logging it again by hand would.
    """
    query = (
        select(MealEntry)
        .options(joinedload(MealEntry.food))
        .where(
            MealEntry.user_id == current_user.id,
            MealEntry.eaten_on == data.from_day,
            MealEntry.meal_type == data.from_meal,
        )
        .order_by(MealEntry.created_at, MealEntry.id)
    )
    copies = [
        MealEntry(
            user_id=current_user.id,
            # The source entries are the user's, so their foods are too
            food=entry.food,
            eaten_on=data.to_day,
            meal_type=data.to_meal,
            grams=entry.grams,
        )
        for entry in session.scalars(query)
    ]
    quick_copies = [
        QuickEntry(
            user_id=current_user.id,
            eaten_on=data.to_day,
            meal_type=data.to_meal,
            name=entry.name,
            calories=entry.calories,
            protein=entry.protein,
            carbs=entry.carbs,
            fat=entry.fat,
        )
        for entry in quick_entries_for(
            session, current_user, data.from_day, data.from_meal
        )
    ]
    session.add_all([*copies, *quick_copies])
    session.commit()
    return [to_response(entry) for entry in copies] + [
        quick_to_response(entry) for entry in quick_copies
    ]


@router.delete("/quick/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quick_entry(
    entry_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's quick entries."""
    entry = session.get(QuickEntry, entry_id)
    if entry is None or entry.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found"
        )
    session.delete(entry)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's food entries."""
    entry = get_own_entry(session, current_user, entry_id)
    session.delete(entry)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
