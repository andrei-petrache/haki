"""Password reset by e-mail (app/password_reset.py, app/mail.py)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import mail, password_reset
from app.config import Settings, settings
from app.security import ACCESS, RESET, create_token, decode_reset_token
from tests.conftest import register_and_login

EMAIL = "reset@example.com"
# The password register_and_login signs up with
OLD_PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-brand-new-password"


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "password_reset_enabled", True)
    monkeypatch.setattr(settings, "public_base_url", "https://haki.example/")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, str]]]:
    """The (address, link) of every reset e-mail sent."""
    outbox: list[tuple[str, str]] = []
    monkeypatch.setattr(
        password_reset,
        "send_password_reset",
        lambda to, link: outbox.append((to, link)),
    )
    yield outbox


def ask(client: TestClient, email: str = EMAIL) -> Any:
    return client.post("/auth/password-reset", json={"email": email})


def confirm(client: TestClient, token: str, password: str = NEW_PASSWORD) -> Any:
    body = {"token": token, "new_password": password}
    return client.post("/auth/password-reset/confirm", json=body)


def token_from(link: str) -> str:
    return link.split("#token=", 1)[1]


def login(client: TestClient, password: str) -> int:
    body = {"email": EMAIL, "password": password}
    return client.post("/auth/login", json=body).status_code


def raw_token(claims: dict[str, Any]) -> str:
    now = datetime.now(UTC)
    payload = {"iat": now, "exp": now + timedelta(minutes=30)} | claims
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def user_id(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


# Asking for a link


def test_off_both_endpoints_are_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "password_reset_enabled", False)

    assert ask(client).status_code == 404
    assert confirm(client, "x").status_code == 404


def test_the_answer_is_the_same_with_or_without_an_account(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    register_and_login(client, EMAIL)

    known = ask(client, EMAIL.upper())
    unknown = ask(client, "nobody@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    # Only the account's own, stored address gets a link
    assert [to for to, _ in sent] == [EMAIL]


def test_the_link_comes_from_the_setting_with_the_token_in_the_fragment(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    register_and_login(client, EMAIL)

    ask(client)

    link = sent[0][1]
    assert link.startswith("https://haki.example/reset#token=")
    assert "?" not in link
    assert decode_reset_token(token_from(link)) is not None


def test_a_host_header_never_changes_the_link(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    register_and_login(client, EMAIL)

    client.post(
        "/auth/password-reset",
        json={"email": EMAIL},
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"},
    )

    assert "evil" not in sent[0][1]


def test_at_most_three_links_an_hour_per_account(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    register_and_login(client, EMAIL)

    answers = [ask(client).status_code for _ in range(5)]

    assert answers == [202] * 5
    assert len(sent) == 3


# Setting the new password


def test_a_reset_sets_the_password_and_signs_out_everywhere(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    old_session = register_and_login(client, EMAIL)
    ask(client)

    response = confirm(client, token_from(sent[0][1]))

    assert response.status_code == 200
    fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=fresh).status_code == 200
    assert client.get("/auth/me", headers=old_session).status_code == 401
    assert login(client, OLD_PASSWORD) == 401
    assert login(client, NEW_PASSWORD) == 200


def test_a_link_works_once(client: TestClient, sent: list[tuple[str, str]]) -> None:
    register_and_login(client, EMAIL)
    ask(client)
    token = token_from(sent[0][1])
    assert confirm(client, token).status_code == 200

    again = confirm(client, token, "yet-another-password")

    assert again.status_code == 400
    assert again.json()["code"] == "invalid_reset_token"
    assert login(client, NEW_PASSWORD) == 200


def test_a_password_change_kills_the_links_sent_before(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    headers = register_and_login(client, EMAIL)
    ask(client)
    changed = client.put(
        "/auth/me/password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert changed.status_code == 200

    response = confirm(client, token_from(sent[0][1]), "taken-over-password")

    assert response.status_code == 400
    assert login(client, NEW_PASSWORD) == 200


@pytest.mark.parametrize("typ", [ACCESS, None])
def test_an_access_token_never_resets_a_password(
    client: TestClient, typ: str | None
) -> None:
    # A stolen session (30 minutes) must not let anyone keep the account
    headers = register_and_login(client, EMAIL)
    claims: dict[str, Any] = {"sub": str(user_id(client, headers))}
    if typ is not None:
        claims["typ"] = typ

    response = confirm(client, raw_token(claims))

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"
    assert login(client, OLD_PASSWORD) == 200


def test_a_reset_token_never_opens_the_api(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    register_and_login(client, EMAIL)
    ask(client)

    headers = {"Authorization": f"Bearer {token_from(sent[0][1])}"}

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_a_token_without_typ_still_opens_the_api(client: TestClient) -> None:
    # Access tokens issued before the claim existed stay valid until expiry
    headers = register_and_login(client, EMAIL)
    uid = user_id(client, headers)

    old = {"Authorization": f"Bearer {raw_token({'sub': str(uid)})}"}

    assert client.get("/auth/me", headers=old).status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        create_token(1, None, RESET, timedelta(minutes=-1)),  # expired
        raw_token({"sub": "999999", "typ": RESET}),  # no such user
    ],
)
def test_bad_tokens_are_refused(client: TestClient, token: str) -> None:
    register_and_login(client, EMAIL)

    response = confirm(client, token)

    assert response.status_code == 400
    assert login(client, OLD_PASSWORD) == 200


def test_the_new_password_follows_the_signup_rules(
    client: TestClient, sent: list[tuple[str, str]]
) -> None:
    register_and_login(client, EMAIL)
    ask(client)

    response = confirm(client, token_from(sent[0][1]), "short")

    assert response.status_code == 422
    assert login(client, OLD_PASSWORD) == 200


# The e-mail and the guard


def test_the_email_goes_to_the_address_given_and_cannot_add_headers() -> None:
    message = mail.reset_message(EMAIL, "https://haki.example/reset#token=t")

    assert message["To"] == EMAIL
    assert "https://haki.example/reset#token=t" in message.get_content()
    with pytest.raises(ValueError):
        mail.reset_message("a@example.com\r\nBcc: x@example.com", "link")


@pytest.mark.parametrize(("host", "tls"), [("smtp.example", True), ("mailpit", False)])
def test_smtp_uses_tls_unless_the_server_is_local(
    monkeypatch: pytest.MonkeyPatch, host: str, tls: bool
) -> None:
    calls: list[str] = []

    class FakeSMTP:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def starttls(self, **kwargs: Any) -> None:
            calls.append("starttls")

        def send_message(self, message: EmailMessage) -> None:
            calls.append("send")

    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", host)
    monkeypatch.setattr(settings, "mail_backend", "smtp")

    mail.send_password_reset(EMAIL, "https://haki.example/reset#token=t")

    assert calls == (["starttls", "send"] if tls else ["send"])


def test_prod_refuses_the_log_backend_for_reset_links() -> None:
    with pytest.raises(ValidationError, match="MAIL_BACKEND=smtp"):
        Settings(
            environment="prod",
            password_reset_enabled=True,
            mail_backend="log",
        )
    # Prod with the flag off, or with SMTP, starts
    Settings(environment="prod", password_reset_enabled=False, mail_backend="log")
    Settings(environment="prod", password_reset_enabled=True, mail_backend="smtp")
