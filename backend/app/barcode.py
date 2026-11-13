"""Barcode lookup through Open Food Facts (phase 5).

GET /barcode/{code} answers a product's name and nutrients per 100 g, from
Open Food Facts, credited, under the ODbL. It creates no food: the client
fills the usual "new food" form with it and the user saves their own food.

Products are cached in `off_products`, a database of their own: what Open
Food Facts gave, unmodified, never mixed with our catalog or users' foods,
and published as it is on request (ODbL share-alike). Only products found
are stored; a code Open Food Facts lacks is remembered for a day in memory,
so made-up codes cannot grow the table.

The call to Open Food Facts goes to one fixed host, with no redirects, a 5 s
timeout and at most 512 KB read; the path holds only digits. Calls are
capped per pod (OFF_REQUESTS_PER_MINUTE, 45 by default: Open Food Facts
allows 100 a minute per address, and the pods share one), and lookups per
user and pod (30 a minute). Both caps live in memory: with N pods they
allow N times as much, still a fixed bound. When Open Food Facts cannot be
reached, a cached product up to 180 days old is served, marked stale.

No barcode is ever logged: what a person scans is what they eat.
"""

import json
import math
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.config import settings
from app.errors import ApiError, ErrorCode
from app.models import OffProduct
from app.schemas import MAX_CALORIES_PER_100G

OFF_HOST = "https://world.openfoodfacts.org"
FIELDS = (
    "code,product_name,product_name_en,product_name_ro,brands,quantity,"
    "nutriments,last_modified_t"
)
USER_AGENT = "Haki/0.2 (open-source nutrition app)"
TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 512 * 1024
FRESH = timedelta(days=30)
STALE_AT_MOST = timedelta(days=180)
NOT_FOUND_FOR = timedelta(days=1)
NOT_FOUND_MAX = 10_000
LOOKUPS_PER_USER_PER_MINUTE = 30
SOURCE = {
    "key": "open-food-facts",
    "license": "ODbL-1.0",
    "attribution": "Open Food Facts contributors",
}


def require_enabled() -> None:
    """Off, the endpoint answers as if it did not exist."""
    if not settings.barcode_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(
    prefix="/barcode", tags=["barcode"], dependencies=[Depends(require_enabled)]
)


# Codes


def check_digit_ok(digits: str) -> bool:
    """GS1 mod 10: from the right, the digits before the check digit weigh
    3, 1, 3, 1..."""
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize(code: str) -> str:
    """The code as a GTIN-14 (zero-padded), so a UPC-A and the EAN-13 that
    is the same product share one cache entry. 422 for anything else."""
    if not code.isascii() or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        raise ApiError(ErrorCode.INVALID_BARCODE)
    if not check_digit_ok(code):
        raise ApiError(ErrorCode.INVALID_BARCODE)
    return code.zfill(14)


def off_code(gtin: str) -> str:
    """The form Open Food Facts files a product under: EAN-8 for a padded
    EAN-8, else EAN-13 when the GTIN-14 starts with 0."""
    if gtin.startswith("000000"):
        return gtin[6:]
    return gtin[1:] if gtin.startswith("0") else gtin


# Limits, in memory per pod


class PerMinute:
    """At most `limit` events a minute per key (a sliding window)."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.lock = threading.Lock()
        self.events: dict[Any, deque[float]] = {}

    def take(self, key: Any = None) -> bool:
        now = time.monotonic()
        with self.lock:
            window = self.events.setdefault(key, deque())
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= self.limit:
                return False
            window.append(now)
            return True


per_user = PerMinute(LOOKUPS_PER_USER_PER_MINUTE)
toward_off = PerMinute(settings.off_requests_per_minute)


class NotFound:
    """Codes Open Food Facts lacks, for a day; the oldest go first past the cap."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.until: OrderedDict[str, float] = OrderedDict()

    def add(self, gtin: str) -> None:
        with self.lock:
            self.until[gtin] = time.monotonic() + NOT_FOUND_FOR.total_seconds()
            self.until.move_to_end(gtin)
            while len(self.until) > NOT_FOUND_MAX:
                self.until.popitem(last=False)

    def __contains__(self, gtin: object) -> bool:
        with self.lock:
            expiry = self.until.get(gtin)  # type: ignore[arg-type]
            if expiry is None:
                return False
            if expiry < time.monotonic():
                del self.until[gtin]  # type: ignore[arg-type]
                return False
            return True


not_found = NotFound()


# Open Food Facts


class OffUnavailable(Exception):
    """Open Food Facts could not answer: down, slow, too big or garbled."""


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


opener = urllib.request.build_opener(NoRedirects)


def fetch_off(code: str) -> dict[str, Any] | None:
    """The product's JSON from Open Food Facts, or None if it has none.
    `code` holds digits only (normalize), so the URL can name nothing else."""
    url = f"{OFF_HOST}/api/v2/product/{code}?fields={FIELDS}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise OffUnavailable(f"HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise OffUnavailable(type(error).__name__) from error
    if len(body) > MAX_RESPONSE_BYTES:
        raise OffUnavailable("response too large")
    try:
        data = json.loads(body)
    except ValueError as error:
        raise OffUnavailable("not JSON") from error
    if not isinstance(data, dict):
        raise OffUnavailable("not an object")
    product = data.get("product")
    if data.get("status") != 1 or not isinstance(product, dict):
        return None
    return product


