"""The haki-ro-staples list (scripts/ro_staples.py) holds what the import
will need: refs are permanent once imported, so they are checked now."""

import re

from scripts.ro_staples import METHODS, NOTES, RO_STAPLES

# catalog_foods.name and name_ro are String(100)
MAX_NAME = 100


def test_refs_are_unique() -> None:
    refs = [ref for ref, *_ in RO_STAPLES]

    assert len(refs) == len(set(refs))


def test_refs_are_lower_case_words_joined_by_dashes() -> None:
    for ref, *_ in RO_STAPLES:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", ref), ref


def test_names_fit_their_columns() -> None:
    for ref, ro, en, _ in RO_STAPLES:
        assert 0 < len(ro) <= MAX_NAME, ref
        assert 0 < len(en) <= MAX_NAME, ref


def test_english_names_carry_the_romanian_one() -> None:
    # So an English search tells ours apart from USDA's food of the same name
    for ref, ro, en, _ in RO_STAPLES:
        assert en.endswith(f"({ro})"), ref


def test_every_method_is_known() -> None:
    for ref, *_, method in RO_STAPLES:
        assert method in METHODS, ref


def test_notes_are_for_items_on_the_list() -> None:
    refs = {ref for ref, *_ in RO_STAPLES}

    assert set(NOTES) <= refs


def test_the_list_is_the_one_decided() -> None:
    methods = [method for *_, method in RO_STAPLES]

    assert len(RO_STAPLES) == 109
    assert (methods.count("recipe"), methods.count("usda-dish")) == (80, 7)
    assert methods.count("analogue") == 22
