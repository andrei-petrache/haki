"""Load the catalog from the data files shipped in the image.

    python -m app.catalog_import

Idempotent: every item is upserted by its source and its id at the source
(source_ref), all in one transaction. A second run with the same files
changes nothing; an item whose values changed in the files is updated in
place. Nothing is ever deleted: an item dropped from the files stays, and
users' copies keep their link. Only catalog tables are written, never a
user's row.

Needs only the database settings, like the migrations: never import
app.config or app.db here, which require the JWT secret.
"""

import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.catalog_search import search_text
from app.db_config import DatabaseSettings
from app.models import CatalogExercise, CatalogFood, CatalogSource

logger = logging.getLogger("app.catalog_import")

DATA_DIR = Path(__file__).resolve().parent / "catalog_data"
# Any constant: two imports at once queue behind this lock in PostgreSQL
ADVISORY_LOCK_KEY = 4_242_001

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Label = Annotated[str, StringConstraints(min_length=1, max_length=30)]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class Strict(BaseModel):
    # A misspelt key in a data file is an error, not a silently empty column
    model_config = ConfigDict(extra="forbid")


class SourceData(Strict):
    key: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    license: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    attribution: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    attribution_required: bool
    share_alike: bool
    version: Annotated[str, StringConstraints(min_length=1, max_length=100)]


class FoodData(Strict):
    """Nutrients per 100 g, within the bounds a user's own food has (FoodIn),
    so a copy of any catalog food is a valid food."""

    ref: Ref
    name: Name
    name_ro: Name | None = None
    calories_per_100g: float = Field(ge=0, le=900)
    protein_per_100g: float = Field(ge=0, le=100)
    carbs_per_100g: float = Field(ge=0, le=100)
    fat_per_100g: float = Field(ge=0, le=100)
    # The source's own name for the item, kept in the file for reviewers
    source_description: str | None = None


class ExerciseData(Strict):
    ref: Ref
    name: Name
    name_ro: Name | None = None
    category: Label | None = None
    equipment: Label | None = None
    level: Label | None = None
    force: Label | None = None
    mechanic: Label | None = None
    primary_muscles: list[Label] = Field(max_length=20)
    secondary_muscles: list[Label] = Field(max_length=20)
    image_refs: list[Ref] = Field(max_length=10)


def refs_are_unique(items: Sequence[FoodData | ExerciseData]) -> None:
    refs = [item.ref for item in items]
    duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
    if duplicates:
        raise ValueError(f"duplicate refs: {', '.join(duplicates)}")


class FoodFile(Strict):
    source: SourceData
    foods: list[FoodData] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_refs(self) -> FoodFile:
        refs_are_unique(self.foods)
        return self


class ExerciseFile(Strict):
    source: SourceData
    exercises: list[ExerciseData] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_refs(self) -> ExerciseFile:
        refs_are_unique(self.exercises)
        return self


@dataclass
class Counts:
    """What one import did to one table."""

    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def upsert_source(session: Session, data: SourceData, counts: Counts) -> CatalogSource:
    """The source row for `data`, created or brought up to date."""
    values = data.model_dump()
    source = session.scalar(select(CatalogSource).where(CatalogSource.key == data.key))
    if source is None:
        source = CatalogSource(**values)
        session.add(source)
        session.flush()  # its id, for the items
        counts.inserted += 1
    elif assign_changes(source, values):
        counts.updated += 1
    else:
        counts.unchanged += 1
    return source


def assign_changes(row: Any, values: dict[str, Any]) -> bool:
    """Set the fields whose value differs; True if any did."""
    changed = False
    for field, value in values.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    return changed


def upsert_items(
    session: Session,
    model: type[CatalogFood] | type[CatalogExercise],
    source: CatalogSource,
    items: Sequence[FoodData | ExerciseData],
) -> Counts:
    """Insert new items, update changed ones, leave the rest; never delete."""
    existing = {
        row.source_ref: row
        for row in session.scalars(select(model).where(model.source_id == source.id))
    }
    counts = Counts()
    for item in items:
        values = item.model_dump(exclude={"ref", "source_description"})
        values["search_text"] = search_text(item.name, item.name_ro)
        row = existing.get(item.ref)
        if row is None:
            session.add(model(source_id=source.id, source_ref=item.ref, **values))
            counts.inserted += 1
        elif assign_changes(row, values):
            counts.updated += 1
        else:
            counts.unchanged += 1
    return counts


def load_files(data_dir: Path) -> tuple[FoodFile, ExerciseFile]:
    """Read and validate both files before anything is written."""
    foods = FoodFile.model_validate(read_json(data_dir / "foods.json"))
    exercises = ExerciseFile.model_validate(read_json(data_dir / "exercises.json"))
    return foods, exercises


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def import_catalog(session: Session, data_dir: Path = DATA_DIR) -> dict[str, Counts]:
    """Upsert the whole catalog in one transaction and commit it.

    Returns the counts per table. If anything fails, nothing is written.
    """
    foods, exercises = load_files(data_dir)
    if session.get_bind().dialect.name == "postgresql":
        # Held until the commit: a second import waits, then finds nothing
        # left to do, instead of failing on the unique constraints
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
        )
    counts = {"catalog_sources": Counts()}
    for model, data, items in (
        (CatalogFood, foods, foods.foods),
        (CatalogExercise, exercises, exercises.exercises),
    ):
        source = upsert_source(session, data.source, counts["catalog_sources"])
        counts[model.__tablename__] = upsert_items(session, model, source, items)
    session.commit()
    return counts


# Exit codes, so a failed Job says why without reading its log
EXIT_OK = 0
EXIT_ERROR = 1  # anything unexpected; the traceback is in the log
EXIT_BAD_DATA = 2  # a data file is missing, not JSON, or fails validation
EXIT_DATABASE = 3  # the database refused or could not be reached; retry


def main() -> int:
    """Run the import; return one of the EXIT_* codes."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        load_files(DATA_DIR)
    except (OSError, ValueError) as error:  # ValidationError is a ValueError
        logger.error("Catalog data files are invalid, nothing written: %s", error)
        return EXIT_BAD_DATA
    engine = create_engine(DatabaseSettings().db_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            counts = import_catalog(session, DATA_DIR)
    except (OperationalError, PoolTimeoutError) as error:
        logger.error("Database unavailable, nothing written: %s", error)
        return EXIT_DATABASE
    finally:
        engine.dispose()
    for table, result in counts.items():
        logger.info(
            "%s: %d inserted, %d updated, %d unchanged",
            table,
            result.inserted,
            result.updated,
            result.unchanged,
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
