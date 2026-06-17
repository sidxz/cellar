FROM python:3.13-slim

WORKDIR /app

# RDKit's drawing extension (rdMolDraw2D) links against these system libs;
# the slim base omits them, so the app fails to import at runtime without them.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    libxrender1 \
    libxext6 \
    libx11-6 \
    libexpat1 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies first (layer caching) — project itself not yet installed
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code, then install the project so `cellar` is importable
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
RUN uv sync --frozen --no-dev

RUN adduser --disabled-password --uid 1000 cellar
USER cellar

# Build identity — injected by CI from the git tag (see publish-images.yml).
# Defaults keep local `docker build` runs honest about being unversioned.
ARG APP_VERSION=0.0.0+dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ENV CELLAR_VERSION=$APP_VERSION \
    CELLAR_GIT_SHA=$GIT_SHA \
    CELLAR_BUILD_DATE=$BUILD_DATE

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD [".venv/bin/uvicorn", "cellar.interface.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
