from fastapi import FastAPI

app = FastAPI(title="Haki API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: confirms the process is up and responding."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Readiness check: confirms the app can serve traffic.

    Will also verify the database connection once PostgreSQL is added.
    """
    return {"status": "ready"}
