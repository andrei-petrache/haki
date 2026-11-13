"""Consent to health data (GDPR Art. 7 and 9): body weight and the adaptive
calorie target need it, on top of their flag.

Each purpose has a current version, whose text lives in app/consent_texts/
in every language and never changes (tests/test_consent.py pins its hash):
a material change (purpose, data, recipients) gets a new version, and
everyone is asked again. A consent is valid while the latest one given
for the purpose is not withdrawn and is of the current version.

Withdrawing is as easy as giving (no password), and deletes the health
data at once, in the same transaction, with a row in the erasure log so
that a restore from an older dump deletes it again (app/erasures.py).

Writes behind the consent (a weigh-in, the goal, the week's estimate) hold
the user's row FOR SHARE and check the consent under that lock; withdrawing
holds it FOR UPDATE. So a weigh-in sent while the consent is withdrawn is
either written before the deletion, and deleted with it, or refused.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, SessionDep
from app.config import settings
from app.errors import ApiError, ErrorCode
from app.models import BodyWeight, Consent, Erasure, TdeeEstimate, User

Purpose = Literal["health_data"]
Locale = Literal["en", "ro"]
CURRENT_VERSIONS: dict[str, str] = {"health_data": "v1"}
TEXTS = Path(__file__).parent / "consent_texts"


def require_enabled() -> None:
    """Off with body weight, as if it did not exist: the purpose is its data."""
    if not settings.body_weight_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(
    prefix="/auth/me/consents",
    tags=["consent"],
    dependencies=[Depends(require_enabled)],
)


def consent_text(purpose: str, version: str, locale: str) -> str:
    return (TEXTS / f"{purpose}-{version}.{locale}.md").read_text(encoding="utf-8")


def text_sha256(purpose: str, version: str, locale: str) -> str:
    text = consent_text(purpose, version, locale).encode("utf-8")
    return hashlib.sha256(text).hexdigest()


def latest(session: Session, user: User, purpose: str) -> Consent | None:
    query = (
        select(Consent)
        .where(Consent.user_id == user.id, Consent.purpose == purpose)
        .order_by(Consent.given_at.desc(), Consent.id.desc())
        .limit(1)
    )
    return session.scalar(query)


def is_valid(consent: Consent | None, purpose: str) -> bool:
    return (
        consent is not None
        and consent.withdrawn_at is None
        and consent.version == CURRENT_VERSIONS[purpose]
    )


def has_consent(session: Session, user: User, purpose: str = "health_data") -> bool:
    return is_valid(latest(session, user, purpose), purpose)


def lock_user(session: Session, user: User, *, share: bool) -> None:
    """Hold the user's row until the commit: FOR SHARE for a write behind a
    consent, FOR UPDATE to withdraw one (no-ops on SQLite)."""
    query = select(User.id).where(User.id == user.id)
    session.execute(query.with_for_update(read=share))


def require_consent(
    session: Session, user: User, *, write: bool, purpose: str = "health_data"
) -> None:
    """403 consent_required without a valid consent. A write first takes the
    lock that a withdrawal waits for, then checks under it."""
    if write:
        lock_user(session, user, share=True)
    if not has_consent(session, user, purpose):
        raise ApiError(ErrorCode.CONSENT_REQUIRED)


class ConsentText(BaseModel):
    purpose: str
    version: str
    locale: str
    text: str
    sha256: str


class ConsentStatus(BaseModel):
    purpose: str
    required_version: str
    valid: bool
    # The latest one given, withdrawn or not; null if never given
    given_version: str | None
    given_at: datetime | None
    withdrawn_at: datetime | None


class ConsentIn(BaseModel):
    version: str
    # The language the text was shown in
    locale: Locale


def status_of(session: Session, user: User, purpose: str) -> ConsentStatus:
    found = latest(session, user, purpose)
    return ConsentStatus(
        purpose=purpose,
        required_version=CURRENT_VERSIONS[purpose],
        valid=is_valid(found, purpose),
        given_version=None if found is None else found.version,
        given_at=None if found is None else found.given_at,
        withdrawn_at=None if found is None else found.withdrawn_at,
    )


@router.get("/{purpose}/text", response_model=ConsentText)
def read_text(
    purpose: Purpose, current_user: CurrentUser, locale: Locale = "en"
) -> ConsentText:
    """The text to show before asking, in the current version."""
    version = CURRENT_VERSIONS[purpose]
    return ConsentText(
        purpose=purpose,
        version=version,
        locale=locale,
        text=consent_text(purpose, version, locale),
        sha256=text_sha256(purpose, version, locale),
    )


@router.get("/{purpose}", response_model=ConsentStatus)
def read_consent(
    purpose: Purpose, current_user: CurrentUser, session: SessionDep
) -> ConsentStatus:
    return status_of(session, current_user, purpose)


@router.put("/{purpose}", response_model=ConsentStatus)
def give_consent(
    purpose: Purpose, data: ConsentIn, current_user: CurrentUser, session: SessionDep
) -> ConsentStatus:
    """Give the consent to the text of `version` in `locale`. 409
    consent_version_outdated if the version is not the current one (the
    client showed an old text). Giving it again while valid changes nothing.
    """
    if data.version != CURRENT_VERSIONS[purpose]:
        raise ApiError(ErrorCode.CONSENT_VERSION_OUTDATED)
    lock_user(session, current_user, share=False)
    if not has_consent(session, current_user, purpose):
        session.add(
            Consent(
                user_id=current_user.id,
                purpose=purpose,
                version=data.version,
                locale=data.locale,
                text_sha256=text_sha256(purpose, data.version, data.locale),
                given_at=datetime.now(UTC),
            )
        )
    session.commit()
    return status_of(session, current_user, purpose)


@router.delete("/{purpose}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_consent(
    purpose: Purpose, current_user: CurrentUser, session: SessionDep
) -> Response:
    """Withdraw the consent and delete the health data it covered, at once.

    No password: withdrawing must be as easy as giving (Art. 7(3)). The
    weigh-ins and estimates are deleted, the target goes back to the
    user's own number, and the erasure log keeps what a restore must
    delete again. Withdrawing without a consent is harmless (still 204).
    """
    lock_user(session, current_user, share=False)
    now = datetime.now(UTC)
    withdrawn = session.scalars(
        select(Consent).where(
            Consent.user_id == current_user.id,
            Consent.purpose == purpose,
            Consent.withdrawn_at.is_(None),
        )
    ).all()
    for consent in withdrawn:
        consent.withdrawn_at = now
    deleted = 0
    for model in (BodyWeight, TdeeEstimate):
        result = session.execute(delete(model).where(model.user_id == current_user.id))
        deleted += result.rowcount or 0
    current_user.target_mode = "manual"
    if withdrawn or deleted:
        session.add(
            Erasure(
                user_id=current_user.id,
                user_created_at=current_user.created_at,
                kind="consent",
                purpose=purpose,
                erased_at=now,
            )
        )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
