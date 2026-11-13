"""The data export (app/export.py)."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.orm import Session

from app import export
from tests.conftest import register_and_login
from tests.test_delete_account import PASSWORD, fill_account

OTHER = "mallory@example.com"


def download(
    client: TestClient, headers: dict[str, str], password: str = PASSWORD
) -> Any:
    return client.post("/auth/me/export", json={"password": password}, headers=headers)


def exported(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = download(client, headers)
    assert response.status_code == 200, response.text
    return json.loads(response.text)


def user_id(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def test_every_user_table_is_in_the_export(client: TestClient) -> None:
    headers = register_and_login(client, "export@example.com")
    fill_account(client, headers)

    data = exported(client, headers)

    # fill_account reaches every user table; a new table that the export
    # leaves out fails here, as one that deletion leaves behind fails there
    for table in export.user_tables():
        assert data.get(table.name), table.name
    assert data["format"] == "haki-export" and data["version"] == 1
    assert data["complete"] is True


def test_no_secret_is_exported(client: TestClient) -> None:
    headers = register_and_login(client, "export@example.com")
    fill_account(client, headers)

    response = download(client, headers)
    data = json.loads(response.text)

    assert "password_hash" not in response.text
    assert "password_changed_at" not in response.text
    assert set(data["users"][0]) == {
        "id",
        "email",
        "daily_calorie_target",
        "language",
        "target_mode",
        "goal_kg_per_week",
        "created_at",
    }


def test_another_users_data_is_never_in_it(client: TestClient) -> None:
    mine = register_and_login(client, "export@example.com")
    theirs = register_and_login(client, OTHER)
    fill_account(client, mine)
    fill_account(client, theirs)

    data = exported(client, mine)

    me = user_id(client, mine)
    assert [row["id"] for row in data["users"]] == [me]
    for table in export.user_tables():
        for row in data[table.name]:
            if "user_id" in row:
                assert row["user_id"] == me, table.name
    # The child tables hold only rows under my workouts and programs
    workouts = {row["id"] for row in data["workouts"]}
    assert {row["workout_id"] for row in data["workout_exercises"]} <= workouts
    programs = {row["id"] for row in data["programs"]}
    assert {row["program_id"] for row in data["program_days"]} <= programs


def test_the_file_is_a_download_that_is_never_cached(client: TestClient) -> None:
    headers = register_and_login(client, "export@example.com")

    response = download(client, headers)

    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="haki-export-'
    )
    assert response.headers["cache-control"] == "no-store"


def test_a_wrong_password_exports_nothing(client: TestClient) -> None:
    headers = register_and_login(client, "export@example.com")

    response = download(client, headers, "not-the-password")

    assert response.status_code == 403
    assert response.json()["code"] == "wrong_password"


def test_the_export_needs_a_login(client: TestClient) -> None:
    assert client.post("/auth/me/export", json={"password": "x"}).status_code == 401


def test_a_file_cut_off_by_an_error_lacks_the_last_key(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = register_and_login(client, "export@example.com")
    fill_account(client, headers)
    real = export.rows_of

    def broken(table: Table, uid: int) -> Any:
        if table.name == "workouts":
            raise RuntimeError("the database went away")
        return real(table, uid)

    monkeypatch.setattr(export, "rows_of", broken)
    chunks: list[str] = []

    with pytest.raises(RuntimeError):
        for chunk in export.export_chunks(session, user_id(client, headers)):
            chunks.append(chunk)

    text = "".join(chunks)
    assert '"complete"' not in text
    assert '"users"' in text


def test_a_table_the_export_cannot_tie_to_a_user_fails_loudly() -> None:
    orphan = Table("orphans", MetaData(), Column("id", Integer, primary_key=True))

    with pytest.raises(LookupError, match="orphans"):
        export.rows_of(orphan, 1)
