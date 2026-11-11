"""The catalog import against the migrated PostgreSQL schema.

import_catalog commits; inside the `db` fixture that commit releases a
savepoint, and the test's outer transaction still rolls everything back.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog_import import DATA_DIR, import_catalog, load_files
from app.models import CatalogExercise, CatalogFood

pytestmark = pytest.mark.integration


def test_import_twice_on_postgresql(db: Session) -> None:
    shipped = load_files(DATA_DIR)
    foods, exercises = shipped[0].foods, shipped[1].exercises

    first = import_catalog(db)
    second = import_catalog(db)

    assert first["catalog_foods"].inserted == len(foods)
    assert first["catalog_exercises"].inserted == len(exercises)
    assert second["catalog_foods"].unchanged == len(foods)
    assert second["catalog_exercises"].unchanged == len(exercises)
    assert db.scalar(select(func.count()).select_from(CatalogFood)) == len(foods)


def test_json_lists_round_trip(db: Session) -> None:
    import_catalog(db)

    squat = db.scalars(
        select(CatalogExercise).where(CatalogExercise.source_ref == "Barbell_Squat")
    ).one()

    assert squat.primary_muscles == ["quadriceps"]
    assert squat.image_refs == ["Barbell_Squat/0.jpg", "Barbell_Squat/1.jpg"]
