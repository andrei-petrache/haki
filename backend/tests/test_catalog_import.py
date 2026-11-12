import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import catalog_import
from app.catalog_import import (
    DATA_DIR,
    EXIT_BAD_DATA,
    EXIT_DATABASE,
    EXIT_OK,
    NAME_MAX,
    BadData,
    check_files,
    import_catalog,
    load_files,
    main,
    read_data_file,
)
from app.catalog_search import normalize, query_words, search_text
from app.models import (
    Base,
    CatalogExercise,
    CatalogFood,
    CatalogSource,
    Food,
    User,
)

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

    with pytest.raises(BadData, match=message):
        import_catalog(session, data_dir)

    assert count(session, CatalogSource) == 0
    assert count(session, CatalogFood) == 0
    assert count(session, CatalogExercise) == 0


# Batches and the streamed read


def test_small_batches_import_the_same_as_one_batch(session: Session) -> None:
    foods, exercises = load_files(DATA_DIR)

    counts = import_catalog(session, batch_size=7)

    assert counts["catalog_foods"].inserted == len(foods.foods)
    assert counts["catalog_exercises"].inserted == len(exercises.exercises)
    names = set(session.scalars(select(CatalogFood.name)))
    assert names == {food.name for food in foods.foods}


def test_small_batches_update_only_what_changed(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    import_catalog(session, data_dir, batch_size=7)

    def change(data: dict[str, Any]) -> None:
        data["foods"][0].update(protein_per_100g=23.1)  # first batch
        data["foods"][-1].update(name_ro="Ultimul aliment")  # last batch

    edit("foods.json", change)
    last_ref = load_files(data_dir)[0].foods[-1].ref

    counts = import_catalog(session, data_dir, batch_size=7)

    assert counts["catalog_foods"].updated == 2
    assert counts["catalog_foods"].inserted == 0
    total = len(load_files(data_dir)[0].foods)
    assert counts["catalog_foods"].unchanged == total - 2
    assert catalog_food(session, "171077").protein_per_100g == 23.1
    assert catalog_food(session, last_ref).name_ro == "Ultimul aliment"


def test_a_duplicate_in_a_later_batch_writes_nothing(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    edit("foods.json", lambda d: d["foods"][-1].update(ref=d["foods"][0]["ref"]))

    with pytest.raises(BadData, match="duplicate refs: 171077"):
        import_catalog(session, data_dir, batch_size=2)

    assert count(session, CatalogSource) == 0


def test_a_bad_item_in_the_last_batch_writes_nothing(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    # The first pass validates the whole file before the second one writes
    edit("exercises.json", lambda d: d["exercises"][-1].update(level=""))

    with pytest.raises(BadData, match=r"exercises.json: exercises\[\d+\]"):
        import_catalog(session, data_dir, batch_size=2)

    assert count(session, CatalogSource) == 0
    assert count(session, CatalogFood) == 0


def test_tiny_read_chunks_split_values_and_numbers(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Chunks of 3 characters cut through strings, objects and numbers
    monkeypatch.setattr(catalog_import, "READ_CHUNK", 3)
    foods, _ = load_files(DATA_DIR)

    import_catalog(session)

    chicken = catalog_food(session, "171077")
    expected = next(food for food in foods.foods if food.ref == "171077")
    assert chicken.calories_per_100g == expected.calories_per_100g
    assert chicken.name_ro == expected.name_ro


def test_the_stream_yields_the_source_then_each_item(tmp_path: Path) -> None:
    path = tmp_path / "foods.json"
    path.write_text('{"source": {"key": "s"}, "foods": [{"a": 1}, 2.5, [3]]}')

    assert list(read_data_file(path, "foods")) == [{"key": "s"}, {"a": 1}, 2.5, [3]]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "expected '{', found 'the end'"),
        ('{"foods": [], "source": {}}', "expected the key 'source', found 'foods'"),
        ('{"source": {}, "food": []}', "expected the key 'foods', found 'food'"),
        ('{"source": {}}', "expected ',', found '}'"),
        ('{"source": {}, "foods": []}', "'foods' is empty"),
        ('{"source": {}, "foods": [{"a": 1},]}', "Expecting value"),
        ('{"source": {}, "foods": [{"a": 1}', "expected ']', found 'the end'"),
        ('{"source": {}, "foods": [1], "x": 2}', "expected '}', found ','"),
        ('{"source": {}, "foods": [1]} []', "more data after the end"),
        ('{"source": {}, "foods": [{"a": tru}]}', "Expecting"),
    ],
)
def test_a_malformed_file_is_bad_data(
    tmp_path: Path, content: str, message: str
) -> None:
    path = tmp_path / "foods.json"
    path.write_text(content)

    pattern = f"^foods\\.json: .*{re.escape(message)}.* at character \\d+$"
    with pytest.raises(BadData, match=pattern):
        list(read_data_file(path, "foods"))


def test_check_files_counts_the_items() -> None:
    foods, exercises = load_files(DATA_DIR)

    totals = check_files(DATA_DIR, batch_size=5)

    assert totals == {
        "foods.json": len(foods.foods),
        "exercises.json": len(exercises.exercises),
    }


# Lengths: the columns hold 100 characters per name, 250 of search text


def test_the_source_descriptions_are_longer_than_a_name_and_never_stored(
    session: Session,
) -> None:
    # Why the files carry names of their own: USDA's descriptions do not fit
    foods = load_files(DATA_DIR)[0].foods
    longest = max(len(item.source_description or "") for item in foods)
    import_catalog(session)

    assert longest > NAME_MAX
    assert not hasattr(CatalogFood, "source_description")


@pytest.mark.parametrize("field", ["name", "name_ro"])
def test_a_name_of_100_characters_is_imported_whole(
    session: Session, data_dir: Path, edit: EditFile, field: str
) -> None:
    edit("foods.json", lambda d: d["foods"][0].update({field: "x" * NAME_MAX}))

    import_catalog(session, data_dir)

    assert getattr(catalog_food(session, "171077"), field) == "x" * NAME_MAX


@pytest.mark.parametrize("field", ["name", "name_ro"])
def test_a_longer_name_is_rejected_not_cut(
    session: Session, data_dir: Path, edit: EditFile, field: str
) -> None:
    edit("foods.json", lambda d: d["foods"][0].update({field: "x" * 101}))

    with pytest.raises(BadData, match="at most 100 characters"):
        import_catalog(session, data_dir)

    assert count(session, CatalogFood) == 0


def test_a_search_text_too_long_after_normalizing_is_rejected(
    session: Session, data_dir: Path, edit: EditFile
) -> None:
    # "ﬃ" is one character, "ffi" after normalizing: 100 + 100 become 600
    ligatures = "ﬃ" * NAME_MAX
    edit(
        "exercises.json",
        lambda d: d["exercises"][0].update(name=ligatures, name_ro=ligatures),
    )

    with pytest.raises(BadData, match="at most 250"):
        import_catalog(session, data_dir)

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


# The command and its exit codes


def test_command_imports_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'catalog.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)

    assert main() == EXIT_OK

    with Session(engine) as check:
        assert count(check, CatalogFood) == len(load_files(DATA_DIR)[0].foods)
    engine.dispose()


def test_command_exits_2_on_bad_data(
    data_dir: Path, edit: EditFile, monkeypatch: pytest.MonkeyPatch
) -> None:
    edit("exercises.json", lambda d: d["exercises"][0].pop("name"))
    monkeypatch.setattr(catalog_import, "DATA_DIR", data_dir)

    assert main() == EXIT_BAD_DATA


def test_command_exits_2_on_a_missing_file(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (data_dir / "foods.json").unlink()
    monkeypatch.setattr(catalog_import, "DATA_DIR", data_dir)

    assert main() == EXIT_BAD_DATA


def test_command_exits_3_when_the_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Port 1 on the loopback refuses at once
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/x_test")

    assert main() == EXIT_DATABASE


@pytest.mark.parametrize(("calories", "accepted"), [(950, True), (950.1, False)])
def test_catalog_calories_stop_at_the_users_cap(
    session: Session, data_dir: Path, edit: EditFile, calories: float, accepted: bool
) -> None:
    # The same bound as a user's own food, so every catalog food can be copied
    edit("foods.json", lambda d: d["foods"][0].update(calories_per_100g=calories))

    if accepted:
        import_catalog(session, data_dir)
        assert catalog_food(session, "171077").calories_per_100g == calories
    else:
        with pytest.raises(BadData, match="less than or equal to 950"):
            import_catalog(session, data_dir)
        assert count(session, CatalogFood) == 0
