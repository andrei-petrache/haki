from typing import Any

import pytest
from fastapi.testclient import TestClient


def put_settings(
    client: TestClient, headers: dict[str, str], body: dict[str, Any]
) -> Any:
    return client.put("/auth/me", json=body, headers=headers)


def test_new_users_follow_the_browser(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    me = client.get("/auth/me", headers=auth_headers).json()

    assert me["language"] is None


@pytest.mark.parametrize("language", ["en", "ro"])
def test_set_language_returns_the_user(
    client: TestClient, auth_headers: dict[str, str], language: str
) -> None:
    response = put_settings(client, auth_headers, {"language": language})

    assert response.status_code == 200
    assert response.json()["language"] == language
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["language"] == language


def test_null_language_follows_the_browser_again(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    put_settings(client, auth_headers, {"language": "ro"})

    response = put_settings(client, auth_headers, {"language": None})

    assert response.json()["language"] is None


def test_language_leaves_the_calorie_target(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.put(
        "/auth/me/target", json={"daily_calorie_target": 2200}, headers=auth_headers
    )

    response = put_settings(client, auth_headers, {"language": "ro"})

    assert response.json()["daily_calorie_target"] == 2200


def test_language_is_per_user(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    put_settings(client, auth_headers, {"language": "ro"})

    other = client.get("/auth/me", headers=other_auth_headers).json()

    assert other["language"] is None


@pytest.mark.parametrize("body", [{"language": "de"}, {"language": "RO"}, {}])
def test_settings_reject_unknown_or_missing_language(
    client: TestClient, auth_headers: dict[str, str], body: dict[str, Any]
) -> None:
    put_settings(client, auth_headers, {"language": "ro"})

    response = put_settings(client, auth_headers, body)

    assert response.status_code == 422
    assert client.get("/auth/me", headers=auth_headers).json()["language"] == "ro"


def test_settings_require_login(client: TestClient) -> None:
    assert client.put("/auth/me", json={"language": "ro"}).status_code == 401
