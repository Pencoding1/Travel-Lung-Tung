# syntax=docker/dockerfile:1.7-labs
#
# backend_service image (OC-030).
#
# Runs the authenticated itinerary-draft FastAPI app (`app.main:app`) on the
# documented port 8003, using the same production dependency/build pattern as the
# other services: locked workspace export -> cached `uv pip install` -> editable
# workspace installs.
#
# NOTE: backend_service is NOT wired into the production docker-compose.yaml. It
# is wired only into the standalone, isolated integration stack
# (docker-compose.integration.yaml), which owns its own port and volume and never
# mounts a historical/production volume.

# ==========================================
# STAGE 1: The Graph Resolver (Builder)
# ==========================================
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY --parents */pyproject.toml ./

# Export ONLY the backend dependencies
RUN uv export --package backend_service --no-emit-workspace --no-dev --locked -o /requirements.txt

# ==========================================
# STAGE 2: The Production Image
# ==========================================
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_SYSTEM_PYTHON=1 
ENV UV_CACHE_DIR=/root/.cache/uv 

WORKDIR /workspace

# 1. Cache-Mounted Dependency Layer
COPY --from=builder /requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r requirements.txt

# 2. Application Code Layer
COPY pyproject.toml uv.lock ./
COPY --parents */pyproject.toml ./

COPY shared_lib/ ./shared_lib/
COPY backend_service/ ./backend_service/

RUN uv pip install -e ./shared_lib -e ./backend_service

# 3. Execution
WORKDIR /workspace/backend_service

EXPOSE 8003

# Liveness only. `/health` is independent of durable storage and makes no
# readiness claim (that is `/ready`); a missing store still reports liveness.
# Dependency-free: Python stdlib only, no extra tooling in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8003/health', timeout=3); sys.exit(0)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
