FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC \
    # venv вне /app: каталог проекта монтируется томом в dev-режиме
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Тестовые зависимости (pytest, httpx для scripts/dev_check.py) нужны только в
# dev-режиме — docker-compose.dev.yml собирает образ с WITH_DEV=true.
ARG WITH_DEV=false

# Сначала только манифесты — слой с зависимостями кэшируется, пока они не
# меняются. --frozen: ставим ровно то, что зафиксировано в uv.lock.
COPY pyproject.toml uv.lock ./
RUN if [ "$WITH_DEV" = "true" ]; then         uv sync --frozen --no-install-project;     else         uv sync --frozen --no-dev --no-install-project;     fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
