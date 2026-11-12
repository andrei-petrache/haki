from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentUser, SessionDep
from app.errors import ApiError, ErrorCode
from app.models import Exercise, User, Workout, WorkoutExercise, WorkoutSet
from app.schemas import (
    MAX_DB_ID,
    IdPath,
    WorkoutExerciseResponse,
    WorkoutIn,
    WorkoutResponse,
    WorkoutSetResponse,
    WorkoutSummary,
)

router = APIRouter(prefix="/workouts", tags=["workouts"])

LimitQuery = Annotated[int, Query(ge=1, le=100)]
# Bounded so a huge offset is a 422, not a database error (a 500)
OffsetQuery = Annotated[int, Query(ge=0, le=MAX_DB_ID)]


def check_own(workout: Workout | None, user: User) -> Workout:
    """Reject a missing workout, and another user's, with the same 404.

    Another user's workout gets 404, not 403 (see get_own_food).
    """
    if workout is None or workout.user_id != user.id:
        raise ApiError(ErrorCode.WORKOUT_NOT_FOUND)
    return workout


def get_own_workout(session: Session, user: User, workout_id: int) -> Workout:
    """Load one of the user's workouts with everything in it, or reject with 404.

    The exercises, their names and their sets come in a fixed number of
    queries, however many there are (no query per exercise).
    """
    query = (
        select(Workout)
        .options(
            selectinload(Workout.exercises).joinedload(WorkoutExercise.exercise),
            selectinload(Workout.exercises).selectinload(WorkoutExercise.sets),
        )
        .where(Workout.id == workout_id)
    )
    return check_own(session.scalar(query), user)


def build_exercises(
    session: Session, user: User, data: WorkoutIn
) -> list[WorkoutExercise]:
    """The workout's exercises and sets as rows, checking every exercise is own.

    All exercises are loaded in one query; any that is missing or another
    user's makes the whole request a 404, as logging another user's food does.
    """
    ids = {item.exercise_id for item in data.exercises}
    query = select(Exercise).where(Exercise.id.in_(ids), Exercise.user_id == user.id)
    own = {exercise.id: exercise for exercise in session.scalars(query)}
    if len(own) != len(ids):
        raise ApiError(ErrorCode.EXERCISE_NOT_FOUND)
    return [
        WorkoutExercise(
            exercise=own[item.exercise_id],
            sets=[
                WorkoutSet(reps=set_in.reps, weight_kg=set_in.weight_kg)
                for set_in in item.sets
            ],
        )
        for item in data.exercises
    ]


def to_response(workout: Workout) -> WorkoutResponse:
    return WorkoutResponse(
        id=workout.id,
        performed_on=workout.performed_on,
        note=workout.note,
        program_day_id=workout.program_day_id,
        exercises=[
            WorkoutExerciseResponse(
                exercise_id=item.exercise_id,
                exercise_name=item.exercise.name,
                sets=[WorkoutSetResponse.model_validate(row) for row in item.sets],
            )
            for item in workout.exercises
        ],
    )


@router.get("", response_model=list[WorkoutSummary])
def list_workouts(
    current_user: CurrentUser,
    session: SessionDep,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> list[WorkoutSummary]:
    """Return the current user's workouts, newest first, with their counts."""
    exercise_count = (
        select(func.count(WorkoutExercise.id))
        .where(WorkoutExercise.workout_id == Workout.id)
        .scalar_subquery()
    )
    set_count = (
        select(func.count(WorkoutSet.id))
        .join(WorkoutExercise)
        .where(WorkoutExercise.workout_id == Workout.id)
        .scalar_subquery()
    )
    query = (
        select(Workout, exercise_count, set_count)
        .where(Workout.user_id == current_user.id)
        .order_by(Workout.performed_on.desc(), Workout.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        WorkoutSummary(
            id=workout.id,
            performed_on=workout.performed_on,
            note=workout.note,
            exercise_count=exercises,
            set_count=sets,
        )
        for workout, exercises, sets in session.execute(query)
    ]


@router.get("/{workout_id}", response_model=WorkoutResponse)
def read_workout(
    workout_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> WorkoutResponse:
    """Return one of the current user's workouts with its exercises and sets."""
    return to_response(get_own_workout(session, current_user, workout_id))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WorkoutResponse)
def create_workout(
    data: WorkoutIn, current_user: CurrentUser, session: SessionDep
) -> WorkoutResponse:
    """Record a whole workout in one transaction: all of it or nothing."""
    workout = Workout(
        user_id=current_user.id,
        performed_on=data.performed_on,
        note=data.note,
        exercises=build_exercises(session, current_user, data),
    )
    session.add(workout)
    session.commit()
    # The rows just written, still in the session (expire_on_commit=False)
    return to_response(workout)


@router.put("/{workout_id}", response_model=WorkoutResponse)
def replace_workout(
    workout_id: IdPath, data: WorkoutIn, current_user: CurrentUser, session: SessionDep
) -> WorkoutResponse:
    """Replace everything in one of the current user's workouts."""
    workout = get_own_workout(session, current_user, workout_id)
    workout.performed_on = data.performed_on
    workout.note = data.note
    # The old exercise rows are deleted (delete-orphan), and their sets with
    # them by the database (ON DELETE CASCADE)
    workout.exercises = build_exercises(session, current_user, data)
    session.commit()
    return to_response(workout)


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(
    workout_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's workouts, with its exercises and sets."""
    # Nothing in it needs loading: the database deletes it (ON DELETE CASCADE)
    workout = check_own(session.get(Workout, workout_id), current_user)
    session.delete(workout)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
