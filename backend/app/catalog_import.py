"""Load the catalog from the data files shipped in the image.

    python -m app.catalog_import

Idempotent: every item is upserted by its source and its id at the source
(source_ref), all in one transaction. A second run with the same files
changes nothing; an item whose values changed in the files is updated in
place. Nothing is ever deleted: an item dropped from the files stays, and
users' copies keep their link. Only catalog tables are written, never a
user's row.

Memory does not grow with the data: each file is read as a stream, one item
at a time, and written in batches of BATCH_SIZE. Every file is read twice.
The first pass validates everything, so a bad file writes nothing. The
second pass upserts. Only the refs seen so far are kept in memory, to catch
duplicates.

Needs only the database settings, like the migrations: never import
app.config or app.db here, which require the JWT secret.
"""

import json
import logging
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from typing import Annotated, Any, TextIO

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.catalog_search import search_text
from app.db_config import DatabaseSettings
from app.models import CatalogExercise, CatalogFood, CatalogSource
from app.schemas import MAX_CALORIES_PER_100G

logger = logging.getLogger("app.catalog_import")

DATA_DIR = Path(__file__).resolve().parent / "catalog_data"
# Any constant: two imports at once queue behind this lock in PostgreSQL
ADVISORY_LOCK_KEY = 4_242_001
# Items validated and written together: big enough that the round trips do
# not dominate, small enough that a batch's rows take a few MB at most
BATCH_SIZE = 1_000
# Characters read from a file at a time
READ_CHUNK = 64 * 1024

# The columns' lengths (app/models.py). A longer value is rejected, never
# cut: a cut name could collide with another or lose what tells two foods
# apart ("..., raw" / "..., cooked"), and the file is fixed instead.
NAME_MAX = 100
SEARCH_TEXT_MAX = 250
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)
]
Label = Annotated[str, StringConstraints(min_length=1, max_length=30)]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class BadData(ValueError):
    """A data file is not valid JSON or does not match its schema."""


class Strict(BaseModel):
    # A misspelt key in a data file is an error, not a silently empty column
    model_config = ConfigDict(extra="forbid")


class Named(Strict):
    """An item with an English and an optional Romanian name."""

    ref: Ref
    name: Name
    name_ro: Name | None = None

    @model_validator(mode="after")
    def search_text_fits(self) -> Named:
        # Normalizing can lengthen a name (a ligature becomes two letters)
        length = len(search_text(self.name, self.name_ro))
        if length > SEARCH_TEXT_MAX:
            raise ValueError(
                f"{self.ref}: search text of {length} characters, "
                f"at most {SEARCH_TEXT_MAX}"
            )
        return self


class SourceData(Strict):
    key: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    license: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    attribution: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    attribution_required: bool
    share_alike: bool
    version: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    # Our own estimates, not the source's measurements; absent means false
    estimated: bool = False


class FoodData(Named):
    """Nutrients per 100 g, within the bounds a user's own food has (FoodIn),
    so a copy of any catalog food is a valid food."""

    calories_per_100g: float = Field(ge=0, le=MAX_CALORIES_PER_100G)
    protein_per_100g: float = Field(ge=0, le=100)
    carbs_per_100g: float = Field(ge=0, le=100)
    fat_per_100g: float = Field(ge=0, le=100)
    # The source's own name for the item (USDA descriptions reach 200
    # characters), kept in the file for reviewers and never stored
    source_description: str | None = None


class ExerciseData(Named):
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
    """A whole foods file, for tests and tools that want it at once. The
    import itself streams the file (read_data_file)."""

    source: SourceData
    foods: list[FoodData] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_refs(self) -> FoodFile:
        refs_are_unique(self.foods)
        return self


class ExerciseFile(Strict):
    """A whole exercises file; see FoodFile."""

    source: SourceData
    exercises: list[ExerciseData] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_refs(self) -> ExerciseFile:
        refs_are_unique(self.exercises)
        return self


@dataclass(frozen=True)
class CatalogKind:
    """One data file and the table it fills."""

    file_name: str
    items_key: str
    item_model: type[FoodData] | type[ExerciseData]
    model: type[CatalogFood] | type[CatalogExercise]


KINDS = (
    CatalogKind("foods.json", "foods", FoodData, CatalogFood),
    CatalogKind("exercises.json", "exercises", ExerciseData, CatalogExercise),
)


