"""Prometheus metrics for HTTP requests, on a port of their own.

Labels use the route template ("/workouts/{workout_id}"), never the raw
path, so ids in URLs cannot create new time series. A request that matches
no route is labelled "unmatched".

Why a second port (METRICS_PORT, 9000) and not a route on 8000: the
frontend's Nginx forwards /api/* to port 8000 with the prefix stripped, so
a /metrics route there would be public as /api/metrics. Nginx and the
Service know only 8000; Prometheus scrapes the pod's 9000 directly, from
inside the cluster. The API app itself has no /metrics.

Single process: uvicorn runs one worker in the image (no --workers), so the
default registry is enough. With several workers each would count alone,
and prometheus_client's multiprocess mode (PROMETHEUS_MULTIPROC_DIR) would
be needed.
"""

import time
from collections.abc import Awaitable, Callable
from wsgiref.simple_server import WSGIServer

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, start_http_server
from starlette.routing import BaseRoute

UNMATCHED = "unmatched"

REQUESTS = Counter(
    "haki_http_requests_total",
    "HTTP requests handled by the backend.",
    ["method", "route", "status"],
)
DURATION = Histogram(
    "haki_http_request_duration_seconds",
    "Time to handle an HTTP request, until the response starts.",
    ["method", "route"],
    # From a cached read to a slow Argon2 hash (64 MiB, about 0.1-0.5 s)
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def route_template(request: Request) -> str:
    """The matched route's path template, or "unmatched"."""
    route: BaseRoute | None = request.scope.get("route")
    return getattr(route, "path", None) or UNMATCHED


async def record_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware: count the request and time it, by route template."""
    start = time.perf_counter()
    status = 500  # if the app raises, the client gets a 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = route_template(request)
        DURATION.labels(request.method, route).observe(time.perf_counter() - start)
        REQUESTS.labels(request.method, route, str(status)).inc()


def start_metrics_server(port: int) -> WSGIServer:
    """Serve every metric at /metrics on `port`, in a background thread.

    Stop it with shutdown() and server_close().
    """
    server, _thread = start_http_server(port)
    return server
