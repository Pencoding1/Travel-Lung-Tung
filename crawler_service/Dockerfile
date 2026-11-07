# syntax=docker/dockerfile:1.7-labs
#
# Crawler Service Dockerfile (`app.main:app` on port 8004).
# Uses standalone uv pip installation so the root `uv.lock` for the 4 core
# workspace members (`shared_lib`, `backend_service`, `POI_service`, `ai_service`)
# remains strictly locked (`--locked`).

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_SYSTEM_PYTHON=1
ENV UV_CACHE_DIR=/root/.cache/uv

WORKDIR /workspace

COPY shared_lib/ ./shared_lib/
COPY crawler_service/ ./crawler_service/

# 1. Install shared_lib and crawler_service dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -e ./shared_lib -e ./crawler_service

# 2. OS Dependencies Layer (Playwright/Browsers)
RUN apt-get update && \
    playwright install --with-deps chromium && \
    crawl4ai-setup && \
    crawl4ai-doctor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Permissions & Execution
WORKDIR /workspace/crawler_service
RUN mkdir -p cache logs

EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8004/', timeout=3)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
