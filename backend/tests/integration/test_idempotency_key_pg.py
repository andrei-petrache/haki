"""Idempotency-Key under two requests at once, on PostgreSQL."""

import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session
from app.main import app
from app.models import QuickEntry, User
from tests.conftest import register_and_login

pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning"),
]

EMAIL = "idempotency-race@example.com"
QUICK = {"eaten_on": "2026-11-14", "meal_type": "snack", "calories": 200}


@pytest.fixture
def committing_client(pg_engine: Engine) -> Iterator[TestClient]:
    """A session per request that commits, as in production; the user is
    deleted afterwards, and their entries with them."""
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


def after(barrier: Barrier, send: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    barrier.wait()
    return send(*args, **kwargs)


def test_the_same_key_twice_at_once_logs_one_entry(
    committing_client: TestClient, pg_engine: Engine
) -> None:
    client = committing_client
    headers = register_and_login(client, EMAIL)

    for _ in range(20):
        key = {"Idempotency-Key": str(uuid.uuid4())}
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            sent = [
                pool.submit(
                    after,
                    barrier,
                    client.post,
                    "/entries/quick",
                    json=QUICK,
                    headers=headers | key,
                )
                for _ in "ab"
            ]
            first, second = (future.result() for future in sent)

        assert sorted([first.status_code, second.status_code]) == [200, 201]
        assert first.json()["id"] == second.json()["id"]

    with Session(pg_engine) as session:
        entries = session.scalar(
            select(func.count())
            .select_from(QuickEntry)
            .join(User, User.id == QuickEntry.user_id)
            .where(User.email == EMAIL)
        )
    assert entries == 20
