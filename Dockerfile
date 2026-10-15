# syntax=docker/dockerfile:1

# --- Build: install dependencies and the app into /app/.venv -----------------
FROM python:3.13-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv

# No precompiled bytecode: 70 MB smaller, startup time measured the same
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project --no-editable

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

RUN set -eux; \
    site=/app/.venv/lib/python3.13/site-packages; \
    find "$site" -depth -type d \( -name tests -o -name test \) -exec rm -rf {} +; \
    find "$site/botocore/data" -mindepth 1 -maxdepth 1 -type d \
        ! -name s3 ! -name sts ! -name sso ! -name sso-oidc ! -name signin -exec rm -rf {} +; \
    rm -rf "$site/plotly/labextension" "$site/plotly/package_data/widgetbundle.js"; \
    rm -rf "$site/faker" "$site"/faker-*.dist-info "$site/polyfactory" "$site"/polyfactory-*.dist-info

COPY docker/smoke_check.py /tmp/smoke_check.py
RUN /app/.venv/bin/python /tmp/smoke_check.py

# --- Runtime -------------------------------------------------------------------
FROM python:3.13-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/.nicegui /app/backups \
    && chown app /app /app/.nicegui /app/backups

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY alembic/ ./alembic/

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8080')}/api/readyz\", timeout=4)"]

CMD ["family-hub"]
