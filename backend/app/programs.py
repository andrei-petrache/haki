from uuid import uuid4

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentUser, SessionDep
from app.errors import ApiError, ErrorCode
from app.foods import commit_or_conflict
from app.models import (
    Exercise,
    Program,
    ProgramDay,
    ProgramExercise,
    User,
    Workout,
    WorkoutExercise,
    WorkoutSet,
)
from app.schemas import (
    IdPath,
    ProgramDayIn,
    ProgramDayResponse,
    ProgramExerciseResponse,
    ProgramIn,
    ProgramResponse,
    ProgramSummary,
    WorkoutResponse,
    WorkoutStartIn,
)
from app.workouts import LimitQuery, OffsetQuery
from app.workouts import to_response as workout_response

router = APIRouter(prefix="/programs", tags=["programs"])


def check_own(program: Program | None, user: User) -> Program:
    """Reject a missing program, and another user's, with the same 404.

    Another user's program gets 404, not 403 (see get_own_food).
    """
    if program is None or program.user_id != user.id:
        raise ApiError(ErrorCode.PROGRAM_NOT_FOUND)
    return program


def get_own_program(session: Session, user: User, program_id: int) -> Program:
    """Load one of the user's programs with everything in it, or reject with 404.

    The days, their exercises and the exercise names come in a fixed number
    of queries, however many there are (no query per day or exercise).
    """
    query = (
        select(Program)
        .options(
            selectinload(Program.days)
            .selectinload(ProgramDay.exercises)
            .joinedload(ProgramExercise.exercise)
        )
        .where(Program.id == program_id)
    )
    return check_own(session.scalar(query), user)


def own_exercises(session: Session, user: User, data: ProgramIn) -> dict[int, Exercise]:
    """Every exercise the program plans, by id, checked to be the user's.

    All are loaded in one query; any that is missing or another user's
    makes the whole request a 404, as in a workout.
    """
    ids = {item.exercise_id for day in data.days for item in day.exercises}
    query = select(Exercise).where(Exercise.id.in_(ids), Exercise.user_id == user.id)
    own = {exercise.id: exercise for exercise in session.scalars(query)}
    if len(own) != len(ids):
        raise ApiError(ErrorCode.EXERCISE_NOT_FOUND)
    return own


def planned(day: ProgramDayIn, own: dict[int, Exercise]) -> list[ProgramExercise]:
    """A day's planned exercises as rows, in the order sent."""
    return [
        ProgramExercise(
            exercise=own[item.exercise_id],
            sets=item.sets,
            reps=item.reps,
            weight_kg=item.weight_kg,
        )
        for item in day.exercises
    ]


def build_days(session: Session, user: User, data: ProgramIn) -> list[ProgramDay]:
    """The program's days and planned exercises as new rows, in position
    order, so what POST returns is what GET returns."""
    own = own_exercises(session, user, data)
    return [
        ProgramDay(position=day.position, name=day.name, exercises=planned(day, own))
        for day in sorted(data.days, key=lambda day: day.position)
    ]


def move_days(session: Session, program: Program, positions: dict[int, int]) -> None:
    """Move kept days to new positions without two days sharing one.

    Positions are unique per program and checked row by row, and 1 to 7 is
    all there is: a swap, or a full week reversed, has no free position to
    pass through. So the moving days step out into a scratch program of the
    same user first (each keeps its old position there, which are distinct),
    then come back at their new ones. Their ids never change, so workouts
    started from them stay linked. The scratch program lives only inside
    this transaction: nobody else ever sees it.
    """
    moving = [day for day in program.days if day.position != positions[day.id]]
    if not moving:
        return
    scratch = Program(user_id=program.user_id, name=f"~moving {uuid4().hex}")
    session.add(scratch)
    for day in moving:
        day.program = scratch
    session.flush()
    for day in moving:
        day.position = positions[day.id]
        day.program = program
    session.flush()
    session.delete(scratch)


def update_days(
    session: Session, program: Program, data: ProgramIn, own: dict[int, Exercise]
) -> None:
    """Make the program's days what `data` says, keeping the days sent by id.

    A day sent with its id is changed in place; a day without one is new; a
    day left out is deleted, and workouts started from it only lose the link
    (ON DELETE SET NULL). A body without any ids replaces every day.
    """
    kept = {day.id: day for day in data.days if day.id is not None}
    # The left-out days go first, so their positions are free for the others
    for day in [day for day in program.days if day.id not in kept]:
        program.days.remove(day)
    session.flush()
    move_days(session, program, {key: day.position for key, day in kept.items()})
    for day in program.days:
        day.name = kept[day.id].name
        day.exercises = planned(kept[day.id], own)
    for item in data.days:
        if item.id is None:
            program.days.append(
                ProgramDay(
                    position=item.position, name=item.name, exercises=planned(item, own)
                )
            )


