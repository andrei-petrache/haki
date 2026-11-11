import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog_import import DATA_DIR, import_catalog, load_files
from app.catalog_search import normalize, query_words, search_text
from app.models import CatalogExercise, CatalogFood, CatalogSource, Food, User

EditFile = Callable[[str, Callable[[dict[str, Any]], None]], None]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A copy of the shipped data files, safe to edit."""
    for name in ("foods.json", "exercises.json"):
        shutil.copy(DATA_DIR / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def edit(data_dir: Path) -> EditFile:
    """Change one of the copied data files in place."""

    def edit_file(name: str, change: Callable[[dict[str, Any]], None]) -> None:
        path = data_dir / name
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    return edit_file


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def catalog_food(session: Session, ref: str) -> CatalogFood:
    return session.scalars(
        select(CatalogFood).where(CatalogFood.source_ref == ref)
    ).one()


# The shipped data


def test_the_shipped_files_are_valid() -> None:
    foods, exercises = load_files(DATA_DIR)

    assert foods.source.license == "CC0-1.0"
    assert exercises.source.license == "Unlicense"
    assert len(foods.foods) >= 100
    assert len(exercises.exercises) >= 80


def test_every_shipped_item_has_a_romanian_name() -> None:
    foods, exercises = load_files(DATA_DIR)

    missing = [i.ref for i in [*foods.foods, *exercises.exercises] if not i.name_ro]

    assert missing == []


def test_romanian_names_use_the_comma_below_letters() -> None:
    # ş and ţ (cedilla) are the legacy forms; Romanian writes ș and ț
    foods, exercises = load_files(DATA_DIR)

    names = [i.name_ro or "" for i in [*foods.foods, *exercises.exercises]]

    assert [n for n in names if "ş" in n or "ţ" in n or "Ş" in n or "Ţ" in n] == []


def test_names_are_unique_per_language() -> None:
    # Two catalog items with one name could not both be copied by a user
    foods, exercises = load_files(DATA_DIR)

    for items in (foods.foods, exercises.exercises):
        for names in ([i.name for i in items], [i.name_ro for i in items]):
            assert len(names) == len(set(names))


# Importing


def test_first_import_inserts_everything(session: Session) -> None:
    foods, exercises = load_files(DATA_DIR)

    counts = import_catalog(session)

    assert counts["catalog_sources"].inserted == 2
    assert counts["catalog_foods"].inserted == len(foods.foods)
    assert counts["catalog_exercises"].inserted == len(exercises.exercises)
    assert count(session, CatalogFood) == len(foods.foods)
    assert count(session, CatalogExercise) == len(exercises.exercises)


def test_second_import_changes_nothing(session: Session) -> None:
    import_catalog(session)
    ids = set(session.scalars(select(CatalogFood.id)))

    counts = import_catalog(session)

    assert all(c.inserted == c.updated == 0 for c in counts.values())
    assert counts["catalog_sources"].unchanged == 2
    assert set(session.scalars(select(CatalogFood.id))) == ids


def test_a_changed_value_is_updated_in_place(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    import_catalog(session, data_dir)
    before = catalog_food(session, "171077")
    edit("foods.json", lambda d: d["foods"][0].update(protein_per_100g=23.1))

    counts = import_catalog(session, data_dir)

    assert counts["catalog_foods"].updated == 1
    after = catalog_food(session, "171077")
    assert after.id == before.id
    assert after.protein_per_100g == 23.1


def test_a_changed_name_updates_the_search_text(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    import_catalog(session, data_dir)
    edit("foods.json", lambda d: d["foods"][0].update(name_ro="Piept de pui crud"))

    import_catalog(session, data_dir)

    assert "piept de pui crud" in catalog_food(session, "171077").search_text


def test_a_new_source_version_updates_the_source(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    import_catalog(session, data_dir)
    edit("exercises.json", lambda d: d["source"].update(version="abc123"))

    counts = import_catalog(session, data_dir)

    assert counts["catalog_sources"].updated == 1
    source = session.scalars(
        select(CatalogSource).where(CatalogSource.key == "free-exercise-db")
    ).one()
    assert source.version == "abc123"


def test_an_item_dropped_from_the_files_is_kept(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    import_catalog(session, data_dir)
    total = count(session, CatalogFood)
    edit("foods.json", lambda d: d["foods"].pop(0))

    import_catalog(session, data_dir)

    assert count(session, CatalogFood) == total
    assert catalog_food(session, "171077").name.startswith("Chicken breast")


def test_a_new_item_is_inserted(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    import_catalog(session, data_dir)
    new = {
        "ref": "999999",
        "name": "Test food",
        "calories_per_100g": 1,
        "protein_per_100g": 0,
        "carbs_per_100g": 0,
        "fat_per_100g": 0,
    }
    edit("foods.json", lambda d: d["foods"].append(new))

    counts = import_catalog(session, data_dir)

    assert counts["catalog_foods"].inserted == 1
    assert catalog_food(session, "999999").name_ro is None


def test_import_never_touches_a_users_copy(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    # The copy is what the user logged with; a correction in the catalog
    # must not rewrite their history
    import_catalog(session, data_dir)
    user = User(email="andrei@example.com", password_hash="x")
    session.add(user)
    session.flush()
    chicken = catalog_food(session, "171077")
    copy = Food(
        user_id=user.id,
        name=chicken.name,
        calories_per_100g=chicken.calories_per_100g,
        protein_per_100g=chicken.protein_per_100g,
        carbs_per_100g=chicken.carbs_per_100g,
        fat_per_100g=chicken.fat_per_100g,
        catalog_food_id=chicken.id,
    )
    session.add(copy)
    session.commit()
    edit("foods.json", lambda d: d["foods"][0].update(protein_per_100g=50))

    import_catalog(session, data_dir)

    session.refresh(copy)
    assert copy.protein_per_100g == 22.5
    assert copy.catalog_food_id == chicken.id


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["foods"][1].update(fat_per_100g=-1), "greater than or equal"),
        (lambda d: d["foods"][1].update(name="x" * 101), "at most 100"),
        (lambda d: d["foods"][1].update(ref=d["foods"][0]["ref"]), "duplicate"),
        (lambda d: d["foods"][1].update(proteins=1), "Extra inputs"),
        (lambda d: d["source"].pop("license"), "license"),
    ],
)
def test_a_bad_file_writes_nothing(
    session: Session,
    data_dir: Path,
    edit: EditFile,
    change: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    edit("foods.json", change)

    with pytest.raises(ValidationError, match=message):
        import_catalog(session, data_dir)

    assert count(session, CatalogSource) == 0
    assert count(session, CatalogFood) == 0
    assert count(session, CatalogExercise) == 0


# Search text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Brânză", "branza"),
        ("ȘNIȚEL țară", "snitel tara"),
        ("şniţel", "snitel"),  # the cedilla forms
        ("Împins înclinat", "impins inclinat"),
        ("Barbell Bench Press - Medium Grip", "barbell bench press medium grip"),
        ("Milk, whole, 3.25% fat", "milk whole 3 25 fat"),
        ("  ", ""),
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected


def test_search_text_holds_both_names_between_spaces() -> None:
    assert search_text("Feta cheese", "Brânză feta") == " feta cheese branza feta "


def test_search_text_skips_a_missing_name() -> None:
    assert search_text("Feta cheese", None) == " feta cheese "


def test_query_words() -> None:
    assert query_words("  Piept, de PUI ") == ["piept", "de", "pui"]
    assert query_words("%_") == []
