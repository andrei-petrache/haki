"""The shared catalog of foods and exercises: read-only, for every user.

Only the import (app/catalog_import.py) writes these tables. A user who
picks an item gets a copy in their own list: POST /foods/from-catalog and
POST /exercises/from-catalog.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentUser, SessionDep
from app.catalog_search import query_words
from app.models import CatalogExercise, CatalogFood, CatalogSource
from app.schemas import (
    CatalogExerciseResponse,
    CatalogFoodResponse,
    CatalogLanguage,
    CatalogSourceResponse,
    IdPath,
)
from app.workouts import LimitQuery, OffsetQuery

router = APIRouter(prefix="/catalog", tags=["catalog"])

# Words beyond these are ignored: each one adds a LIKE to the query
MAX_QUERY_WORDS = 8
SearchQuery = Annotated[str, Query(max_length=100)]
LanguageQuery = Annotated[CatalogLanguage, Query()]

CATALOG_FOOD_NOT_FOUND = "Catalog food not found"
CATALOG_EXERCISE_NOT_FOUND = "Catalog exercise not found"


def search_query[M: (CatalogFood, CatalogExercise)](
    model: type[M], q: str, language: CatalogLanguage
) -> Select[tuple[M]]:
    """Items whose names contain every word of `q`, best matches first.

    Words are matched without case or diacritics, anywhere in either name.
    Items where the first word starts a word come first; then by name in
    `language` (English where there is no Romanian name), then by id, so
    pages never overlap.
    """
    words = query_words(q)[:MAX_QUERY_WORDS]
    query = select(model).options(joinedload(model.source))
    for word in words:
        # Normalized words hold only letters and digits: no LIKE wildcards
        query = query.where(model.search_text.contains(word))
    name = model.name
    if language == "ro":
        name = func.coalesce(model.name_ro, model.name)
    order = [func.lower(name), model.id]
    if words:
        starts_a_word = model.search_text.contains(f" {words[0]}")
        order.insert(0, case((starts_a_word, 0), else_=1))
    return query.order_by(*order)


def get_catalog_item[M: (CatalogFood, CatalogExercise)](
    session: Session, model: type[M], item_id: int, detail: str
) -> M:
    """One catalog item, with its source, or 404."""
    query = select(model).options(joinedload(model.source)).where(model.id == item_id)
    item = session.scalar(query)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return item


@router.get("/sources", response_model=list[CatalogSourceResponse])
def list_sources(current_user: CurrentUser, session: SessionDep) -> list[CatalogSource]:
    """Every source of the catalog, with its licence and credit line."""
    return list(session.scalars(select(CatalogSource).order_by(CatalogSource.key)))


@router.get("/foods", response_model=list[CatalogFoodResponse])
def search_foods(
    current_user: CurrentUser,
    session: SessionDep,
    q: SearchQuery = "",
    language: LanguageQuery = "en",
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> list[CatalogFood]:
    """Search the catalog's foods by name; an empty query lists them all."""
    query = search_query(CatalogFood, q, language).limit(limit).offset(offset)
    return list(session.scalars(query))


@router.get("/foods/{food_id}", response_model=CatalogFoodResponse)
def read_food(
    food_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> CatalogFood:
    """One catalog food."""
    return get_catalog_item(session, CatalogFood, food_id, CATALOG_FOOD_NOT_FOUND)


@router.get("/exercises", response_model=list[CatalogExerciseResponse])
def search_exercises(
    current_user: CurrentUser,
    session: SessionDep,
    q: SearchQuery = "",
    language: LanguageQuery = "en",
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> list[CatalogExercise]:
    """Search the catalog's exercises by name; an empty query lists them all."""
    query = search_query(CatalogExercise, q, language).limit(limit).offset(offset)
    return list(session.scalars(query))


@router.get("/exercises/{exercise_id}", response_model=CatalogExerciseResponse)
def read_exercise(
    exercise_id: IdPath, current_user: CurrentUser, session: SessionDep
) -> CatalogExercise:
    """One catalog exercise."""
    return get_catalog_item(
        session, CatalogExercise, exercise_id, CATALOG_EXERCISE_NOT_FOUND
    )
