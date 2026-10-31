from typing import Annotated

from fastapi import Depends, FastAPI, Response, status

from app.auth import router as auth_router
from app.db import database_is_reachable
from app.foods import router as foods_router

app = FastAPI(title="Haki API")
app.include_router(auth_router)
app.include_router(foods_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: confirms the process is up and responding.

    Deliberately does not touch the database: a database outage should
    stop traffic to the app (readiness), not restart it (liveness).
    """
    return {"status": "ok"}


@app.get("/ready")
def ready(
    response: Response,
    database_ok: Annotated[bool, Depends(database_is_reachable)],
) -> dict[str, str]:
    """Readiness check: confirms the app can serve traffic."""
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not ready", "database": "unreachable"}
    return {"status": "ready", "database": "ok"}