def number(value: Any) -> float | None:
    """A finite number from Open Food Facts' field, or None."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except TypeError, ValueError:
        return None
    return result if math.isfinite(result) else None


def text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:limit]


def to_row(gtin: str, product: dict[str, Any], now: datetime) -> OffProduct:
    """What Open Food Facts gave, as it gave it (cut to the columns only)."""
    nutriments = product.get("nutriments")
    if not isinstance(nutriments, dict):
        nutriments = {}
    kcal = number(nutriments.get("energy-kcal_100g"))
    if kcal is None:
        kilojoules = number(nutriments.get("energy-kj_100g"))
        kcal = None if kilojoules is None else kilojoules / 4.184
    modified = number(product.get("last_modified_t"))
    return OffProduct(
        gtin=gtin,
        name=text(product.get("product_name"), 200)
        or text(product.get("product_name_en"), 200),
        name_ro=text(product.get("product_name_ro"), 200),
        brand=text(product.get("brands"), 200),
        quantity=text(product.get("quantity"), 100),
        calories_per_100g=kcal,
        protein_per_100g=number(nutriments.get("proteins_100g")),
        carbs_per_100g=number(nutriments.get("carbohydrates_100g")),
        fat_per_100g=number(nutriments.get("fat_100g")),
        off_last_modified=None if modified is None else int(modified),
        fetched_at=now,
    )


# The answer


class Source(BaseModel):
    key: str
    license: str
    attribution: str
    url: str


class BarcodeResponse(BaseModel):
    barcode: str
    name: str | None
    name_ro: str | None
    brand: str | None
    quantity: str | None
    # Each null when Open Food Facts lacks it or it is outside what a food
    # may hold (out_of_range names those): the form never gets a value
    # POST /foods would refuse
    calories_per_100g: float | None
    protein_per_100g: float | None
    carbs_per_100g: float | None
    fat_per_100g: float | None
    # All four values present
    complete: bool
    out_of_range: list[str]
    # Open Food Facts could not be reached: this is the copy we had
    stale: bool
    fetched_at: datetime
    source: Source


def to_response(row: OffProduct, stale: bool) -> BarcodeResponse:
    values = {
        "calories_per_100g": row.calories_per_100g,
        "protein_per_100g": row.protein_per_100g,
        "carbs_per_100g": row.carbs_per_100g,
        "fat_per_100g": row.fat_per_100g,
    }
    bounds = {"calories_per_100g": MAX_CALORIES_PER_100G}
    out = [
        field
        for field, value in values.items()
        if value is not None and not 0 <= value <= bounds.get(field, 100)
    ]
    macros = ("protein_per_100g", "carbs_per_100g", "fat_per_100g")
    if sum(values[m] or 0 for m in macros) > 100:
        out += [m for m in macros if values[m] is not None and m not in out]
    for field in out:
        values[field] = None
    code = off_code(row.gtin)
    return BarcodeResponse(
        barcode=code,
        name=row.name,
        name_ro=row.name_ro,
        brand=row.brand,
        quantity=row.quantity,
        **values,
        complete=all(value is not None for value in values.values()),
        out_of_range=out,
        stale=stale,
        fetched_at=row.fetched_at,
        source=Source(**SOURCE, url=f"{OFF_HOST}/product/{code}"),
    )


def age(row: OffProduct, now: datetime) -> timedelta:
    fetched = row.fetched_at
    if fetched.tzinfo is None:  # SQLite drops the zone; it is UTC
        fetched = fetched.replace(tzinfo=UTC)
    return now - fetched


def stale_or_unavailable(row: OffProduct | None, now: datetime) -> BarcodeResponse:
    if row is not None and age(row, now) <= STALE_AT_MOST:
        return to_response(row, stale=True)
    raise ApiError(ErrorCode.BARCODE_UNAVAILABLE)


def save(session: Session, row: OffProduct) -> OffProduct:
    """Insert or refresh the product; two lookups at once keep one row."""
    merged = session.merge(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        merged = session.merge(row)
        session.commit()
    return merged


@router.get("/{code}", response_model=BarcodeResponse)
def look_up(
    code: str, current_user: CurrentUser, session: SessionDep
) -> BarcodeResponse:
    """A product by its barcode (EAN-8, UPC-A, EAN-13 or GTIN-14)."""
    gtin = normalize(code)
    if not per_user.take(current_user.id):
        raise ApiError(ErrorCode.BARCODE_RATE_LIMITED)
    now = datetime.now(UTC)
    row = session.get(OffProduct, gtin)
    if row is not None and age(row, now) < FRESH:
        return to_response(row, stale=False)
    if gtin in not_found:
        raise ApiError(ErrorCode.PRODUCT_NOT_FOUND)
    if not toward_off.take():
        return stale_or_unavailable(row, now)
    try:
        product = fetch_off(off_code(gtin))
    except OffUnavailable:
        return stale_or_unavailable(row, now)
    if product is None:
        not_found.add(gtin)
        if row is not None:
            session.delete(row)
            session.commit()
        raise ApiError(ErrorCode.PRODUCT_NOT_FOUND)
    return to_response(save(session, to_row(gtin, product, now)), stale=False)
