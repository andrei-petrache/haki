"""How catalog names are matched: lower case, without diacritics.

The import stores search_text with these functions and the search endpoint
normalizes the query with the same ones, so "branza" finds "Brânză" and the
same plain LIKE runs on PostgreSQL and on the tests' SQLite.
"""

import re
import unicodedata

# Anything that is not a letter or a digit separates words
NON_WORD = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    """Lower case, diacritics removed, words separated by single spaces.

    "Ș", "ş" (the cedilla form older keyboards type) and "S" all become "s".
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return NON_WORD.sub(" ", without_marks).strip()


def search_text(*names: str | None) -> str:
    """The text a catalog row is searched by: all its names, normalized.

    Wrapped in spaces, so " word" matches a word's start anywhere, the first
    word included.
    """
    return f" {' '.join(normalize(name) for name in names if name)} "


def query_words(query: str) -> list[str]:
    """The words of a search query; every one must appear in a match."""
    return normalize(query).split()
