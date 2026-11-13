"""The erasure log, and how a restore applies it again.

Deleting an account, or withdrawing the health-data consent (which deletes
that data), writes a row to `erasures` in the same transaction: the user's
id and created_at, the kind, and when. A dump taken before an erasure still
holds what was erased; restoring it would bring that back. So a restore runs
`reapply` with the log of the live database, before any traffic, and erases
it all again (decisions.md, 12 and 13 November).

The log is part of the database, so a restore overwrites it too: it must be
copied out before (`export`), and kept outside the database, newer than any
dump. How and where is the backup design (ops); this module gives the two
steps:

    python -m app.erasures export erasures.jsonl     # from the live database
    python -m app.erasures reapply erasures.jsonl    # on the restored one

A row erases only where both the id and created_at match: a restore sets
the id sequence back, so an id from the log may since belong to someone
new. Applying the log twice changes nothing the second time.
"""

import json
import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, exists, select, update
from sqlalchemy.orm import Session

from app.models import BodyWeight, Consent, Erasure, TdeeEstimate, User

logger = logging.getLogger("app.erasures")

FIELDS = ("user_id", "user_created_at", "kind", "purpose", "erased_at")


@dataclass
class Counts:
    accounts: int = 0
    consents: int = 0
    health_rows: int = 0
    logged: int = 0


def read_log(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(select(Erasure).order_by(Erasure.erased_at, Erasure.id))
    return [
        {
            "user_id": row.user_id,
            "user_created_at": row.user_created_at.isoformat(),
            "kind": row.kind,
            "purpose": row.purpose,
            "erased_at": row.erased_at.isoformat(),
        }
        for row in rows
    ]


def parse(entry: dict[str, Any]) -> dict[str, Any]:
    if set(entry) != set(FIELDS):
        raise ValueError(f"an erasure entry has the fields {FIELDS}: {entry}")
    return entry | {
        "user_created_at": datetime.fromisoformat(entry["user_created_at"]),
        "erased_at": datetime.fromisoformat(entry["erased_at"]),
    }


def utc(moment: datetime) -> datetime:
    """A moment as an aware UTC datetime. SQLite returns times without their
    zone; they are UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def reapply(session: Session, entries: Iterable[dict[str, Any]]) -> Counts:
    """Erase again everything the log says was erased, oldest first, and put
    the entries the restored log lacks back into it. One transaction."""
    counts = Counts()
    parsed = sorted((parse(entry) for entry in entries), key=lambda e: e["erased_at"])
    for entry in parsed:
        user_id, at = entry["user_id"], entry["erased_at"]
        user = session.get(User, user_id)
        # The same account only if it was created at the same moment
        if user is not None and utc(user.created_at) != utc(entry["user_created_at"]):
            user = None
        if entry["kind"] == "account":
            if user is not None:
                session.delete(user)
                session.flush()
                counts.accounts += 1
        elif user is not None:
            counts.consents += reapply_withdrawal(session, user, entry["purpose"], at)
            for model in (BodyWeight, TdeeEstimate):
                result = session.execute(
                    delete(model).where(
                        model.user_id == user.id, model.created_at <= at
                    )
                )
                counts.health_rows += result.rowcount or 0
        known = session.scalar(
            select(
                exists().where(
                    Erasure.user_id == user_id,
                    Erasure.kind == entry["kind"],
                    Erasure.erased_at == at,
                )
            )
        )
        if not known:
            session.add(Erasure(**entry))
            counts.logged += 1
    session.commit()
    return counts


def reapply_withdrawal(session: Session, user: User, purpose: str, at: datetime) -> int:
    """Mark withdrawn the consents given before `at`; back to the user's own
    target unless a consent given after `at` is still standing."""
    result = session.execute(
        update(Consent)
        .where(
            Consent.user_id == user.id,
            Consent.purpose == purpose,
            Consent.withdrawn_at.is_(None),
            Consent.given_at <= at,
        )
        .values(withdrawn_at=at)
    )
    standing = session.scalar(
        select(
            exists().where(
                Consent.user_id == user.id,
                Consent.purpose == purpose,
                Consent.withdrawn_at.is_(None),
            )
        )
    )
    if not standing:
        user.target_mode = "manual"
    return result.rowcount or 0


def main(argv: list[str]) -> int:
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(argv) != 2 or argv[0] not in {"export", "reapply"}:
        print("usage: python -m app.erasures export|reapply FILE", file=sys.stderr)
        return 2
    command, path = argv[0], Path(argv[1])
    with SessionLocal() as session:
        if command == "export":
            lines = [json.dumps(entry) for entry in read_log(session)]
            path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
            logger.info("%d erasures written to %s", len(lines), path)
            return 0
        entries = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        counts = reapply(session, entries)
    logger.info(
        "erased again: %d accounts, %d consents withdrawn, %d health rows; "
        "%d entries added to the log",
        counts.accounts,
        counts.consents,
        counts.health_rows,
        counts.logged,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
