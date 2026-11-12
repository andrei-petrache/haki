from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.security import create_access_token
from tests.conftest import register_and_login

EMAIL = "andrei@example.com"
# The password register_and_login signs up with
OLD = "correct-horse-battery"
NEW = "new-staple-battery-horse"


def login(client: TestClient, password: str, email: str = EMAIL) -> Any:
    return client.post("/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def change(
    client: TestClient, headers: dict[str, str], current: str = OLD, new: str = NEW
) -> Any:
    body = {"current_password": current, "new_password": new}
    return client.put("/auth/me/password", json=body, headers=headers)


def me_status(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/auth/me", headers=headers).status_code


def test_change_password_replaces_it(client: TestClient) -> None:
    headers = register_and_login(client, EMAIL)

    response = change(client, headers)

    assert response.status_code == 200
    assert login(client, NEW).status_code == 200
    assert login(client, OLD).status_code == 401


def test_change_password_returns_a_fresh_token_that_works(
    client: TestClient,
) -> None:
    headers = register_and_login(client, EMAIL)

    body = change(client, headers).json()

    assert body["token_type"] == "bearer"
    assert me_status(client, bearer(body["access_token"])) == 200


def test_change_password_refuses_every_older_token(client: TestClient) -> None:
    headers = register_and_login(client, EMAIL)
    # Another device, signed in before the change
    other_device = bearer(login(client, OLD).json()["access_token"])

    change(client, headers)

    assert me_status(client, headers) == 401
    assert me_status(client, other_device) == 401


def test_a_login_after_the_change_is_accepted(client: TestClient) -> None:
    headers = register_and_login(client, EMAIL)
    change(client, headers)

    token = login(client, NEW).json()["access_token"]

    assert me_status(client, bearer(token)) == 200


def test_a_second_change_refuses_the_first_changes_token(client: TestClient) -> None:
    headers = register_and_login(client, EMAIL)
    first = bearer(change(client, headers).json()["access_token"])

    second = change(client, first, NEW, "third-battery-horse-staple")

    assert second.status_code == 200
    assert me_status(client, first) == 401
    assert me_status(client, bearer(second.json()["access_token"])) == 200


def test_users_who_never_changed_their_password_are_unaffected(
    client: TestClient,
) -> None:
    headers = register_and_login(client, EMAIL)
    others = register_and_login(client, "mallory@example.com")

    change(client, headers)

    assert me_status(client, others) == 200
    assert login(client, OLD, "mallory@example.com").status_code == 200


def test_a_token_from_before_password_versions_still_works(client: TestClient) -> None:
    # Tokens issued before this change carry no "pwc" claim; they stay valid
    # for a user who never changed the password
    headers = register_and_login(client, EMAIL)
    user_id = client.get("/auth/me", headers=headers).json()["id"]

    assert me_status(client, bearer(create_access_token(user_id))) == 200


def test_a_token_with_a_wrong_password_stamp_is_refused(client: TestClient) -> None:
    headers = register_and_login(client, EMAIL)
    user_id = client.get("/auth/me", headers=headers).json()["id"]

    forged = create_access_token(user_id, stamp=123)

    assert me_status(client, bearer(forged)) == 401


def test_wrong_current_password_is_403_and_changes_nothing(
    client: TestClient,
) -> None:
    headers = register_and_login(client, EMAIL)

    response = change(client, headers, current="not-my-password")

    # Not 401: the token is valid, and clients sign out on a 401
    assert response.status_code == 403
    assert me_status(client, headers) == 200
    assert login(client, OLD).status_code == 200
    assert login(client, NEW).status_code == 401


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (OLD, "short"),
        (OLD, "x" * 129),
        ("x" * 129, NEW),
    ],
)
def test_change_password_rejects_invalid_lengths(
    client: TestClient, current: str, new: str
) -> None:
    headers = register_and_login(client, EMAIL)

    response = change(client, headers, current, new)

    assert response.status_code == 422
    assert me_status(client, headers) == 200
    assert login(client, OLD).status_code == 200


def test_change_password_requires_login(client: TestClient) -> None:
    body = {"current_password": OLD, "new_password": NEW}

    response = client.put("/auth/me/password", json=body)

    assert response.status_code == 401
