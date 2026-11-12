from fastapi import APIRouter, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentUser, SessionDep
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
    ProgramDayResponse,
    ProgramExerciseResponse,
    ProgramIn,
    ProgramResponse,
    ProgramSummary,
    WorkoutResponse,
    WorkoutStartIn,
)
from app.workouts import LimitQuery, OffsetQuery, not_found
from app.workouts import to_response as workout_response

router = APIRouter(prefix="/programs", tags=["programs"])

CONFLICT = (
    "A program with this name already exists, or two of its days have the same position"
)


def check_own(program: Program | None, user: User) -> Program:
    """Reject a missing program, and another user's, with the same 404.

    Another user's program gets 404, not 403 (see get_own_food).
    """
    if program is None or program.user_id != user.id:
        raise not_found("Program not found")
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


def build_days(session: Session, user: User, data: ProgramIn) -> list[ProgramDay]:
    """The program's days and planned exercises as rows, checking every exercise.

    All exercises are loaded in one query; any that is missing or another
    user's makes the whole request a 404, as in a workout. Days are written
    in position order and exercises in the order sent, so what POST returns
    is what GET returns.
    """
    ids = {item.exercise_id for day in data.days for item in day.exercises}
    query = select(Exercise).where(Exercise.id.in_(ids), Exercise.user_id == user.id)
    own = {exercise.id: exercise for exercise in session.scalars(query)}
    if len(own) != len(ids):
        raise not_found("Exercise not found")
    return [
        ProgramDay(
            position=day.position,
            name=day.name,
            exercises=[
                ProgramExercise(
                    exercise=own[item.exercise_id],
                    sets=item.sets,
                    reps=item.reps,
                    weight_kg=item.weight_kg,
                )
                for item in day.exercises
            ],
        )
        for day in sorted(data.days, key=lambda day: day.position)
    ]


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
            for day in program.days
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
    commit_or_conflict(session, CONFLICT)
    # The rows just written, still in the session (expire_on_commit=False)
    return to_response(program)


@router.put("/{program_id}", response_model=ProgramResponse)
def replace_program(
    program_id: IdPath, data: ProgramIn, current_user: CurrentUser, session: SessionDep
) -> ProgramResponse:
    """Replace one of the current user's programs: its name and all its days,
    in one transaction. The days are new rows with new ids; workouts already
    started from the old days are copies and stay as they are.
    """
    program = get_own_program(session, current_user, program_id)
    # Every exercise is checked before anything changes
    days = build_days(session, current_user, data)
    # The old days go first, so the new ones can take the same positions
    # (unique per program) without the database seeing both at once. The
    # name changes after this flush, so a taken name fails at the commit,
    # where commit_or_conflict turns it into a 409 and rolls it all back.
    program.days = []
    session.flush()
    program.name = data.name
    program.days = days
    commit_or_conflict(session, CONFLICT)
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

    The workout is an ordinary one, edited with PUT /workouts/{id}: a copy,
    with no link back to the day, so changing or deleting the program never
    touches it, and the previous version of the app reads it too.
    """
    program = get_own_program(session, current_user, program_id)
    # A day of another program, even one of the user's own, is a 404 as well
    day = next((day for day in program.days if day.id == day_id), None)
    if day is None:
        raise not_found("Program day not found")
    workout = Workout(
        user_id=current_user.id,
        performed_on=data.performed_on,
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
