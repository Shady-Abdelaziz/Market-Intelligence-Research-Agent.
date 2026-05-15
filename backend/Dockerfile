# Multi-stage build. CMD argument selects api or worker mode.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS runtime
COPY pyproject.toml alembic.ini entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh
COPY app ./app
COPY alembic ./alembic
COPY eval ./eval

# Default to api mode; override with CMD ["worker"] in compose
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
