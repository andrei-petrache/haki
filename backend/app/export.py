"""Data export (GDPR Art. 15 and 20): everything stored about the user, as JSON.

POST /auth/me/export {password} answers a JSON file, generated on the fly
and streamed: nothing is written anywhere, nothing is cached. Every user
table is in it (tests/test_export.py fails for a table that is not), each
row with its columns as stored, except the password hash and its stamp.

All tables are read in one REPEATABLE READ transaction on PostgreSQL, so
the export is one consistent moment: an entry added meanwhile never points
at a food the export lacks. The last key written is "complete": true; a
file without it was cut off by an error and must not be trusted.
"""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine, Select, Table, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep, wrong_password
from app.models import Base, Program, ProgramDay, User, Workout, WorkoutExercise
from app.schemas import AccountDeleteIn
from app.security import verify_password

FORMAT = "haki-export"
VERSION = 1
# Never exported: the password's hash, and the stamp that signs tokens
SECRET_COLUMNS = {"users": {"password_hash", "password_changed_at"}}
# Rows are fetched in batches of this many, so memory stays flat
BATCH = 500

router = APIRouter(prefix="/auth/me", tags=["auth"])


def user_tables() -> list[Table]:
    """Every table that can hold a user's data: all but the shared catalog."""
    return [
        table
        for table in Base.metadata.sorted_tables
        if not table.name.startswith("catalog_")
    ]


def rows_of(table: Table, user_id: int) -> Select[Any]:
    """The user's rows of `table`, oldest first. A table this does not know
    how to tie to a user fails, so a new table is never left out silently."""
    columns = [c for c in table.c if c.name not in SECRET_COLUMNS.get(table.name, ())]
    query = select(*columns).select_from(table).order_by(table.c.id)
    workouts, moves = Workout.__table__, WorkoutExercise.__table__
    programs, days = Program.__table__, ProgramDay.__table__
    if table.name == "users":
        return query.where(table.c.id == user_id)
    if "user_id" in table.c:
        return query.where(table.c.user_id == user_id)
    # The tables below a workout or a program belong to its owner
    if table.name == "workout_exercises":
        return query.join(workouts, table.c.workout_id == workouts.c.id).where(
            workouts.c.user_id == user_id
        )
    if table.name == "workout_sets":
        return (
            query.join(moves, table.c.workout_exercise_id == moves.c.id)
            .join(workouts, moves.c.workout_id == workouts.c.id)
            .where(workouts.c.user_id == user_id)
        )
    if table.name == "program_days":
        return query.join(programs, table.c.program_id == programs.c.id).where(
            programs.c.user_id == user_id
        )
    if table.name == "program_exercises":
        return (
            query.join(days, table.c.program_day_id == days.c.id)
            .join(programs, days.c.program_id == programs.c.id)
            .where(programs.c.user_id == user_id)
        )
    raise LookupError(f"the export does not know whose rows {table.name} holds")


def to_json(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"cannot export a {type(value).__name__}")


def dumps(value: Any) -> str:
    return json.dumps(value, default=to_json, ensure_ascii=False)


def export_chunks(session: Session, user_id: int) -> Iterator[str]:
    """The export as pieces of one JSON object, table by table."""
    yield "{" + f'"format": {dumps(FORMAT)}, "version": {VERSION}, '
    yield f'"exported_at": {dumps(datetime.now(UTC))}'
    for table in user_tables():
        yield f", {dumps(table.name)}: ["
        result = session.execute(
            rows_of(table, user_id).execution_options(yield_per=BATCH)
        )
        for index, row in enumerate(result.mappings()):
            yield ("," if index else "") + dumps(dict(row))
        yield "]"
    # Written last: a file without it was cut off
    yield ', "complete": true}'


def consistent_export(bind: Any, user_id: int) -> Iterator[str]:
    """export_chunks in a session of its own, one REPEATABLE READ read-only
    transaction on PostgreSQL. Its own session, because the request's is
    closed by the time a streamed body is sent."""
    with Session(bind=bind) as session:
        if isinstance(bind, Engine) and bind.dialect.name == "postgresql":
            session.connection(
                execution_options={
                    "isolation_level": "REPEATABLE READ",
                    "postgresql_readonly": True,
                }
            )
        yield from export_chunks(session, user_id)


@router.post("/export", status_code=status.HTTP_200_OK)
def export_my_data(
    data: AccountDeleteIn, current_user: CurrentUser, session: SessionDep
) -> StreamingResponse:
    """Download everything stored about the current user, as one JSON file.

    The current password is asked for, so a stolen session alone cannot
    take everything at once; 403 if it is wrong.
    """
    if not verify_password(data.password, current_user.password_hash):
        raise wrong_password()
    user: User = current_user
    name = f"haki-export-{datetime.now(UTC).date().isoformat()}.json"
    return StreamingResponse(
        consistent_export(session.get_bind(), user.id),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )
