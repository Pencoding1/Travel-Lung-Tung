# Use a slim Python 3.12 image as the base
FROM python:3.12-slim-bookworm

# Install 'uv' directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 1. Set the working directory for the entire monorepo context
WORKDIR /workspace

# 2. Copy the ROOT workspace files (Crucial for workspace resolution)
COPY pyproject.toml uv.lock ./

# 3. Copy the full directories for BOTH projects
# (Since crawler_service doesn't have a strict [build-system], uv needs the files present)
COPY shared_lib/ ./shared_lib/
COPY crawler_service/ ./crawler_service/

# 4. Switch into the crawler service directory
WORKDIR /workspace/crawler_service

# 5. Sync dependencies exactly like you do locally
# uv will detect it's in a workspace, find the root lockfile, and link travel-shared
RUN uv sync --no-dev

# 6. Install Playwright system dependencies and Chromium
RUN uv run crawl4ai-setup
RUN uv run crawl4ai-doctor
RUN uv run playwright install --with-deps chromium

# Expose the port your FastAPI instance will run on
EXPOSE 8001

# Start the FastAPI server
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]