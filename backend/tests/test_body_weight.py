"""Body weight and the adaptive target through the API (app/body.py)."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.body import server_today
from app.config import settings
from app.consent import CURRENT_VERSIONS
from app.models import TdeeEstimate

TODAY = server_today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())
# The 21 days this week's estimate looks at, oldest first
WINDOW = [MONDAY - timedelta(days=n) for n in range(21, 0, -1)]


@pytest.fixture(autouse=True)
def enabled(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, auth_headers: dict[str, str]
) -> Iterator[None]:
    """The flag on, and the main user's health-data consent given (the
    consent itself is tested in tests/test_consent.py)."""
    monkeypatch.setattr(settings, "body_weight_enabled", True)
    consent(client, auth_headers)
    yield


def consent(client: TestClient, headers: dict[str, str]) -> None:
    body = {"version": CURRENT_VERSIONS["health_data"], "locale": "en"}
    given = client.put("/auth/me/consents/health_data", json=body, headers=headers)
    assert given.status_code == 200, given.text


def weigh(client: TestClient, headers: dict[str, str], day: date, kg: float) -> Any:
    return client.put(f"/weights/{day}", json={"weight_kg": kg}, headers=headers)


def eat(client: TestClient, headers: dict[str, str], day: date, kcal: float) -> None:
    body = {"eaten_on": str(day), "meal_type": "lunch", "calories": kcal}
    response = client.post("/entries/quick", json=body, headers=headers)
    assert response.status_code == 201, response.text


def set_goal(
    client: TestClient, headers: dict[str, str], mode: str, goal: float | None
) -> Any:
    body = {"target_mode": mode, "goal_kg_per_week": goal}
    return client.put("/auth/me/goal", json=body, headers=headers)


def set_manual_target(client: TestClient, headers: dict[str, str], kcal: int) -> None:
    body = {"daily_calorie_target": kcal}
    assert client.put("/auth/me/target", json=body, headers=headers).status_code == 200


def read_target(client: TestClient, headers: dict[str, str], day: date = TODAY) -> Any:
    return client.get("/targets/current", params={"date": str(day)}, headers=headers)


def three_steady_weeks(
    client: TestClient, headers: dict[str, str], kg_per_week: float, kcal: float
) -> None:
    for i, day in enumerate(WINDOW):
        assert weigh(client, headers, day, 80 + kg_per_week * i / 7).status_code == 201
        eat(client, headers, day, kcal)


# The flag


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/weights"),
        ("PUT", f"/weights/{TODAY}"),
        ("DELETE", f"/weights/{TODAY}"),
        ("PUT", "/auth/me/goal"),
        ("GET", f"/targets/current?date={TODAY}"),
    ],
)
def test_off_every_endpoint_is_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    monkeypatch.setattr(settings, "body_weight_enabled", False)

    response = client.request(method, path, json={}, headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_off_the_summary_keeps_the_users_own_target(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    set_manual_target(client, auth_headers, 2000)
    set_goal(client, auth_headers, "adaptive", -0.5)
    monkeypatch.setattr(settings, "body_weight_enabled", False)

    summary = client.get("/summary", params={"date": str(TODAY)}, headers=auth_headers)

    assert summary.json()["daily_calorie_target"] == 2000


# Weigh-ins


def test_a_weigh_in_is_created_then_replaced(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    first = weigh(client, auth_headers, TODAY, 80.456)
    second = weigh(client, auth_headers, TODAY, 79.9)

    assert first.status_code == 201
    assert first.json() == {"measured_on": str(TODAY), "weight_kg": 80.46}
    assert second.status_code == 200
    listed = client.get("/weights", headers=auth_headers).json()
    assert [(p["measured_on"], p["weight_kg"]) for p in listed] == [(str(TODAY), 79.9)]


def test_weights_are_numbers_in_json_never_strings(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    weigh(client, auth_headers, TODAY, 72.5)
    set_goal(client, auth_headers, "adaptive", -0.25)

    point = client.get("/weights", headers=auth_headers).json()[0]
    me = client.get("/auth/me", headers=auth_headers).json()

    assert isinstance(point["weight_kg"], float)
    assert isinstance(point["trend_kg"], float)
    assert isinstance(me["goal_kg_per_week"], float)


@pytest.mark.parametrize(
    ("day", "kg", "code"),
    [
        (TODAY, 19.9, "validation_error"),
        (TODAY, 400.1, "validation_error"),
        (TODAY + timedelta(days=2), 80, "date_out_of_range"),
        (date(1999, 12, 31), 80, "date_out_of_range"),
    ],
)
def test_impossible_weigh_ins_are_refused(
    client: TestClient, auth_headers: dict[str, str], day: date, kg: float, code: str
) -> None:
    response = weigh(client, auth_headers, day, kg)

    assert response.status_code == 422
    assert response.json()["code"] == code
    assert client.get("/weights", headers=auth_headers).json() == []


def test_tomorrow_is_allowed_for_time_zones_ahead(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert weigh(client, auth_headers, TODAY + timedelta(days=1), 80).status_code == 201


def test_a_weigh_in_is_deleted_once(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    weigh(client, auth_headers, TODAY, 80)

    first = client.delete(f"/weights/{TODAY}", headers=auth_headers)
    second = client.delete(f"/weights/{TODAY}", headers=auth_headers)

    assert first.status_code == 204
    assert second.status_code == 404
    assert second.json()["code"] == "weight_not_found"


def test_another_users_weigh_ins_stay_theirs(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    consent(client, other_auth_headers)
    weigh(client, other_auth_headers, TODAY, 90)

    mine = client.get("/weights", headers=auth_headers).json()
    deleted = client.delete(f"/weights/{TODAY}", headers=auth_headers)

    assert mine == []
    assert deleted.status_code == 404
    assert len(client.get("/weights", headers=other_auth_headers).json()) == 1


def test_the_list_is_a_range_with_a_trend(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    for i, day in enumerate(WINDOW):
        weigh(client, auth_headers, day, 83.0 if i == 15 else 80.0)

    response = client.get(
        "/weights",
        params={"from": str(WINDOW[10]), "to": str(WINDOW[20])},
        headers=auth_headers,
    )

    points = response.json()
    assert [p["measured_on"] for p in points] == [str(d) for d in WINDOW[10:]]
    # The trend started before `from`, so it is settled at 80
    assert points[0]["trend_kg"] == 80.0
    assert [p["outlier"] for p in points].count(True) == 1
    assert points[5]["outlier"]


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-01-10", "to": "2026-01-01"},
        {"from": "2024-12-31", "to": "2026-01-01"},
    ],
)
def test_a_backwards_or_too_long_range_is_refused(
    client: TestClient, auth_headers: dict[str, str], params: dict[str, str]
) -> None:
    response = client.get("/weights", params=params, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["code"] == "date_out_of_range"


def test_weigh_ins_need_a_login(client: TestClient) -> None:
    assert client.get("/weights").status_code == 401
    assert weigh(client, {}, TODAY, 80).status_code == 401


# The goal and the target


def test_the_goal_is_part_of_the_user(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = set_goal(client, auth_headers, "adaptive", -0.5)

    assert response.status_code == 200
    me = client.get("/auth/me", headers=auth_headers).json()
    assert (me["target_mode"], me["goal_kg_per_week"]) == ("adaptive", -0.5)


@pytest.mark.parametrize(
    "body",
    [
        {"target_mode": "magic", "goal_kg_per_week": None},
        {"target_mode": "adaptive", "goal_kg_per_week": -1.5},
        {"target_mode": "adaptive", "goal_kg_per_week": 0.75},
        {"target_mode": "adaptive"},
    ],
)
def test_impossible_goals_are_refused(
    client: TestClient, auth_headers: dict[str, str], body: dict[str, Any]
) -> None:
    response = client.put("/auth/me/goal", json=body, headers=auth_headers)

    assert response.status_code == 422
    me = client.get("/auth/me", headers=auth_headers).json()
    assert (me["target_mode"], me["goal_kg_per_week"]) == ("manual", None)


def test_in_manual_mode_the_target_is_the_users_own(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    set_manual_target(client, auth_headers, 2100)

    response = read_target(client, auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "manual"
    assert response.json()["target_kcal"] == 2100


@pytest.mark.parametrize("days", [-2, 2, 30])
def test_the_target_is_only_for_the_clients_today(
    client: TestClient, auth_headers: dict[str, str], days: int
) -> None:
    response = read_target(client, auth_headers, TODAY + timedelta(days=days))

    assert response.status_code == 422
    assert response.json()["code"] == "date_out_of_range"


def test_without_data_the_estimate_is_collecting_and_says_why(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    set_manual_target(client, auth_headers, 2000)
    set_goal(client, auth_headers, "adaptive", -0.5)

    first = read_target(client, auth_headers).json()
    second = read_target(client, auth_headers).json()

    assert first["status"] == "collecting"
    assert first["target_kcal"] == 2000
    assert "few_weigh_ins" in first["reasons"]
    assert first["week_start"] == str(MONDAY)
    assert second == first
    # Stored once for the week
    assert session.scalar(select(func.count()).select_from(TdeeEstimate)) == 1


def test_three_weeks_of_data_give_an_adaptive_target(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    set_manual_target(client, auth_headers, 2000)
    set_goal(client, auth_headers, "adaptive", -0.5)
    # Losing 0.5 kg a week on 2000 kcal: a TDEE of about 2550
    three_steady_weeks(client, auth_headers, -0.5, 2000)

    body = read_target(client, auth_headers).json()

    assert body["status"] == "adaptive"
    assert body["tdee_kcal"] == 2550
    assert body["target_kcal"] == 2000  # 2550 - 0.5 x 7700 / 7
    assert body["trend_kg_per_week"] == pytest.approx(-0.5)
    assert body["reasons"] == []
    assert not body["floor_applied"]


def test_changing_the_goal_mid_week_changes_the_target_not_the_estimate(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    set_manual_target(client, auth_headers, 2000)
    set_goal(client, auth_headers, "adaptive", -0.5)
    three_steady_weeks(client, auth_headers, -0.5, 2000)
    read_target(client, auth_headers)

    set_goal(client, auth_headers, "adaptive", 0)
    body = read_target(client, auth_headers).json()

    assert (body["tdee_kcal"], body["target_kcal"]) == (2550, 2550)
    assert session.scalar(select(func.count()).select_from(TdeeEstimate)) == 1


def test_the_floor_is_reported_when_it_sets_the_target(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    set_goal(client, auth_headers, "adaptive", -1.0)
    three_steady_weeks(client, auth_headers, 0, 1500)

    body = read_target(client, auth_headers).json()

    assert body["tdee_kcal"] == 1500
    assert body["target_kcal"] == 1200
    assert body["floor_applied"]


def test_last_weeks_estimate_smooths_this_one(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    set_goal(client, auth_headers, "adaptive", None)
    three_steady_weeks(client, auth_headers, 0, 2300)
    last_week = TdeeEstimate(
        user_id=client.get("/auth/me", headers=auth_headers).json()["id"],
        week_start=MONDAY - timedelta(days=7),
        status="adaptive",
        tdee_kcal=2250,
        weigh_ins=21,
        logged_days=21,
        reasons="",
    )
    session.add(last_week)
    session.commit()

    body = read_target(client, auth_headers).json()

    assert body["tdee_kcal"] == 2275


def test_the_summary_uses_the_adaptive_target(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    set_manual_target(client, auth_headers, 2000)
    set_goal(client, auth_headers, "adaptive", 0)
    three_steady_weeks(client, auth_headers, 0, 2300)

    summary = client.get("/summary", params={"date": str(TODAY)}, headers=auth_headers)

    assert summary.json()["daily_calorie_target"] == 2300


def test_the_summary_of_an_old_day_never_creates_an_estimate(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    set_manual_target(client, auth_headers, 2000)
    set_goal(client, auth_headers, "adaptive", 0)

    old = TODAY - timedelta(days=60)
    summary = client.get("/summary", params={"date": str(old)}, headers=auth_headers)

    assert summary.json()["daily_calorie_target"] == 2000
    assert session.scalar(select(func.count()).select_from(TdeeEstimate)) == 0
