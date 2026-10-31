from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.models import Food, User
from app.schemas import FoodIn, FoodResponse

router = APIRouter(prefix="/foods", tags=["foods"])


def get_own_food(session: Session, user: User, food_id: int) -> Food:
    """Load one of the user's foods, or reject with 404.

    Another user's food also gets 404 (not 403), so clients cannot
    probe which ids exist.
    """
    food = session.get(Food, food_id)
    if food is None or food.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Food not found"
        )
    return food


def commit_or_conflict(session: Session, detail: str) -> None:
    """Commit, turning a database constraint violation into a 409."""
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=detail
        ) from None


@router.get("", response_model=list[FoodResponse])
def list_foods(current_user: CurrentUser, session: SessionDep) -> list[Food]:
    """Return the current user's foods, sorted by name."""
    query = select(Food).where(Food.user_id == current_user.id).order_by(Food.name)
    return list(session.scalars(query))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=FoodResponse)
def create_food(data: FoodIn, current_user: CurrentUser, session: SessionDep) -> Food:
    """Add a food to the current user's list."""
    food = Food(user_id=current_user.id, **data.model_dump())
    session.add(food)
    commit_or_conflict(session, "A food with this name already exists")
    session.refresh(food)
    return food


@router.put("/{food_id}", response_model=FoodResponse)
def update_food(
    food_id: int, data: FoodIn, current_user: CurrentUser, session: SessionDep
) -> Food:
    """Replace all fields of one of the current user's foods."""
    food = get_own_food(session, current_user, food_id)
    for field, value in data.model_dump().items():
        setattr(food, field, value)
    commit_or_conflict(session, "A food with this name already exists")
    session.refresh(food)
    return food


@router.delete("/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_food(
    food_id: int, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's foods, unless meal entries use it."""
    food = get_own_food(session, current_user, food_id)
    session.delete(food)
    # meal_entries.food_id is ON DELETE RESTRICT, so the database refuses
    commit_or_conflict(session, "Food is used by meal entries")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
