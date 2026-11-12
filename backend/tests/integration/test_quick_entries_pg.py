"""Quick entries on the schema the migrations create (quick_entries)."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import QuickEntry, User
from tests.conftest import register_and_login

pytestmark = pytest.mark.integration

MakeUser = Callable[[str], User]


def add_quick(db: Session, user: User, **overrides: Any) -> QuickEntry:
    entry = QuickEntry(
        user_id=user.id,
        **{
            "eaten_on": date(2026, 11, 12),
            "meal_type": "lunch",
            "name": "Quick add",
            "calories": 450,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            **overrides,
        },
    )
    db.add(entry)
    db.flush()
    return entry


@pytest.mark.parametrize(
    "overrides",
    [{"calories": -1}, {"protein": -1}, {"carbs": -1}, {"fat": -1}, {"meal_type": "x"}],
)
def test_the_database_refuses_bad_quick_entries(
    db: Session, make_user: MakeUser, overrides: dict[str, Any]
) -> None:
    user = make_user("quick-bad@example.com")

    with db.begin_nested(), pytest.raises(IntegrityError):
        add_quick(db, user, **overrides)


def test_deleting_a_user_deletes_their_quick_entries(
    db: Session, make_user: MakeUser
) -> None:
    user = make_user("quick-gone@example.com")
    add_quick(db, user)

    db.execute(delete(User).where(User.id == user.id))

    count = db.scalar(select(func.count()).select_from(QuickEntry))
    assert count == 0


def test_quick_add_counts_in_the_summary_on_postgresql(
    db: Session, pg_client: TestClient
) -> None:
    headers = register_and_login(pg_client, "quick@example.com")
    body = {"eaten_on": "2026-11-12", "meal_type": "snack", "calories": 120.5}

    created = pg_client.post("/entries/quick", json=body, headers=headers)
    totals = pg_client.get("/summary", params={"date": "2026-11-12"}, headers=headers)

    assert created.status_code == 201
    assert totals.json()["meals"]["snack"]["calories"] == 120.5
