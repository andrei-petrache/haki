"""Consent and the erasure log on PostgreSQL (app/consent.py, app/erasures.py)."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app import erasures
from app.body import server_today
from app.config import settings
from app.consent import CURRENT_VERSIONS
from app.db import get_session
from app.main import app
from app.models import BodyWeight, Erasure, User
from tests.conftest import register_and_login
from tests.test_delete_account import PASSWORD

pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning"),
]

RACE_EMAIL = "consent-race@example.com"
PATH = "/auth/me/consents/health_data"
CONSENT = {"version": CURRENT_VERSIONS["health_data"], "locale": "en"}


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "body_weight_enabled", True)


@pytest.fixture
def committing_client(pg_engine: Engine) -> Iterator[TestClient]:
    """A session per request that commits, as in production; the user is
    deleted afterwards, and the erasure rows of the test with them."""
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
            ids = select(User.id).where(User.email == RACE_EMAIL).scalar_subquery()
            session.execute(delete(Erasure).where(Erasure.user_id == ids))
            session.execute(delete(User).where(User.email == RACE_EMAIL))


def after(barrier: Barrier, send: Callable[..., Any], *args: Any, **kwargs: Any) -> int:
    barrier.wait()
    return send(*args, **kwargs).status_code


def test_a_weigh_in_racing_a_withdrawal_never_outlives_it(
    committing_client: TestClient, pg_engine: Engine
) -> None:
    client = committing_client
    headers = register_and_login(client, RACE_EMAIL)
    day = str(server_today())
    weighed: list[int] = []

    for round_ in range(20):
        assert client.put(PATH, json=CONSENT, headers=headers).status_code == 200
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            weigh = pool.submit(
                after,
                barrier,
                client.put,
                f"/weights/{day}",
                json={"weight_kg": 80 + round_ / 10},
                headers=headers,
            )
            withdraw = pool.submit(after, barrier, client.delete, PATH, headers=headers)
            weighed.append(weigh.result())
            assert withdraw.result() == 204

        # Whichever came first, no weigh-in survives the withdrawal
        with Session(pg_engine) as session:
            left = session.scalar(
                select(func.count())
                .select_from(BodyWeight)
                .join(User, User.id == BodyWeight.user_id)
                .where(User.email == RACE_EMAIL)
            )
        assert left == 0, f"round {round_}: a weigh-in outlived the withdrawal"

    assert set(weighed) <= {200, 201, 403}, weighed


def test_the_log_is_applied_again_after_a_restore_on_postgresql(
    db: Session, pg_client: TestClient
) -> None:
    headers = register_and_login(pg_client, "restored@example.com")
    user = pg_client.get("/auth/me", headers=headers).json()
    created = db.scalar(select(User.created_at).where(User.id == user["id"]))
    pg_client.request(
        "DELETE", "/auth/me", json={"password": PASSWORD}, headers=headers
    )
    log = erasures.read_log(db)
    # The older dump still has the account
    db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, created_at) "
            "VALUES (:id, :email, 'from-the-dump', :created)"
        ),
        {"id": user["id"], "email": user["email"], "created": created},
    )

    counts = erasures.reapply(db, log)

    assert counts.accounts == 1
    assert db.get(User, user["id"]) is None
