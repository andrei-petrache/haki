"""Replacing a program on PostgreSQL, where (program_id, position) is a
unique constraint checked at once: the old days must be gone before the
new ones on the same positions arrive."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import register_and_login

pytestmark = pytest.mark.integration


def body(exercise_id: int, name: str, *positions: int) -> dict:
    return {
        "name": name,
        "days": [
            {
                "position": position,
                "name": f"Day {position}",
                "exercises": [
                    {"exercise_id": exercise_id, "sets": 3, "reps": 5, "weight_kg": 80}
                ],
            }
            for position in positions
        ],
    }


def test_replace_program_on_the_same_positions(
    db: Session, pg_client: TestClient
) -> None:
    headers = register_and_login(pg_client, "program-edit@example.com")
    squat = pg_client.post("/exercises", json={"name": "Squat"}, headers=headers)
    squat_id = squat.json()["id"]
    created = pg_client.post(
        "/programs", json=body(squat_id, "PPL", 1, 2, 3), headers=headers
    ).json()

    response = pg_client.put(
        f"/programs/{created['id']}",
        json=body(squat_id, "PPL v2", 3, 2, 1),
        headers=headers,
    )

    assert response.status_code == 200
    assert [d["position"] for d in response.json()["days"]] == [1, 2, 3]
    taken = pg_client.post(
        "/programs", json=body(squat_id, "Other", 1), headers=headers
    )
    clash = pg_client.put(
        f"/programs/{taken.json()['id']}",
        json=body(squat_id, "ppl V2", 1),
        headers=headers,
    )
    assert clash.status_code == 409
