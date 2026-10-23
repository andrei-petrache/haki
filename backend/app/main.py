from fastapi import FastAPI
app = FastAPI(title="Haki API")

@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: confirms the process is up and responding."""
    return {"status": "ok"}
    