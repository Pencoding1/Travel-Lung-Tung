# syntax=docker/dockerfile:1.7-labs

# ==========================================
# STAGE 1: The Graph Resolver (Builder)
# ==========================================
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY --parents */pyproject.toml ./

# Export ONLY the data ingestion dependencies
RUN uv export --package POI_service --no-emit-workspace --no-dev --locked -o /requirements.txt

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
COPY POI_service/ ./POI_service/

RUN uv pip install -e ./shared_lib -e ./POI_service

# 3. Execution
WORKDIR /workspace/POI_service

EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]