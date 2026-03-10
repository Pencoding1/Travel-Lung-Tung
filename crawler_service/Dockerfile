# Use a slim Python 3.12 image as the base
FROM python:3.12-slim-bookworm

# Install 'uv' directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory for the entire monorepo context
WORKDIR /workspace

# 1. Copy the root workspace file
COPY pyproject.toml ./

# 2. Copy the shared library
COPY shared_lib/ ./shared_lib/

# 3. Copy only the crawler pyproject to cache dependencies
COPY crawler_service/pyproject.toml ./crawler_service/

# Switch to the crawler service directory
WORKDIR /workspace/crawler_service

# 4. Sync dependencies using uv (this installs FastAPI, crawl4ai, travel-shared, etc.)
RUN uv sync --no-dev

# 5. Install Playwright system dependencies and Chromium
# This is absolutely critical for crawl4ai to run without crashing in Docker
RUN uv run crawl4ai-setup
RUN uv run crawl4ai-doctor
RUN uv run playwright install --with-deps chromium

# 6. Copy the rest of your crawler source code (js_codes, pipelines, config, etc.)
COPY crawler_service/ ./

# Expose the port your FastAPI instance will run on
EXPOSE 8001

# Start the FastAPI server using uv to run uvicorn
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]