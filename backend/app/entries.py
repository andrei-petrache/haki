import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentUser, SessionDep
from app.errors import ApiError, ErrorCode
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

# Far above any real meal. Without it, copying a meal onto another and
# back doubles a user's rows each time: 27 requests made 514,229 rows
MAX_ENTRIES_PER_MEAL = 100
MEAL_FULL = f"A meal holds at most {MAX_ENTRIES_PER_MEAL} entries"

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
    catalog = entry.food.catalog_food
    return MealEntryResponse(
        id=entry.id,
        food_id=entry.food_id,
        food_name=entry.food.name,
        catalog_name=catalog.name if catalog else None,
        catalog_name_ro=catalog.name_ro if catalog else None,
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
        .options(joinedload(MealEntry.food).joinedload(Food.catalog_food))
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


def check_room(session: Session, user: User, day: date, meal: str, adding: int) -> None:
    """409 if `adding` entries would take one meal of one day past
    MAX_ENTRIES_PER_MEAL, food and quick entries counted together.

    Two requests at once can both pass and overshoot by one request's
    worth; the bound stays linear, which is what it is for.
    """
    count = 0
    for model in (MealEntry, QuickEntry):
        count += (
            session.scalar(
                select(func.count())
                .select_from(model)
                .where(
                    model.user_id == user.id,
                    model.eaten_on == day,
                    model.meal_type == meal,
                )
            )
            or 0
        )
    if count + adding > MAX_ENTRIES_PER_MEAL:
        raise ApiError(ErrorCode.MEAL_FULL, detail=MEAL_FULL)


def get_own_entry(session: Session, user: User, entry_id: int) -> MealEntry:
    """Load one of the user's entries, or reject with 404 (see get_own_food)."""
    entry = session.get(MealEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise ApiError(ErrorCode.ENTRY_NOT_FOUND)
    return entry


@router.get("", response_model=list[MealEntryResponse])
def list_entries(
    day: DayQuery, current_user: CurrentUser, session: SessionDep
) -> list[MealEntryResponse]:
    """Return the current user's entries for one day, quick ones included."""
    return day_entries(session, current_user, day)


# Idempotency-Key: a UUID the client makes once per entry it queues (offline
# logging), so the same request sent again, after its answer got lost,
# returns the entry made the first time instead of logging the meal twice
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=64)]


def parse_key(raw: str | None) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise ApiError(ErrorCode.INVALID_IDEMPOTENCY_KEY) from None


def keyed[E: (MealEntry, QuickEntry)](
    session: Session, model: type[E], user: User, key: uuid.UUID
) -> E | None:
    """The user's entry made with this key, if any; never another user's."""
    query = select(model).where(model.user_id == user.id, model.client_key == key)
    return session.scalar(query)


def replay[E: (MealEntry, QuickEntry)](
    existing: E, data: MealEntryIn | QuickEntryIn, response: Response
) -> E:
    """The entry made the first time, with 200, if the body is the same;
    409 if the key comes back with another body (a client bug)."""
    for field, value in data.model_dump().items():
        if getattr(existing, field) != value:
            raise ApiError(ErrorCode.IDEMPOTENCY_KEY_REUSED)
    response.status_code = status.HTTP_200_OK
    return existing


def create_once[E: (MealEntry, QuickEntry)](
    session: Session,
    user: User,
    entry: E,
    data: MealEntryIn | QuickEntryIn,
    response: Response,
) -> E:
    """Commit a new entry. With a key, two requests at once both pass the
    lookup; the unique index lets one in, and the other gets its entry."""
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = None
        if entry.client_key is not None:
            existing = keyed(session, type(entry), user, entry.client_key)
        if existing is None:
            raise
        return replay(existing, data, response)
    return entry


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MealEntryResponse)
def create_entry(
    data: MealEntryIn,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> MealEntryResponse:
    """Log an amount of one of the current user's foods: 201. With an
    Idempotency-Key already used for the same body: 200 and that entry;
    for another body: 409 idempotency_key_reused."""
    key = parse_key(idempotency_key)
    if key is not None and (existing := keyed(session, MealEntry, current_user, key)):
        return to_response(replay(existing, data, response))
    # Checking only the entry isn't enough: the food must be the user's too
    food = get_own_food(session, current_user, data.food_id)
    check_room(session, current_user, data.eaten_on, data.meal_type, 1)
    entry = MealEntry(
        user_id=current_user.id,
        food=food,
        eaten_on=data.eaten_on,
        meal_type=data.meal_type,
        grams=data.grams,
        client_key=key,
    )
    return to_response(create_once(session, current_user, entry, data, response))


@router.post(
    "/quick", status_code=status.HTTP_201_CREATED, response_model=MealEntryResponse
)
def create_quick_entry(
    data: QuickEntryIn,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> MealEntryResponse:
    """Log calories (and maybe macros) without a food. Idempotency-Key as
    for POST /entries."""
    key = parse_key(idempotency_key)
    if key is not None and (existing := keyed(session, QuickEntry, current_user, key)):
        return quick_to_response(replay(existing, data, response))
    check_room(session, current_user, data.eaten_on, data.meal_type, 1)
    entry = QuickEntry(user_id=current_user.id, client_key=key, **data.model_dump())
    return quick_to_response(create_once(session, current_user, entry, data, response))


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
        .options(joinedload(MealEntry.food).joinedload(Food.catalog_food))
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
    # The target meal must have room for all of them, or nothing is copied
    check_room(
        session,
        current_user,
        data.to_day,
        data.to_meal,
        len(copies) + len(quick_copies),
    )
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
        raise ApiError(ErrorCode.ENTRY_NOT_FOUND)
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
