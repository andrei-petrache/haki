import pytest
from fastapi.testclient import TestClient

from tests.conftest import register_and_login

EMAIL = "andrei@example.com"
# The password register_and_login signs up with
OLD = "correct-horse-battery"
NEW = "new-staple-battery-horse"


def login(client: TestClient, password: str, email: str = EMAIL) -> int:
    response = client.post("/auth/login", json={"email": email, "password": password})
    return response.status_code


def change(client: TestClient, headers: dict[str, str], current: str, new: str) -> int:
    body = {"current_password": current, "new_password": new}
    return client.put("/auth/me/password", json=body, headers=headers).status_code


def test_change_password_replaces_it(client: TestClient) -> None:
    headers = register_and_login(client, EMAIL)

    status = change(client, headers, OLD, NEW)

    assert status == 204
    assert login(client, NEW) == 200
    assert login(client, OLD) == 401


def test_wrong_current_password_is_401_and_changes_nothing(
    client: TestClient,
) -> None:
    headers = register_and_login(client, EMAIL)

    status = change(client, headers, "not-my-password", NEW)

    assert status == 401
    assert login(client, OLD) == 200
    assert login(client, NEW) == 401


def test_tokens_from_before_the_change_stay_valid(client: TestClient) -> None:
    # Documented: tokens carry no password version yet
    headers = register_and_login(client, EMAIL)
    change(client, headers, OLD, NEW)

    assert client.get("/auth/me", headers=headers).status_code == 200


def test_change_password_touches_only_the_current_user(client: TestClient) -> None:
    headers = register_and_login(client, EMAIL)
    register_and_login(client, "mallory@example.com")

    change(client, headers, OLD, NEW)

    assert login(client, OLD, "mallory@example.com") == 200


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

    status = change(client, headers, current, new)

    assert status == 422
    assert login(client, OLD) == 200


def test_change_password_requires_login(client: TestClient) -> None:
    body = {"current_password": OLD, "new_password": NEW}

    response = client.put("/auth/me/password", json=body)

    assert response.status_code == 401
