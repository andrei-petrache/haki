import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.auth import router as auth_router
from app.body import router as body_router
from app.catalog import router as catalog_router
from app.config import settings
from app.consent import router as consent_router
from app.dashboard import router as dashboard_router
from app.db import database_is_reachable
from app.entries import router as entries_router
from app.errors import ErrorCode, error_response, install_error_handlers
from app.exercises import router as exercises_router
from app.export import router as export_router
from app.features import router as features_router
from app.food_search import router as food_search_router
from app.foods import router as foods_router
from app.metrics import record_request, start_metrics_server
from app.password_reset import router as password_reset_router
from app.programs import router as programs_router
from app.security import HashingBusy
from app.summary import router as summary_router
from app.workouts import router as workouts_router

logger = logging.getLogger(__name__)

# Shown in /docs and /openapi.json. Without it FastAPI reports its default,
# "0.1.0", which looks like the v0.1.0 release. The last release is v0.1.1;
# Workouts came after it, so this is the next minor, not released yet.
API_VERSION = "0.2.0.dev0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Serve the metrics on their own port while the API runs (app/metrics.py)."""
    server = None
    if settings.metrics_port:
        server = start_metrics_server(settings.metrics_port)
    app.state.metrics_server = server
    try:
        yield
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


app = FastAPI(title="Haki API", version=API_VERSION, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(foods_router)
app.include_router(food_search_router)
app.include_router(entries_router)
app.include_router(summary_router)
app.include_router(exercises_router)
app.include_router(workouts_router)
app.include_router(programs_router)
app.include_router(catalog_router)
app.include_router(body_router)
app.include_router(password_reset_router)
app.include_router(export_router)
app.include_router(features_router)
app.include_router(consent_router)
app.include_router(dashboard_router)
# Every HTTPException and every 422 answers {"detail", "code"} (app/errors.py)
install_error_handlers(app)
# Outermost: it also counts responses from the exception handlers below
app.middleware("http")(record_request)


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
    return error_response(ErrorCode.DATABASE_UNAVAILABLE, headers={"Retry-After": "5"})


@app.exception_handler(HashingBusy)
def hashing_busy(request: Request, exc: Exception) -> JSONResponse:
    """Answer 503 when every password hashing slot stayed busy.

    The server is overloaded as a whole, not this one client: that is a 503
    (try again shortly), not a 429 (you sent too many requests).
    """
    logger.warning("All password hashing slots busy during %s", request.url.path)
    return error_response(ErrorCode.SERVER_BUSY, headers={"Retry-After": "2"})


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
