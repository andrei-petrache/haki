from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.errors import ApiError, ErrorCode
from app.models import CatalogFood, Food, MealEntry, User
from app.schemas import CatalogFoodCopyIn, FoodIn, FoodResponse, IdPath, LastLogged

router = APIRouter(prefix="/foods", tags=["foods"])


def get_own_food(session: Session, user: User, food_id: int) -> Food:
    """Load one of the user's foods, or reject with 404.

    Another user's food also gets 404 (not 403), so clients cannot
    probe which ids exist.
    """
    food = session.get(Food, food_id)
    if food is None or food.user_id != user.id:
        raise ApiError(ErrorCode.FOOD_NOT_FOUND)
    return food


def newest_entries(
    session: Session, user: User, food_ids: list[int]
) -> dict[int, MealEntry]:
    """The user's newest entry of each food, by entry id, in one query."""
    if not food_ids:
        return {}
    newest = (
        select(func.max(MealEntry.id))
        .where(MealEntry.user_id == user.id, MealEntry.food_id.in_(food_ids))
        .group_by(MealEntry.food_id)
    )
    entries = session.scalars(select(MealEntry).where(MealEntry.id.in_(newest)))
    return {entry.food_id: entry for entry in entries}


def to_last_logged(entry: MealEntry | None) -> LastLogged | None:
    """How an entry logged its food, or None without an entry."""
    if entry is None:
        return None
    return LastLogged(
        grams=entry.grams, meal_type=entry.meal_type, eaten_on=entry.eaten_on
    )


def last_logged(
    session: Session, user: User, food_ids: list[int]
) -> dict[int, LastLogged | None]:
    """How the user last logged each food that they ever logged."""
    return {
        food_id: to_last_logged(entry)
        for food_id, entry in newest_entries(session, user, food_ids).items()
    }


def food_responses(
    session: Session, user: User, foods: list[Food]
) -> list[FoodResponse]:
    """The foods as responses, each with how it was last logged."""
    last = last_logged(session, user, [food.id for food in foods])
    return [
        FoodResponse.model_validate(food).model_copy(
            update={"last_logged": last.get(food.id)}
        )
        for food in foods
    ]


def food_response(session: Session, user: User, food: Food) -> FoodResponse:
    return food_responses(session, user, [food])[0]


def commit_or_conflict(session: Session, code: ErrorCode) -> None:
    """Commit, turning a database constraint violation into the 409 `code`."""
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(code) from None


@router.get("", response_model=list[FoodResponse])
def list_foods(
    current_user: CurrentUser,
    session: SessionDep,
    favourite: Annotated[bool | None, Query()] = None,
) -> list[FoodResponse]:
    """Return the current user's foods, sorted by name; with favourite=true
    only their favourites, with favourite=false only the others."""
    query = select(Food).where(Food.user_id == current_user.id).order_by(Food.name)
    if favourite is True:
        query = query.where(Food.favourited_at.is_not(None))
    elif favourite is False:
        query = query.where(Food.favourited_at.is_(None))
    return food_responses(session, current_user, list(session.scalars(query)))


@router.get("/recent", response_model=list[FoodResponse])
def list_recent_foods(
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[FoodResponse]:
    """Return the current user's foods by when they were last logged, newest
    first, each once. Foods never logged are left out.

    "Last logged" is the newest entry's id, not its day: a meal logged today
    for yesterday counts as used today, and ids never tie, unlike times.
    """
    last_use = (
        select(MealEntry.food_id, func.max(MealEntry.id).label("last_entry_id"))
        .where(MealEntry.user_id == current_user.id)
        .group_by(MealEntry.food_id)
        .subquery()
    )
    query = (
        select(Food)
        .join(last_use, last_use.c.food_id == Food.id)
        # Entries can only point at their owner's foods; checked again anyway
        .where(Food.user_id == current_user.id)
        .order_by(last_use.c.last_entry_id.desc())
        .limit(limit)
    )
    return food_responses(session, current_user, list(session.scalars(query)))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=FoodResponse)
def create_food(
    data: FoodIn, current_user: CurrentUser, session: SessionDep
) -> FoodResponse:
    """Add a food to the current user's list."""
    food = Food(user_id=current_user.id, **data.model_dump())
    session.add(food)
    commit_or_conflict(session, ErrorCode.FOOD_NAME_TAKEN)
    session.refresh(food)
    return food_response(session, current_user, food)


def find_own_copy(session: Session, user: User, catalog_food_id: int) -> Food | None:
    """The user's copy of a catalog food, if they have one; never another's."""
    query = select(Food).where(
        Food.user_id == user.id, Food.catalog_food_id == catalog_food_id
    )
    return session.scalar(query)


@router.post(
    "/from-catalog", status_code=status.HTTP_201_CREATED, response_model=FoodResponse
)
def copy_catalog_food(
    data: CatalogFoodCopyIn,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
) -> FoodResponse:
    """Add a catalog food to the current user's list, as their own copy.

    201 with the new copy; 200 with the existing one if the user already
    has it (asking twice is harmless); 404 for an unknown catalog food;
    409 if one of the user's own foods already has the name.
    """
    item = session.get(CatalogFood, data.catalog_food_id)
    if item is None:
        raise ApiError(ErrorCode.CATALOG_FOOD_NOT_FOUND)
    existing = find_own_copy(session, current_user, item.id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return food_response(session, current_user, existing)
    food = Food(
        user_id=current_user.id,
        name=item.name_ro if data.language == "ro" and item.name_ro else item.name,
        calories_per_100g=item.calories_per_100g,
        protein_per_100g=item.protein_per_100g,
        carbs_per_100g=item.carbs_per_100g,
        fat_per_100g=item.fat_per_100g,
        catalog_food_id=item.id,
    )
    session.add(food)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # A second request for the same copy can win the race: return its copy
        existing = find_own_copy(session, current_user, item.id)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return food_response(session, current_user, existing)
        raise ApiError(ErrorCode.FOOD_NAME_TAKEN) from None
    session.refresh(food)
    return food_response(session, current_user, food)


@router.put("/{food_id}", response_model=FoodResponse)
def update_food(
    food_id: IdPath, data: FoodIn, current_user: CurrentUser, session: SessionDep
) -> FoodResponse:
    """Replace all fields of one of the current user's foods."""
    food = get_own_food(session, current_user, food_id)
    for field, value in data.model_dump().items():
        setattr(food, field, value)
    commit_or_conflict(session, ErrorCode.FOOD_NAME_TAKEN)
    session.refresh(food)
    return food_response(session, current_user, food)


@router.delete("/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_food(
    food_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's foods, unless meal entries use it."""
    food = get_own_food(session, current_user, food_id)
    session.delete(food)
    # meal_entries.food_id is ON DELETE RESTRICT, so the database refuses
    commit_or_conflict(session, ErrorCode.FOOD_IN_USE)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{food_id}/favourite", response_model=FoodResponse)
def mark_favourite(
    food_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> FoodResponse:
    """Mark one of the current user's foods as a favourite. Idempotent: a
    favourite stays one, with the time it was first marked."""
    food = get_own_food(session, current_user, food_id)
    if food.favourited_at is None:
        food.favourited_at = datetime.now(UTC)
        session.commit()
    return food_response(session, current_user, food)


@router.delete("/{food_id}/favourite", status_code=status.HTTP_204_NO_CONTENT)
def unmark_favourite(
    food_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Stop one of the current user's foods being a favourite. Idempotent."""
    food = get_own_food(session, current_user, food_id)
    if food.favourited_at is not None:
        food.favourited_at = None
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
