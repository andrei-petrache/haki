"""catalog_sources.estimated on the schema the migrations create."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_the_previous_versions_source_insert_gets_false(db: Session) -> None:
    # The previous version's import names only the columns it knows
    db.execute(
        text(
            "INSERT INTO catalog_sources (key, name, url, license, attribution, "
            "attribution_required, share_alike, version) VALUES ('old-import', "
            "'Old', 'https://example.com', 'CC0-1.0', 'Old', false, false, '1')"
        )
    )

    estimated = db.scalar(
        text("SELECT estimated FROM catalog_sources WHERE key = 'old-import'")
    )
    assert estimated is False