@dataclass
class Counts:
    """What one import did to one table."""

    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


# Reading


class JsonReader:
    """Reads JSON values one at a time from a file, never the whole file.

    The buffer holds at most one chunk plus the value being read, so an item
    costs memory only while it is read.
    """

    WHITESPACE = " \t\r\n"
    DECODER = json.JSONDecoder()

    def __init__(self, file: TextIO, name: str) -> None:
        self.file = file
        self.name = name
        self.buffer = ""
        self.pos = 0
        self.dropped = 0  # characters before the buffer, for error positions
        self.at_end = False

    def fail(self, message: str, pos: int | None = None) -> BadData:
        at = self.dropped + (self.pos if pos is None else pos)
        return BadData(f"{self.name}: {message} at character {at}")

    def read_more(self) -> bool:
        """Append a chunk to the buffer; False at the end of the file."""
        if self.at_end:
            return False
        chunk = self.file.read(READ_CHUNK)
        if not chunk:
            self.at_end = True
            return False
        self.dropped += self.pos
        self.buffer = self.buffer[self.pos :] + chunk
        self.pos = 0
        return True

    def peek(self) -> str:
        """The next character that is not whitespace, or "" at the end."""
        while True:
            while (
                self.pos < len(self.buffer) and self.buffer[self.pos] in self.WHITESPACE
            ):
                self.pos += 1
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if not self.read_more():
                return ""

    def expect(self, char: str) -> None:
        found = self.peek()
        if found != char:
            raise self.fail(f"expected {char!r}, found {found or 'the end'!r}")
        self.pos += 1

    def value(self) -> Any:
        """The next whole JSON value."""
        if not self.peek():
            raise self.fail("unexpected end of the file")
        while True:
            try:
                value, end = self.DECODER.raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError as error:
                # Usually the value goes on in the next chunk
                if self.read_more():
                    continue
                raise self.fail(error.msg, error.pos) from error
            # A number at the buffer's end may go on in the next chunk too
            if end == len(self.buffer) and self.read_more():
                continue
            self.pos = end
            return value


def read_data_file(path: Path, items_key: str) -> Iterator[Any]:
    """Yield a data file's source, then its items one by one.

    The file is an object with exactly two keys, "source" and items_key,
    in that order, so the source is known before the first item.
    """
    with path.open(encoding="utf-8") as file:
        reader = JsonReader(file, path.name)
        reader.expect("{")
        for position, expected in enumerate(("source", items_key)):
            if position:
                reader.expect(",")
            key = reader.value()
            if key != expected:
                raise reader.fail(f"expected the key {expected!r}, found {key!r}")
            reader.expect(":")
            if key == "source":
                yield reader.value()
            else:
                yield from read_array(reader, items_key)
        reader.expect("}")
        if reader.peek():
            raise reader.fail("more data after the end")


def read_array(reader: JsonReader, items_key: str) -> Iterator[Any]:
    reader.expect("[")
    if reader.peek() == "]":
        raise reader.fail(f"{items_key!r} is empty")
    while True:
        yield reader.value()
        if reader.peek() != ",":
            break
        reader.pos += 1
    reader.expect("]")


def validated(model: type[BaseModel], raw: Any, where: str) -> Any:
    try:
        return model.model_validate(raw)
    except ValidationError as error:
        raise BadData(f"{where}: {error}") from error


def read_batches(
    path: Path, kind: CatalogKind, batch_size: int
) -> tuple[SourceData, Iterator[list[FoodData | ExerciseData]]]:
    """The file's source, and its items validated in batches."""
    stream = read_data_file(path, kind.items_key)
    source = validated(SourceData, next(stream), f"{path.name}: source")

    def batches() -> Iterator[list[FoodData | ExerciseData]]:
        position = 0
        # The last batch is usually shorter
        for raw_items in batched(stream, batch_size, strict=False):
            batch = []
            for raw in raw_items:
                where = f"{path.name}: {kind.items_key}[{position}]"
                batch.append(validated(kind.item_model, raw, where))
                position += 1
            yield batch

    return source, batches()


