from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.errors import ApiError, ErrorCode
from app.foods import commit_or_conflict, language_for
from app.models import (
    CatalogExercise,
    Exercise,
    User,
    Workout,
    WorkoutExercise,
    WorkoutSet,
)
from app.schemas import (
    MAX_DB_ID,
    BestSet,
    CatalogExerciseCopyIn,
    ExerciseIn,
    ExerciseResponse,
    IdPath,
    LastSession,
    WorkoutSetResponse,
)

router = APIRouter(prefix="/exercises", tags=["exercises"])


def get_own_exercise(session: Session, user: User, exercise_id: int) -> Exercise:
    """Load one of the user's exercises, or reject with 404 (see get_own_food)."""
    exercise = session.get(Exercise, exercise_id)
    if exercise is None or exercise.user_id != user.id:
        raise ApiError(ErrorCode.EXERCISE_NOT_FOUND)
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
    commit_or_conflict(session, ErrorCode.EXERCISE_NAME_TAKEN)
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
        raise ApiError(ErrorCode.CATALOG_EXERCISE_NOT_FOUND)
    existing = find_own_copy(session, current_user, item.id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing
    exercise = Exercise(
        user_id=current_user.id,
        name=item.name_ro
        if language_for(data.language, current_user) == "ro" and item.name_ro
        else item.name,
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
        raise ApiError(ErrorCode.EXERCISE_NAME_TAKEN) from None
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
    commit_or_conflict(session, ErrorCode.EXERCISE_NAME_TAKEN)
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
    commit_or_conflict(session, ErrorCode.EXERCISE_IN_USE)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# History, for the gym screen: what the user did last time, and their best

BeforeWorkout = Annotated[int | None, Query(ge=1, le=MAX_DB_ID)]


def earlier_than(session: Session, user: User, workout_id: int | None) -> list[Any]:
    """Conditions for workouts that come before `workout_id` (by day, then
    by id for two on one day); none without it. 404 for a workout that is
    not the user's."""
    if workout_id is None:
        return []
    workout = session.get(Workout, workout_id)
    if workout is None or workout.user_id != user.id:
        raise ApiError(ErrorCode.WORKOUT_NOT_FOUND)
    return [
        or_(
            Workout.performed_on < workout.performed_on,
            and_(
                Workout.performed_on == workout.performed_on,
                Workout.id < workout.id,
            ),
        )
    ]


@router.get("/{exercise_id}/last", response_model=LastSession | None)
def last_session(
    exercise_id: IdPath,
    current_user: CurrentUser,
    session: SessionDep,
    before_workout: BeforeWorkout = None,
) -> LastSession | None:
    """The exercise's sets in the user's latest workout with it, or null
    if they never did it. With before_workout, the latest one before that
    workout, so editing a workout shows the session before it."""
    exercise = get_own_exercise(session, current_user, exercise_id)
    latest = session.execute(
        select(Workout.id, Workout.performed_on)
        .join(WorkoutExercise, WorkoutExercise.workout_id == Workout.id)
        .where(
            Workout.user_id == current_user.id,
            WorkoutExercise.exercise_id == exercise.id,
            *earlier_than(session, current_user, before_workout),
        )
        .order_by(Workout.performed_on.desc(), Workout.id.desc())
        .limit(1)
    ).first()
    if latest is None:
        return None
    sets = session.execute(
        select(WorkoutSet.reps, WorkoutSet.weight_kg)
        .join(WorkoutExercise, WorkoutSet.workout_exercise_id == WorkoutExercise.id)
        .where(
            WorkoutExercise.workout_id == latest.id,
            WorkoutExercise.exercise_id == exercise.id,
        )
        .order_by(WorkoutExercise.id, WorkoutSet.id)
    )
    return LastSession(
        workout_id=latest.id,
        performed_on=latest.performed_on,
        sets=[WorkoutSetResponse(reps=s.reps, weight_kg=s.weight_kg) for s in sets],
    )


@router.get("/{exercise_id}/best", response_model=BestSet | None)
def best_set(
    exercise_id: IdPath,
    current_user: CurrentUser,
    session: SessionDep,
    before_workout: BeforeWorkout = None,
) -> BestSet | None:
    """The user's best set of the exercise, or null if they never did it:
    the heaviest, and of those the most reps (bodyweight sets, at 0 kg,
    compare by reps). A tie goes to the first time it was done. With
    before_workout, only sets from workouts before that one."""
    exercise = get_own_exercise(session, current_user, exercise_id)
    best = session.execute(
        select(
            WorkoutSet.reps,
            WorkoutSet.weight_kg,
            Workout.performed_on,
            Workout.id.label("workout_id"),
        )
        .join(WorkoutExercise, WorkoutSet.workout_exercise_id == WorkoutExercise.id)
        .join(Workout, WorkoutExercise.workout_id == Workout.id)
        .where(
            Workout.user_id == current_user.id,
            WorkoutExercise.exercise_id == exercise.id,
            *earlier_than(session, current_user, before_workout),
        )
        .order_by(
            WorkoutSet.weight_kg.desc(),
            WorkoutSet.reps.desc(),
            Workout.performed_on,
            Workout.id,
        )
        .limit(1)
    ).first()
    if best is None:
        return None
    return BestSet(
        reps=best.reps,
        weight_kg=best.weight_kg,
        performed_on=best.performed_on,
        workout_id=best.workout_id,
    )
