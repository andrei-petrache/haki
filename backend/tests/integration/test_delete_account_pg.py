"""Deleting an account on PostgreSQL, where meal_entries.food_id is
ON DELETE RESTRICT, checked at once, and the exercises' references are
deferred to the commit: every table must end up empty."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import register_and_login
from tests.test_delete_account import fill_account, row_counts, user_tables

pytestmark = pytest.mark.integration


def test_delete_account_on_postgresql(db: Session, pg_client: TestClient) -> None:
    headers = register_and_login(pg_client, "delete-pg@example.com")
    fill_account(pg_client, headers)
    assert [name for name, n in row_counts(db).items() if n == 0] == []

    response = pg_client.request(
        "DELETE",
        "/auth/me",
        json={"password": "correct-horse-battery"},
        headers=headers,
    )
    # The deferred foreign keys are checked at COMMIT, which this rolled-back
    # test never reaches: check them now
    db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    assert response.status_code == 204
    assert row_counts(db) == {table.name: 0 for table in user_tables()}
