"""Barcode lookup through Open Food Facts (app/barcode.py). Open Food Facts
itself is never called: fetch_off is replaced, or pointed at a local server."""

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import barcode
from app.config import settings
from app.models import Base, OffProduct

EAN13 = "5901234123457"  # GS1's own example, valid check digit
UPCA = "036000291452"  # the UPC-A on GS1's example, check digit 2
PRODUCT = {
    "code": EAN13,
    "product_name": "Iaurt grecesc 10%",
    "product_name_ro": "Iaurt grecesc 10%",
    "brands": "Olympus",
    "quantity": "400 g",
    "nutriments": {
        "energy-kcal_100g": 120,
        "proteins_100g": 5,
        "carbohydrates_100g": 4,
        "fat_100g": 10,
    },
    "last_modified_t": 1700000000,
}


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """On, with fresh limits and memory for every test."""
    monkeypatch.setattr(settings, "barcode_enabled", True)
    monkeypatch.setattr(barcode, "per_user", barcode.PerMinute(30))
    monkeypatch.setattr(barcode, "toward_off", barcode.PerMinute(45))
    monkeypatch.setattr(barcode, "not_found", barcode.NotFound())
    yield


@pytest.fixture
def off(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Open Food Facts answering PRODUCT for EAN13 and nothing else; the
    list collects the codes asked for."""
    asked: list[str] = []

    def fake(code: str) -> dict[str, Any] | None:
        asked.append(code)
        return dict(PRODUCT) if code == EAN13 else None

    monkeypatch.setattr(barcode, "fetch_off", fake)
    return asked


def look_up(client: TestClient, headers: dict[str, str], code: str) -> Any:
    return client.get(f"/barcode/{code}", headers=headers)


def rows(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(OffProduct)) or 0


# Codes


@pytest.mark.parametrize(
    ("code", "gtin"),
    [
        (EAN13, "0" + EAN13),
        (UPCA, "00" + UPCA),
        ("96385074", "000000" + "96385074"),  # EAN-8
        ("0" + EAN13, "0" + EAN13),  # already GTIN-14
    ],
)
def test_codes_become_gtin_14(code: str, gtin: str) -> None:
    assert barcode.normalize(code) == gtin


@pytest.mark.parametrize(
    "code", ["5901234123458", "12345", "590123412345a", "٥٩٠١٢٣٤١٢٣٤٥٧", "1" * 15]
)
def test_bad_codes_are_refused(
    client: TestClient, auth_headers: dict[str, str], off: list[str], code: str
) -> None:
    response = look_up(client, auth_headers, code)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_barcode"
    assert off == []


def test_a_upc_a_and_its_ean_13_are_one_product(
    client: TestClient, auth_headers: dict[str, str], off: list[str], session: Session
) -> None:
    upc_as_ean = "0" + UPCA

    look_up(client, auth_headers, UPCA)
    look_up(client, auth_headers, upc_as_ean)

    assert off == [upc_as_ean]  # asked once, in Open Food Facts' form


# Found


def test_a_product_is_answered_credited_and_cached(
    client: TestClient, auth_headers: dict[str, str], off: list[str], session: Session
) -> None:
    first = look_up(client, auth_headers, EAN13)
    again = look_up(client, auth_headers, EAN13)

    body = first.json()
    assert first.status_code == again.status_code == 200
    assert (body["name"], body["brand"], body["quantity"]) == (
        "Iaurt grecesc 10%",
        "Olympus",
        "400 g",
    )
    assert body["calories_per_100g"] == 120 and body["fat_per_100g"] == 10
    assert body["complete"] is True and body["stale"] is False
    assert body["source"] == {
        "key": "open-food-facts",
        "license": "ODbL-1.0",
        "attribution": "Open Food Facts contributors",
        "url": f"https://world.openfoodfacts.org/product/{EAN13}",
    }
    assert off == [EAN13]  # the second came from the cache
    assert rows(session) == 1


def test_values_a_food_could_not_hold_are_left_out(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    odd = dict(
        PRODUCT,
        nutriments={
            "energy-kcal_100g": 2000,
            "proteins_100g": 60,
            "carbohydrates_100g": 50,
            "fat_100g": -1,
        },
    )
    monkeypatch.setattr(barcode, "fetch_off", lambda code: odd)

    body = look_up(client, auth_headers, EAN13).json()

    assert body["calories_per_100g"] is None
    assert body["fat_per_100g"] is None
    # 60 + 50 > 100 g: neither can be right
    assert body["protein_per_100g"] is None and body["carbs_per_100g"] is None
    assert body["complete"] is False
    assert set(body["out_of_range"]) == {
        "calories_per_100g",
        "protein_per_100g",
        "carbs_per_100g",
        "fat_per_100g",
    }


def test_kilojoules_stand_in_for_missing_kcal(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    kj_only = dict(PRODUCT, nutriments={"energy-kj_100g": 418.4, "fat_100g": 1})
    monkeypatch.setattr(barcode, "fetch_off", lambda code: kj_only)

    body = look_up(client, auth_headers, EAN13).json()

    assert body["calories_per_100g"] == pytest.approx(100)
    assert body["protein_per_100g"] is None  # missing stays missing, never 0
    assert body["complete"] is False and body["out_of_range"] == []


# Not found, unavailable, limits


def test_an_unknown_code_is_not_stored_and_not_asked_again_for_a_day(
    client: TestClient, auth_headers: dict[str, str], off: list[str], session: Session
) -> None:
    unknown = "4006381333931"

    first = look_up(client, auth_headers, unknown)
    again = look_up(client, auth_headers, unknown)

    assert first.status_code == again.status_code == 404
    assert first.json()["code"] == "product_not_found"
    assert off == [unknown]
    assert rows(session) == 0  # made-up codes never grow the table


def test_without_open_food_facts_an_old_copy_is_served_stale(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session.add(
        barcode.to_row("0" + EAN13, PRODUCT, datetime.now(UTC) - timedelta(days=40))
    )
    session.commit()

    def down(code: str) -> None:
        raise barcode.OffUnavailable("timeout")

    monkeypatch.setattr(barcode, "fetch_off", down)

    body = look_up(client, auth_headers, EAN13).json()

    assert body["stale"] is True and body["name"] == "Iaurt grecesc 10%"


@pytest.mark.parametrize("days_old", [None, 200])
def test_without_open_food_facts_and_a_usable_copy_it_is_unavailable(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    days_old: int | None,
) -> None:
    if days_old is not None:
        fetched = datetime.now(UTC) - timedelta(days=days_old)
        session.add(barcode.to_row("0" + EAN13, PRODUCT, fetched))
        session.commit()

    def down(code: str) -> None:
        raise barcode.OffUnavailable("timeout")

    monkeypatch.setattr(barcode, "fetch_off", down)

    response = look_up(client, auth_headers, EAN13)

    assert response.status_code == 503
    assert response.json()["code"] == "barcode_unavailable"


def test_lookups_per_user_are_capped(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    off: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(barcode, "per_user", barcode.PerMinute(2))

    statuses = [look_up(client, auth_headers, EAN13).status_code for _ in range(3)]
    theirs = look_up(client, other_auth_headers, EAN13)

    assert statuses == [200, 200, 429]
    assert theirs.status_code == 200


def test_off_and_without_login(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get(f"/barcode/{EAN13}").status_code == 401
    monkeypatch.setattr(settings, "barcode_enabled", False)
    assert look_up(client, auth_headers, EAN13).status_code == 404


# The HTTP client, against a local server


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        if "redirect" in self.path:
            self.send_response(302)
            self.send_header("Location", "http://example.com/")
            self.end_headers()
            return
        if "huge" in self.path:
            body = b"x" * (barcode.MAX_RESPONSE_BYTES + 10)
        elif "missing" in self.path:
            body = json.dumps({"status": 0}).encode()
        else:
            body = json.dumps({"status": 1, "product": PRODUCT}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def local_off(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(barcode, "OFF_HOST", f"http://127.0.0.1:{server.server_port}")
    yield
    server.shutdown()


@pytest.mark.usefixtures("local_off")
def test_the_client_reads_found_and_missing_products() -> None:
    assert barcode.fetch_off(EAN13)["brands"] == "Olympus"  # type: ignore[index]
    assert barcode.fetch_off("missing") is None


@pytest.mark.usefixtures("local_off")
@pytest.mark.parametrize("path", ["redirect", "huge"])
def test_the_client_never_follows_a_redirect_nor_reads_too_much(path: str) -> None:
    with pytest.raises(barcode.OffUnavailable):
        barcode.fetch_off(path)


def test_the_client_gives_up_on_an_unreachable_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(barcode, "OFF_HOST", "http://127.0.0.1:9")

    with pytest.raises(barcode.OffUnavailable):
        barcode.fetch_off(EAN13)


# Open Food Facts data stays in off_products (Andrei, 14 Nov: never copied
# into our catalog, attributed wherever it appears)


def test_a_lookup_writes_off_products_and_nothing_else(
    client: TestClient, auth_headers: dict[str, str], off: list[str], session: Session
) -> None:
    def counts() -> dict[str, int]:
        return {
            table.name: session.scalar(select(func.count()).select_from(table)) or 0
            for table in Base.metadata.sorted_tables
        }

    before = counts()
    look_up(client, auth_headers, EAN13)
    after = counts()

    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"off_products"}


def test_the_catalog_import_never_reads_open_food_facts_data() -> None:
    import app.catalog_import as catalog_import

    assert "OffProduct" not in vars(catalog_import)
    assert "off_products" not in Path(catalog_import.__file__).read_text()


@pytest.mark.parametrize("stale", [False, True])
def test_every_product_answer_carries_its_attribution(
    client: TestClient,
    auth_headers: dict[str, str],
    off: list[str],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    stale: bool,
) -> None:
    if stale:
        fetched = datetime.now(UTC) - timedelta(days=40)
        session.add(barcode.to_row("0" + EAN13, PRODUCT, fetched))
        session.commit()

        def down(code: str) -> None:
            raise barcode.OffUnavailable("timeout")

        monkeypatch.setattr(barcode, "fetch_off", down)

    body = look_up(client, auth_headers, EAN13).json()

    assert body["stale"] is stale
    assert body["source"]["license"] == "ODbL-1.0"
    assert body["source"]["attribution"] == "Open Food Facts contributors"
    assert body["source"]["url"].startswith("https://world.openfoodfacts.org/")
