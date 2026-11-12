from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_exercises import create_exercise
from tests.test_workouts import create_workout


def sets(*pairs: tuple[int, float]) -> list[dict[str, Any]]:
    return [{"reps": reps, "weight_kg": weight} for reps, weight in pairs]


def log(
    client: TestClient,
    headers: dict[str, str],
    day: str,
    *blocks: tuple[int, list[dict[str, Any]]],
) -> int:
    body = {
        "performed_on": day,
        "note": None,
        "exercises": [{"exercise_id": e, "sets": s} for e, s in blocks],
    }
    return create_workout(client, headers, body)["id"]


def history(
    client: TestClient,
    headers: dict[str, str],
    exercise_id: int,
    kind: str,
    **params: Any,
) -> Any:
    response = client.get(
        f"/exercises/{exercise_id}/{kind}", params=params, headers=headers
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def squat(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Squat")["id"]


@pytest.fixture
def bench(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Bench press")["id"]


# Last time


def test_last_is_null_for_an_exercise_never_done(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    assert history(client, auth_headers, squat, "last") is None


def test_last_returns_the_latest_workouts_sets_in_order(
    client: TestClient, auth_headers: dict[str, str], squat: int, bench: int
) -> None:
    log(client, auth_headers, "2026-11-01", (squat, sets((5, 100))))
    latest = log(
        client,
        auth_headers,
        "2026-11-05",
        (squat, sets((8, 80), (6, 90))),
        (bench, sets((10, 50))),
        # A second block of the same exercise counts too, after the first
        (squat, sets((12, 60))),
    )
    # Logged later, but for an earlier day: not "last time"
    log(client, auth_headers, "2026-11-03", (squat, sets((3, 120))))

    last = history(client, auth_headers, squat, "last")

    assert last == {
        "workout_id": latest,
        "performed_on": "2026-11-05",
        "sets": sets((8, 80), (6, 90), (12, 60)),
    }


def test_last_skips_workouts_without_the_exercise(
    client: TestClient, auth_headers: dict[str, str], squat: int, bench: int
) -> None:
    with_squat = log(client, auth_headers, "2026-11-01", (squat, sets((5, 100))))
    log(client, auth_headers, "2026-11-02", (bench, sets((10, 50))))

    assert history(client, auth_headers, squat, "last")["workout_id"] == with_squat


def test_last_before_a_workout_shows_the_session_before_it(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    first = log(client, auth_headers, "2026-11-01", (squat, sets((5, 100))))
    second = log(client, auth_headers, "2026-11-03", (squat, sets((5, 105))))
    third = log(client, auth_headers, "2026-11-03", (squat, sets((5, 110))))

    before_third = history(client, auth_headers, squat, "last", before_workout=third)
    before_second = history(client, auth_headers, squat, "last", before_workout=second)
    before_first = history(client, auth_headers, squat, "last", before_workout=first)

    # Two workouts on one day: the one logged first comes first
    assert before_third["workout_id"] == second
    assert before_second["workout_id"] == first
    assert before_first is None


# Best set


def test_best_is_null_for_an_exercise_never_done(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    assert history(client, auth_headers, squat, "best") is None


def test_best_is_the_heaviest_then_the_most_reps(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    log(client, auth_headers, "2026-11-01", (squat, sets((10, 100), (3, 110))))
    best_day = log(client, auth_headers, "2026-11-04", (squat, sets((5, 110))))
    log(client, auth_headers, "2026-11-06", (squat, sets((12, 90))))

    best = history(client, auth_headers, squat, "best")

    assert best == {
        "reps": 5,
        "weight_kg": 110,
        "performed_on": "2026-11-04",
        "workout_id": best_day,
    }


def test_best_bodyweight_sets_compare_by_reps(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    pull_up = create_exercise(client, auth_headers, "Pull-up")["id"]
    log(client, auth_headers, "2026-11-01", (pull_up, sets((8, 0), (12, 0), (10, 0))))

    assert history(client, auth_headers, pull_up, "best")["reps"] == 12


def test_best_tie_goes_to_the_first_time(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    first = log(client, auth_headers, "2026-11-01", (squat, sets((5, 100))))
    log(client, auth_headers, "2026-11-08", (squat, sets((5, 100))))

    assert history(client, auth_headers, squat, "best")["workout_id"] == first


def test_best_before_a_workout_ignores_it_and_later_ones(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    log(client, auth_headers, "2026-11-01", (squat, sets((5, 100))))
    today = log(client, auth_headers, "2026-11-08", (squat, sets((5, 120))))

    best = history(client, auth_headers, squat, "best", before_workout=today)

    assert best["weight_kg"] == 100


# Access and validation


@pytest.mark.parametrize("kind", ["last", "best"])
def test_history_ignores_another_users_workouts(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    kind: str,
) -> None:
    mine = create_exercise(client, auth_headers, "Squat")["id"]
    theirs = create_exercise(client, other_auth_headers, "Squat")["id"]
    log(client, other_auth_headers, "2026-11-01", (theirs, sets((5, 200))))

    assert history(client, auth_headers, mine, kind) is None


@pytest.mark.parametrize("kind", ["last", "best"])
def test_history_of_another_users_exercise_is_404(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    kind: str,
) -> None:
    theirs = create_exercise(client, other_auth_headers, "Squat")["id"]
    log(client, other_auth_headers, "2026-11-01", (theirs, sets((5, 200))))

    response = client.get(f"/exercises/{theirs}/{kind}", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.parametrize("kind", ["last", "best"])
def test_history_before_another_users_workout_is_404(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
    kind: str,
) -> None:
    theirs = create_exercise(client, other_auth_headers, "Squat")["id"]
    their_workout = log(
        client, other_auth_headers, "2026-11-01", (theirs, sets((5, 1)))
    )

    response = client.get(
        f"/exercises/{squat}/{kind}",
        params={"before_workout": their_workout},
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize("kind", ["last", "best"])
@pytest.mark.parametrize("before", [0, 2_147_483_648, "x"])
def test_history_rejects_an_invalid_workout_id(
    client: TestClient,
    auth_headers: dict[str, str],
    squat: int,
    kind: str,
    before: Any,
) -> None:
    response = client.get(
        f"/exercises/{squat}/{kind}",
        params={"before_workout": before},
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.parametrize("kind", ["last", "best"])
def test_history_requires_login(client: TestClient, kind: str) -> None:
    assert client.get(f"/exercises/1/{kind}").status_code == 401
