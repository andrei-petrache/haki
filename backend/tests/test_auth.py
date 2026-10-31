from fastapi.testclient import TestClient
from httpx2 import Response

EMAIL = "andrei@example.com"
PASSWORD = "correct-horse-battery"


def signup(
    client: TestClient, email: str = EMAIL, password: str = PASSWORD
) -> Response:
    return client.post("/auth/signup", json={"email": email, "password": password})


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> Response:
    return client.post("/auth/login", json={"email": email, "password": password})


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_signup_creates_user(client: TestClient) -> None:
    response = signup(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert "id" in body
    assert "password_hash" not in body


def test_signup_rejects_duplicate_email_case_insensitively(client: TestClient) -> None:
    signup(client)

    response = signup(client, email="Andrei@Example.com")

    assert response.status_code == 409


def test_signup_rejects_short_password(client: TestClient) -> None:
    response = signup(client, password="short")

    assert response.status_code == 422


def test_signup_rejects_invalid_email(client: TestClient) -> None:
    response = signup(client, email="not-an-email")

    assert response.status_code == 422


def test_login_returns_bearer_token(client: TestClient) -> None:
    signup(client)

    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_wrong_password(client: TestClient) -> None:
    signup(client)

    response = login(client, password="wrong-password")

    assert response.status_code == 401


def test_login_gives_same_error_for_unknown_email(client: TestClient) -> None:
    signup(client)

    wrong_password = login(client, password="wrong-password")
    unknown_email = login(client, email="nobody@example.com")

    assert unknown_email.status_code == 401
    assert unknown_email.json() == wrong_password.json()


def test_me_returns_current_user(client: TestClient) -> None:
    signup(client)
    token = login(client).json()["access_token"]

    response = client.get("/auth/me", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/auth/me", headers=auth_header("not-a-real-token"))

    assert response.status_code == 401