def to_response(program: Program) -> ProgramResponse:
    return ProgramResponse(
        id=program.id,
        name=program.name,
        days=[
            ProgramDayResponse(
                id=day.id,
                position=day.position,
                name=day.name,
                exercises=[
                    ProgramExerciseResponse(
                        exercise_id=item.exercise_id,
                        exercise_name=item.exercise.name,
                        sets=item.sets,
                        reps=item.reps,
                        weight_kg=item.weight_kg,
                    )
                    for item in day.exercises
                ],
            )
            # In position order also right after a PUT moved them in memory
            for day in sorted(program.days, key=lambda day: day.position)
        ],
    )


@router.get("", response_model=list[ProgramSummary])
def list_programs(
    current_user: CurrentUser,
    session: SessionDep,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> list[ProgramSummary]:
    """Return the current user's programs by name, each with its number of days.

    One query whatever the number of programs: the count is a subquery.
    """
    day_count = (
        select(func.count(ProgramDay.id))
        .where(ProgramDay.program_id == Program.id)
        .scalar_subquery()
    )
    query = (
        select(Program, day_count)
        .where(Program.user_id == current_user.id)
        .order_by(func.lower(Program.name), Program.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        ProgramSummary(id=program.id, name=program.name, day_count=days)
        for program, days in session.execute(query)
    ]


@router.get("/{program_id}", response_model=ProgramResponse)
def read_program(
    program_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> ProgramResponse:
    """Return one of the current user's programs with its days and exercises."""
    return to_response(get_own_program(session, current_user, program_id))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProgramResponse)
def create_program(
    data: ProgramIn, current_user: CurrentUser, session: SessionDep
) -> ProgramResponse:
    """Create a whole program in one transaction: all of it or nothing."""
    program = Program(
        user_id=current_user.id,
        name=data.name,
        days=build_days(session, current_user, data),
    )
    session.add(program)
    # The name is unique per user ignoring case, the position per program
    commit_or_conflict(session, ErrorCode.PROGRAM_CONFLICT)
    # The rows just written, still in the session (expire_on_commit=False)
    return to_response(program)


@router.put("/{program_id}", response_model=ProgramResponse)
def replace_program(
    program_id: IdPath, data: ProgramIn, current_user: CurrentUser, session: SessionDep
) -> ProgramResponse:
    """Replace one of the current user's programs: its name and all its days,
    in one transaction: all of it or nothing.

    Days sent with their id are kept and changed in place (see update_days),
    so workouts started from them stay linked; the others are new rows.
    Workouts are copies of the plan either way and never change.
    """
    program = get_own_program(session, current_user, program_id)
    # Everything is checked before anything changes: another program's day
    # (even the user's own) is a 404, as in start_workout
    current = {day.id for day in program.days}
    if any(day.id is not None and day.id not in current for day in data.days):
        raise ApiError(ErrorCode.PROGRAM_DAY_NOT_FOUND)
    own = own_exercises(session, current_user, data)
    # A taken name or two days on one position can fail at any flush, not
    # only at the commit: either way a 409, and nothing is kept
    try:
        update_days(session, program, data, own)
        program.name = data.name
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(ErrorCode.PROGRAM_CONFLICT) from None
    return to_response(program)


@router.delete("/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_program(
    program_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Delete one of the current user's programs; the exercises stay in the catalog."""
    # Nothing in it needs loading: the database deletes it (ON DELETE CASCADE)
    program = check_own(session.get(Program, program_id), current_user)
    session.delete(program)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{program_id}/days/{day_id}/workouts",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkoutResponse,
)
def start_workout(
    program_id: IdPath,
    day_id: IdPath,
    data: WorkoutStartIn,
    current_user: CurrentUser,
    session: SessionDep,
) -> WorkoutResponse:
    """Start a workout from one day of a program, with its planned sets.

    The workout is an ordinary one, edited with PUT /workouts/{id}: a copy
    of the plan, so changing or deleting the program never changes what was
    done, and the previous version of the app reads it too. It remembers the
    day in program_day_id, for the plan next to it; deleting or replacing
    the day only clears that link (ON DELETE SET NULL).
    """
    program = get_own_program(session, current_user, program_id)
    # A day of another program, even one of the user's own, is a 404 as well
    day = next((day for day in program.days if day.id == day_id), None)
    if day is None:
        raise ApiError(ErrorCode.PROGRAM_DAY_NOT_FOUND)
    workout = Workout(
        user_id=current_user.id,
        performed_on=data.performed_on,
        program_day_id=day.id,
        # In the day's order; each planned set becomes one logged set
        exercises=[
            WorkoutExercise(
                exercise=item.exercise,
                sets=[
                    WorkoutSet(reps=item.reps, weight_kg=item.weight_kg)
                    for _ in range(item.sets)
                ],
            )
            for item in day.exercises
        ],
    )
    session.add(workout)
    session.commit()
    return workout_response(workout)
