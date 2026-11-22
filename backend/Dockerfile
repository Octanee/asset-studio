# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app /data
USER app
ENV PATH="/app/.venv/bin:$PATH" ASSET_STUDIO_DATA_DIR=/data
EXPOSE 8400
CMD ["uvicorn", "asset_studio.main:app", "--host", "0.0.0.0", "--port", "8400"]
