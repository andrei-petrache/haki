"""One search over the user's own foods and the catalog: GET /foods/search.

Own foods come first, then catalog foods, in one list; each result says
where it comes from ("own" or "catalog"). Both are matched by the
catalog's rules: every word of the query, in either name, case and
diacritics ignored ("branza" finds "Brânză").
"""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.catalog import MAX_QUERY_WORDS, search_query
from app.catalog_search import query_words, search_text
from app.foods import newest_entries, to_last_logged
from app.models import CatalogFood, Food, User
from app.schemas import (
    CatalogFoodResult,
    CatalogLanguage,
    FoodSearchResult,
    OwnFoodResult,
)

router = APIRouter(prefix="/foods", tags=["foods"])

SearchQuery = Annotated[str, Query(min_length=1, max_length=100)]
# Each origin gets this many at most: many matching foods of the user's own
# never hide the catalog
SearchLimit = Annotated[int, Query(ge=1, le=50)]


def own_matches(
    session: Session, user: User, words: list[str], limit: int
) -> list[OwnFoodResult]:
    """The user's foods matching every word, last used first, then by name.

    A copy of a catalog food also matches by the catalog's names, so an
    English word finds a food the user keeps under its Romanian name. The
    user's foods are filtered here, not in SQL: they have no search_text
    column, and one user's list is small.
    """
    rows = session.execute(
        select(Food, CatalogFood.name, CatalogFood.name_ro)
        .outerjoin(CatalogFood, Food.catalog_food_id == CatalogFood.id)
        .where(Food.user_id == user.id)
    )
    matched = [
        food
        for food, catalog_name, catalog_name_ro in rows
        if all(
            word in search_text(food.name, catalog_name, catalog_name_ro)
            for word in words
        )
    ]
    newest = newest_entries(session, user, [food.id for food in matched])

    def rank(food: Food) -> tuple[bool, int, str, int]:
        entry = newest.get(food.id)
        # Logged ones first, the newest use first; then by name
        return (entry is None, -(entry.id if entry else 0), food.name.lower(), food.id)

    return [
        OwnFoodResult(
            id=food.id,
            name=food.name,
            calories_per_100g=food.calories_per_100g,
            protein_per_100g=food.protein_per_100g,
            carbs_per_100g=food.carbs_per_100g,
            fat_per_100g=food.fat_per_100g,
            favourite=food.favourite,
            last_logged=to_last_logged(newest.get(food.id)),
            catalog_food_id=food.catalog_food_id,
        )
        for food in sorted(matched, key=rank)[:limit]
    ]


def catalog_matches(
    session: Session, user: User, q: str, language: CatalogLanguage, limit: int
) -> list[CatalogFoodResult]:
    """Catalog foods matching `q`, in the catalog's order, leaving out the
    ones the user already copied: their own copy is listed instead."""
    copied = select(Food.catalog_food_id).where(
        Food.user_id == user.id, Food.catalog_food_id.is_not(None)
    )
    query = (
        search_query(CatalogFood, q, language)
        .where(CatalogFood.id.not_in(copied))
        .limit(limit)
    )
    return [
        CatalogFoodResult(
            id=item.id,
            name=item.name_ro if language == "ro" and item.name_ro else item.name,
            calories_per_100g=item.calories_per_100g,
            protein_per_100g=item.protein_per_100g,
            carbs_per_100g=item.carbs_per_100g,
            fat_per_100g=item.fat_per_100g,
            source_key=item.source.key,
        )
        for item in session.scalars(query)
    ]


@router.get("/search", response_model=list[FoodSearchResult])
def search_foods(
    current_user: CurrentUser,
    session: SessionDep,
    q: SearchQuery,
    language: CatalogLanguage = "en",
    limit: SearchLimit = 20,
) -> list[OwnFoodResult | CatalogFoodResult]:
    """The user's matching foods, then the catalog's: at most `limit` of
    each. A query of only punctuation matches nothing."""
    words = query_words(q)[:MAX_QUERY_WORDS]
    if not words:
        return []
    return [
        *own_matches(session, current_user, words, limit),
        *catalog_matches(session, current_user, q, language, limit),
    ]
