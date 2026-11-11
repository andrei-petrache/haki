from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.foods import commit_or_conflict
from app.models import CatalogExercise, Exercise, User
from app.schemas import CatalogExerciseCopyIn, ExerciseIn, ExerciseResponse, IdPath

router = APIRouter(prefix="/exercises", tags=["exercises"])

DUPLICATE_NAME = "An exercise with this name already exists"
IN_USE = "Exercise is used by workouts or programs"


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


def find_own_copy(
    session: Session, user: User, catalog_exercise_id: int
) -> Exercise | None:
    """The user's copy of a catalog exercise, if any; never another user's."""
    query = select(Exercise).where(
        Exercise.user_id == user.id,
        Exercise.catalog_exercise_id == catalog_exercise_id,
    )
    return session.scalar(query)


@router.post(
    "/from-catalog",
    status_code=status.HTTP_201_CREATED,
    response_model=ExerciseResponse,
)
def copy_catalog_exercise(
    data: CatalogExerciseCopyIn,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
) -> Exercise:
    """Add a catalog exercise to the current user's catalog, as their own copy.

    Same answers as POST /foods/from-catalog: 201, 200 with the existing
    copy, 404 for an unknown catalog exercise, 409 if the name (ignoring
    case) is taken by one of the user's own exercises.
    """
    item = session.get(CatalogExercise, data.catalog_exercise_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Catalog exercise not found"
        )
    existing = find_own_copy(session, current_user, item.id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing
    exercise = Exercise(
        user_id=current_user.id,
        name=item.name_ro if data.language == "ro" and item.name_ro else item.name,
        catalog_exercise_id=item.id,
    )
    session.add(exercise)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # A second request for the same copy can win the race: return its copy
        existing = find_own_copy(session, current_user, item.id)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return existing
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_NAME
        ) from None
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
    """Delete one of the user's exercises, unless a workout or a program uses it."""
    exercise = get_own_exercise(session, current_user, exercise_id)
    session.delete(exercise)
    # workout_exercises.exercise_id and program_exercises.exercise_id are
    # deferred: the database refuses at commit
    commit_or_conflict(session, IN_USE)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
