# Haki backend image. Build from the backend/ directory:
#   docker build -t haki-backend:dev .
# Configuration (DATABASE_URL, JWT_SECRET_KEY, ...) comes only from environment
# variables at runtime; nothing secret is baked into the image.

# ---- Builder: install runtime dependencies into a virtual environment ----
FROM python:3.14.4-slim-trixie AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Requirements before code: this layer is rebuilt only when dependencies change.
# requirements.txt is the lock: every package pinned, each with its hashes.
# --require-hashes refuses any file whose hash differs; --no-deps refuses any
# package that is not in the lock.
COPY requirements.txt .
RUN pip install --require-hashes --no-deps -r requirements.txt

# ---- Runtime: only the venv and the code, no build tooling ----
FROM python:3.14.4-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Fixed numeric ids, so Kubernetes can verify runAsNonRoot
RUN groupadd --system --gid 10001 haki \
    && useradd --system --uid 10001 --gid haki --no-create-home \
       --shell /usr/sbin/nologin haki

WORKDIR /app

# Owned by root and only readable by the app user: the app cannot modify itself
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

USER 10001:10001

EXPOSE 8000

# Migrations are not run here; they run as a separate one-off step
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
