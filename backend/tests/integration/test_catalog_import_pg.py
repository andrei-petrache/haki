"""The catalog import against the migrated PostgreSQL schema.

import_catalog commits; inside the `db` fixture that commit releases a
savepoint, and the test's outer transaction still rolls everything back.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog_import import DATA_DIR, import_catalog, load_files
from app.models import CatalogExercise, CatalogFood, CatalogSource
from tests.test_catalog_import import all_foods

pytestmark = pytest.mark.integration


def test_import_twice_on_postgresql(db: Session) -> None:
    exercises = load_files(DATA_DIR)[1].exercises
    foods = all_foods()

    first = import_catalog(db)
    second = import_catalog(db)

    assert first["catalog_foods"].inserted == len(foods)
    assert first["catalog_exercises"].inserted == len(exercises)
    assert second["catalog_foods"].unchanged == len(foods)
    assert second["catalog_exercises"].unchanged == len(exercises)
    assert db.scalar(select(func.count()).select_from(CatalogFood)) == len(foods)


def test_our_estimates_are_flagged_on_postgresql(db: Session) -> None:
    import_catalog(db)

    sources = {s.key: s.estimated for s in db.scalars(select(CatalogSource))}

    assert sources == {
        "usda-fdc-sr-legacy": False,
        "haki-ro-staples": True,
        "free-exercise-db": False,
    }
    sarmale = db.scalars(
        select(CatalogFood).where(CatalogFood.source_ref == "sarmale-varza")
    ).one()
    assert sarmale.name_ro == "Sarmale în foi de varză"


def test_json_lists_round_trip(db: Session) -> None:
    import_catalog(db)

    squat = db.scalars(
        select(CatalogExercise).where(CatalogExercise.source_ref == "Barbell_Squat")
    ).one()

    assert squat.primary_muscles == ["quadriceps"]
    assert squat.image_refs == ["Barbell_Squat/0.jpg", "Barbell_Squat/1.jpg"]
