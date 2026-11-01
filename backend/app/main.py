import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.auth import router as auth_router
from app.db import database_is_reachable
from app.entries import router as entries_router
from app.foods import router as foods_router
from app.security import HashingBusy
from app.summary import router as summary_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Haki API")
app.include_router(auth_router)
app.include_router(foods_router)
app.include_router(entries_router)
app.include_router(summary_router)


@app.exception_handler(OperationalError)
@app.exception_handler(PoolTimeoutError)
def database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Answer 503 instead of 500 when the database can't be reached.

    503 tells clients (and load balancers) the problem is temporary and on
    our side. The full error goes to the server log, never to the client.
    """
    logger.error(
        "Database unavailable during %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Service temporarily unavailable, try again shortly"},
        headers={"Retry-After": "5"},
    )


@app.exception_handler(HashingBusy)
def hashing_busy(request: Request, exc: Exception) -> JSONResponse:
    """Answer 503 when every password hashing slot stayed busy.

    The server is overloaded as a whole, not this one client: that is a 503
    (try again shortly), not a 429 (you sent too many requests).
    """
    logger.warning("All password hashing slots busy during %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Server busy, try again shortly"},
        headers={"Retry-After": "2"},
    )


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
