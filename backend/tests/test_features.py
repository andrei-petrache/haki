import pytest
from fastapi.testclient import TestClient

from app.config import settings


@pytest.mark.parametrize("on", [True, False])
def test_the_flags_follow_the_settings_without_a_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, on: bool
) -> None:
    monkeypatch.setattr(settings, "password_reset_enabled", on)
    monkeypatch.setattr(settings, "body_weight_enabled", not on)

    response = client.get("/features")

    assert response.status_code == 200
    assert response.json() == {
        "password_reset": on,
        "body_weight": not on,
        "export": True,
    }


def test_the_answer_may_be_cached_for_a_minute(client: TestClient) -> None:
    response = client.get("/features")

    assert response.headers["cache-control"] == "public, max-age=60"
