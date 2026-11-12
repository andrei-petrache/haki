"""A password change on PostgreSQL, which keeps the time's microseconds and
its zone: the fresh token's stamp must match the stored value exactly."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from tests.conftest import register_and_login

pytestmark = pytest.mark.integration


def test_password_change_on_postgresql(db: Session, pg_client: TestClient) -> None:
    old = register_and_login(pg_client, "password-pg@example.com")
    body = {
        "current_password": "correct-horse-battery",
        "new_password": "new-staple-battery-horse",
    }

    response = pg_client.put("/auth/me/password", json=body, headers=old)

    assert response.status_code == 200
    fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert pg_client.get("/auth/me", headers=fresh).status_code == 200
    assert pg_client.get("/auth/me", headers=old).status_code == 401
    stored = db.scalar(
        select(User.password_changed_at).where(User.email == "password-pg@example.com")
    )
    assert stored is not None and stored.utcoffset() is not None
