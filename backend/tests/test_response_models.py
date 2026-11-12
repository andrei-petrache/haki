"""Responses describe what is stored; only input carries bounds.

A response model that re-checks an input bound fails with a 500 on a row
that another version of the app accepted, e.g. after a rollback to a
version with a lower limit.
"""

from collections.abc import Iterable, Iterator
from typing import Any, get_args

import annotated_types
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.main import app
from app.models import Food


def models_in(annotation: Any) -> Iterator[type[BaseModel]]:
    """Every pydantic model an annotation holds, nested ones included."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        for field in annotation.model_fields.values():
            yield from models_in(field.annotation)
    for argument in get_args(annotation):
        yield from models_in(argument)


def api_routes(routes: Iterable[Any]) -> Iterator[APIRoute]:
    """Every APIRoute, also inside included routers. FastAPI wraps those in
    an _IncludedRouter that keeps the APIRouter as `original_router`; if
    that changes, test_the_app_has_response_models_to_check fails."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        router = getattr(route, "original_router", route)
        inner = getattr(router, "routes", None)
        if inner:
            yield from api_routes(inner)


def response_models() -> set[type[BaseModel]]:
    return {
        model
        for route in api_routes(app.routes)
        if route.response_model is not None
        for model in models_in(route.response_model)
    }


def test_the_app_has_response_models_to_check() -> None:
    names = {model.__name__ for model in response_models()}

    assert {"FoodResponse", "ExerciseResponse", "WorkoutResponse"} <= names


def test_no_response_model_carries_an_input_bound() -> None:
    bounded = sorted(
        f"{model.__name__}.{name}"
        for model in response_models()
        for name, field in model.model_fields.items()
        if any(
            isinstance(
                m, annotated_types.BaseMetadata | annotated_types.GroupedMetadata
            )
            for m in field.metadata
        )
    )

    assert bounded == []


def test_a_stored_food_above_todays_limit_is_still_listed(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    food = {
        "name": "Lard",
        "calories_per_100g": 902,
        "protein_per_100g": 0,
        "carbs_per_100g": 0,
        "fat_per_100g": 100,
    }
    food_id = client.post("/foods", json=food, headers=auth_headers).json()["id"]
    # As if a later version had accepted it and this one had been rolled back to
    session.execute(
        update(Food).where(Food.id == food_id).values(calories_per_100g=1200)
    )
    session.commit()

    response = client.get("/foods", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[0]["calories_per_100g"] == 1200
