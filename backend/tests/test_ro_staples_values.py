"""The haki-ro-staples values (scripts/ro_staples_values.py) are what their
recipes give: recomputed here from the SR Legacy rows kept in the repo."""

import json

from app.catalog_import import FoodFile
from scripts.ro_staples import NOTES, RO_STAPLES
from scripts.ro_staples_values import (
    ANALOGUES,
    CATALOG_FILE,
    OIL_UPTAKE,
    RECIPES,
    USDA,
    USDA_DISH,
    catalog_file,
    read_snapshot,
)


def test_the_catalog_file_is_what_the_recipes_give() -> None:
    committed = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    assert committed == catalog_file(read_snapshot())


def test_every_item_has_a_value_by_its_decided_method() -> None:
    by_method = {"recipe": RECIPES, "usda-dish": USDA_DISH, "analogue": ANALOGUES}

    for ref, *_, method in RO_STAPLES:
        assert ref in by_method[method], (ref, method)
    listed = {ref for ref, *_ in RO_STAPLES}
    for table in by_method.values():
        assert set(table) <= listed


def test_every_ingredient_is_an_sr_legacy_row_kept_in_the_repo() -> None:
    snapshot = read_snapshot()
    used = {name for recipe in RECIPES.values() for name, _ in recipe.ingredients}
    used |= set(USDA_DISH.values()) | {food for food, _ in ANALOGUES.values()}

    for name in used:
        assert USDA[name] in snapshot, name


def test_recipes_are_sane() -> None:
    for ref, recipe in RECIPES.items():
        assert 0 < recipe.yield_factor <= 1, ref
        assert all(grams > 0 for _, grams in recipe.ingredients), ref


def test_fried_recipes_say_where_their_oil_uptake_comes_from() -> None:
    fried = [ref for ref, note in NOTES.items() if note.startswith("fried")]

    assert fried
    for ref in fried:
        assert OIL_UPTAKE in RECIPES[ref].note, ref


def test_every_analogue_gives_its_reason() -> None:
    for ref, (_, reason) in ANALOGUES.items():
        assert len(reason) > 10, ref


def test_the_file_is_a_valid_catalog_source_of_estimates() -> None:
    data = FoodFile.model_validate(json.loads(CATALOG_FILE.read_text(encoding="utf-8")))

    assert data.source.key == "haki-ro-staples"
    assert data.source.estimated is True
    assert data.source.license == "CC0-1.0"
    assert len(data.foods) == len(RO_STAPLES)
