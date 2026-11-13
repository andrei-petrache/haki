"""Body weight and the adaptive target on the schema the migrations create."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.body import server_today
from app.config import settings
from app.consent import CURRENT_VERSIONS
from app.db import get_session
from app.main import app
from app.models import TdeeEstimate, User
from tests.conftest import register_and_login

pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning"),
]

TODAY = server_today()
RACE_EMAIL = "first-read-race@example.com"
CONSENT_PATH = "/auth/me/consents/health_data"
CONSENT = {"version": CURRENT_VERSIONS["health_data"], "locale": "en"}


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "body_weight_enabled", True)


def test_the_previous_versions_user_insert_still_works(
    db: Session, make_user: Callable[[str], User]
) -> None:
    # The previous version names only the columns it knows
    db.execute(
        text("INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'x')")
    )

    mode, goal = db.execute(
        text("SELECT target_mode, goal_kg_per_week FROM users WHERE email = :e"),
        {"e": "old@example.com"},
    ).one()
    assert (mode, goal) == ("manual", None)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE users SET target_mode = 'magic'",
        "UPDATE users SET goal_kg_per_week = -2",
        "INSERT INTO body_weights (user_id, measured_on, weight_kg) "
        "SELECT id, '2026-11-01', 5 FROM users",
        "INSERT INTO body_weights (user_id, measured_on, weight_kg) "
        "SELECT id, '1999-01-01', 80 FROM users",
        "INSERT INTO tdee_estimates (user_id, week_start, status, tdee_kcal, "
        "weigh_ins, logged_days, reasons) SELECT id, '2026-11-02', 'collecting', "
        "2000, 0, 0, '' FROM users",
    ],
)
def test_the_database_refuses_impossible_values(
    db: Session, make_user: Callable[[str], User], sql: str
) -> None:
    make_user("checks@example.com")

    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text(sql))


def test_weights_come_back_as_json_numbers_on_postgresql(
    db: Session, pg_client: TestClient
) -> None:
    headers = register_and_login(pg_client, "numbers@example.com")
    pg_client.put(CONSENT_PATH, json=CONSENT, headers=headers)

    put = pg_client.put(
        f"/weights/{TODAY}", json={"weight_kg": 72.456}, headers=headers
    )
    listed = pg_client.get("/weights", headers=headers).json()
    goal = {"target_mode": "adaptive", "goal_kg_per_week": -0.25}
    me = pg_client.put("/auth/me/goal", json=goal, headers=headers).json()

    assert put.json()["weight_kg"] == 72.46
    assert listed[0]["weight_kg"] == 72.46
    assert isinstance(listed[0]["weight_kg"], float)
    assert me["goal_kg_per_week"] == -0.25
    assert isinstance(me["goal_kg_per_week"], float)


@pytest.fixture
def committing_client(pg_engine: Engine) -> Iterator[TestClient]:
    """The API with a session per request that commits, as in production;
    the user is deleted afterwards, and everything of theirs with them."""
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
            session.execute(delete(User).where(User.email == RACE_EMAIL))


def test_two_first_reads_of_the_week_store_one_estimate(
    committing_client: TestClient, pg_engine: Engine
) -> None:
    client = committing_client
    headers = register_and_login(client, RACE_EMAIL)
    client.put(CONSENT_PATH, json=CONSENT, headers=headers)
    goal = {"target_mode": "adaptive", "goal_kg_per_week": None}
    client.put("/auth/me/goal", json=goal, headers=headers)
    barrier = Barrier(2)

    def read(_: int) -> Any:
        barrier.wait()
        return client.get(
            "/targets/current", params={"date": str(TODAY)}, headers=headers
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(read, range(2))

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json()
    with Session(pg_engine) as session:
        user_id = session.scalar(select(User.id).where(User.email == RACE_EMAIL))
        count = session.scalar(
            select(func.count())
            .select_from(TdeeEstimate)
            .where(TdeeEstimate.user_id == user_id)
        )
    assert count == 1
