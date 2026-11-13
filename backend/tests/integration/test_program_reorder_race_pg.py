"""Two reorders of one program at once, each committing on its own connection.

The other integration tests run inside one rolled-back transaction, which
cannot show two requests racing. This one commits for real, then deletes
the user, whose rows go with it (ON DELETE CASCADE): the database ends empty.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session
from app.main import app
from app.models import Program, User
from tests.conftest import register_and_login

pytestmark = [
    pytest.mark.integration,
    # A request working from rows another one already changed shows up as
    # "expected to delete N rows; 0 were matched": a lost update, so fail
    pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning"),
]

EMAIL = "reorder-race@example.com"


@pytest.fixture
def committing_client(pg_engine: Engine) -> Iterator[TestClient]:
    """The API with a session per request that commits, as in production."""
    sessions = sessionmaker(bind=pg_engine, expire_on_commit=False)

    def get_committing_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = get_committing_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        with sessions.begin() as session:
            session.execute(delete(User).where(User.email == EMAIL))


def test_two_reorders_at_once_never_fail_with_a_server_error(
    committing_client: TestClient, pg_engine: Engine
) -> None:
    client = committing_client
    headers = register_and_login(client, EMAIL)
    squat = client.post("/exercises", json={"name": "Squat"}, headers=headers)
    planned = {
        "exercise_id": squat.json()["id"],
        "sets": 3,
        "reps": 5,
        "weight_kg": 100,
    }
    week = {
        "name": "Week",
        "days": [
            {"position": p, "name": f"Day {p}", "exercises": [planned]}
            for p in range(1, 8)
        ],
    }
    plan = client.post("/programs", json=week, headers=headers).json()

    def reorder(shift: int) -> dict[str, Any]:
        return {
            "name": "Week",
            "days": [
                {
                    "id": d["id"],
                    "position": (d["position"] - 1 + shift) % 7 + 1,
                    "name": d["name"],
                    "exercises": [planned],
                }
                for d in plan["days"]
            ],
        }

    statuses: list[int] = []
    for _ in range(20):
        barrier = Barrier(2)

        def put(body: dict[str, Any], barrier: Barrier = barrier) -> int:
            barrier.wait()
            response = client.put(f"/programs/{plan['id']}", json=body, headers=headers)
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses += pool.map(put, [reorder(3), reorder(5)])

    assert set(statuses) <= {200, 409}, statuses
    assert 200 in statuses
    with Session(pg_engine) as session:
        left = session.scalar(
            select(func.count()).select_from(Program).where(Program.name.like("~%"))
        )
    assert left == 0
    # Whichever won, the program holds all seven days, one per position
    days = client.get(f"/programs/{plan['id']}", headers=headers).json()["days"]
    assert sorted(d["position"] for d in days) == list(range(1, 8))
    assert sorted(d["id"] for d in days) == sorted(d["id"] for d in plan["days"])
