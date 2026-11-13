"""Which optional features this server has turned on, for clients to know
before anyone types: the login screen shows "Forgot password?" only when
the reset works. Public and cacheable: it says nothing about any user."""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.config import settings

router = APIRouter(tags=["features"])

# Flags change only with a deploy: a minute of caching is harmless
CACHE_SECONDS = 60


class FeaturesResponse(BaseModel):
    password_reset: bool
    body_weight: bool
    export: bool


@router.get("/features", response_model=FeaturesResponse)
def features(response: Response) -> FeaturesResponse:
    """The optional features on this server; no login needed."""
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return FeaturesResponse(
        password_reset=settings.password_reset_enabled,
        body_weight=settings.body_weight_enabled,
        # The export is a right (GDPR Art. 15 and 20): always on
        export=True,
    )