def check_files(data_dir: Path, batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """Validate every file whole before anything is written: the number of
    items per file, or BadData (OSError if a file cannot be read)."""
    totals = {}
    for kind in KINDS:
        path = data_dir / kind.file_name
        _, batches = read_batches(path, kind, batch_size)
        seen: set[str] = set()
        duplicates: set[str] = set()
        for batch in batches:
            for item in batch:
                if item.ref in seen:
                    duplicates.add(item.ref)
                seen.add(item.ref)
        if duplicates:
            raise BadData(
                f"{path.name}: duplicate refs: {', '.join(sorted(duplicates))}"
            )
        totals[kind.file_name] = len(seen)
    return totals


def load_files(data_dir: Path) -> tuple[FoodFile, ExerciseFile]:
    """Both files read whole, for tests and tools. The import streams them."""
    foods = FoodFile.model_validate(read_json(data_dir / "foods.json"))
    exercises = ExerciseFile.model_validate(read_json(data_dir / "exercises.json"))
    return foods, exercises


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# Writing


def upsert_source(session: Session, data: SourceData, counts: Counts) -> int:
    """The id of the source row for `data`, created or brought up to date."""
    values = data.model_dump()
    source = session.scalar(select(CatalogSource).where(CatalogSource.key == data.key))
    if source is None:
        source = CatalogSource(**values)
        session.add(source)
        counts.inserted += 1
    elif assign_changes(source, values):
        counts.updated += 1
    else:
        counts.unchanged += 1
    session.flush()  # its id, for the items
    return source.id


def assign_changes(row: Any, values: dict[str, Any]) -> bool:
    """Set the fields whose value differs; True if any did."""
    changed = False
    for field, value in values.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed = True
    return changed


def item_values(item: FoodData | ExerciseData) -> dict[str, Any]:
    """The columns an item fills, besides its source and ref."""
    values = item.model_dump(exclude={"ref", "source_description"})
    values["search_text"] = search_text(item.name, item.name_ro)
    return values


def upsert_batch(
    session: Session,
    model: type[CatalogFood] | type[CatalogExercise],
    source_id: int,
    items: Sequence[FoodData | ExerciseData],
    counts: Counts,
) -> None:
    """Insert new items, update changed ones, leave the rest; never delete.

    Reads only this batch's rows, as plain tuples, and writes with bulk
    statements, so no ORM object of the batch stays in the session.
    """
    values = {item.ref: item_values(item) for item in items}
    fields = list(next(iter(values.values())))
    existing = {
        row.source_ref: row._mapping
        for row in session.execute(
            select(
                model.id, model.source_ref, *(getattr(model, f) for f in fields)
            ).where(model.source_id == source_id, model.source_ref.in_(list(values)))
        )
    }
    inserts = []
    updates = []
    for ref, item in values.items():
        row = existing.get(ref)
        if row is None:
            inserts.append({"source_id": source_id, "source_ref": ref, **item})
        elif any(row[f] != v for f, v in item.items()):
            updates.append({"id": row["id"], **item})
    if inserts:
        session.execute(insert(model), inserts)
    if updates:
        session.execute(update(model), updates)
        forget_updated(session, model, {row["id"] for row in updates})
    counts.inserted += len(inserts)
    counts.updated += len(updates)
    counts.unchanged += len(values) - len(inserts) - len(updates)


def forget_updated(session: Session, model: type, ids: set[int]) -> None:
    """Expire the caller's own copies of rows a bulk update changed, so they
    reload instead of showing the old values."""
    for obj in list(session.identity_map.values()):
        if isinstance(obj, model) and obj.id in ids:
            session.expire(obj)


def import_catalog(
    session: Session, data_dir: Path = DATA_DIR, batch_size: int = BATCH_SIZE
) -> dict[str, Counts]:
    """Upsert the whole catalog in one transaction and commit it.

    Returns the counts per table. If anything fails, nothing is written.
    """
    check_files(data_dir, batch_size)
    if session.get_bind().dialect.name == "postgresql":
        # Held until the commit: a second import waits, then finds nothing
        # left to do, instead of failing on the unique constraints
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
        )
    counts = {"catalog_sources": Counts()}
    for kind in KINDS:
        source, batches = read_batches(data_dir / kind.file_name, kind, batch_size)
        source_id = upsert_source(session, source, counts["catalog_sources"])
        table = counts[kind.model.__tablename__] = Counts()
        for batch in batches:
            upsert_batch(session, kind.model, source_id, batch, table)
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
        check_files(DATA_DIR)
    except (OSError, ValueError) as error:  # BadData is a ValueError
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
