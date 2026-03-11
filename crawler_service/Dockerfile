# syntax=docker/dockerfile:1.7-labs

# ==========================================
# STAGE 1: The Graph Resolver (Builder)
# ==========================================
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /workspace

# Dynamically copy the monorepo skeleton to satisfy uv's workspace validation
COPY pyproject.toml uv.lock ./
COPY --parents */pyproject.toml ./

# Export ONLY the crawler's 3rd-party dependencies to a flat file
RUN uv export --package crawler_service --no-emit-workspace --no-dev --locked -o /requirements.txt

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

# 2. OS Dependencies Layer (Playwright/Browsers)
RUN apt-get update && \
    playwright install --with-deps chromium && \
    crawl4ai-setup && \
    crawl4ai-doctor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Application Code Layer
COPY pyproject.toml uv.lock ./
COPY --parents */pyproject.toml ./

COPY shared_lib/ ./shared_lib/
COPY crawler_service/ ./crawler_service/

# Link the local workspace packages
RUN uv pip install -e ./shared_lib -e ./crawler_service

# 4. Permissions & Execution
WORKDIR /workspace/crawler_service
RUN mkdir -p cache && chmod 777 cache

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]