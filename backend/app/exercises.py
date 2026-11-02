from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.foods import commit_or_conflict
from app.models import Exercise, User
from app.schemas import ExerciseIn, ExerciseResponse, IdPath

router = APIRouter(prefix="/exercises", tags=["exercises"])

DUPLICATE_NAME = "An exercise with this name already exists"


def get_own_exercise(session: Session, user: User, exercise_id: int) -> Exercise:
    """Load one of the user's exercises, or reject with 404 (see get_own_food)."""
    exercise = session.get(Exercise, exercise_id)
    if exercise is None or exercise.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found"
        )
    return exercise


@router.get("", response_model=list[ExerciseResponse])
def list_exercises(current_user: CurrentUser, session: SessionDep) -> list[Exercise]:
    """Return the current user's exercises, sorted by name ignoring case."""
    query = (
        select(Exercise)
        .where(Exercise.user_id == current_user.id)
        .order_by(func.lower(Exercise.name), Exercise.id)
    )
    return list(session.scalars(query))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ExerciseResponse)
def create_exercise(
    data: ExerciseIn, current_user: CurrentUser, session: SessionDep
) -> Exercise:
    """Add an exercise to the current user's catalog."""
    exercise = Exercise(user_id=current_user.id, name=data.name)
    session.add(exercise)
    # The unique index ignores case: "squat" conflicts with "Squat"
    commit_or_conflict(session, DUPLICATE_NAME)
    session.refresh(exercise)
    return exercise


@router.put("/{exercise_id}", response_model=ExerciseResponse)
def rename_exercise(
    exercise_id: IdPath,
    data: ExerciseIn,
    current_user: CurrentUser,
    session: SessionDep,
) -> Exercise:
    """Rename one of the current user's exercises; past workouts follow."""
    exercise = get_own_exercise(session, current_user, exercise_id)
    exercise.name = data.name
    commit_or_conflict(session, DUPLICATE_NAME)
    session.refresh(exercise)
    return exercise


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise(
    exercise_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's exercises, unless a workout uses it."""
    exercise = get_own_exercise(session, current_user, exercise_id)
    session.delete(exercise)
    # workout_exercises.exercise_id is deferred: the database refuses at commit
    commit_or_conflict(session, "Exercise is used by workouts")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
