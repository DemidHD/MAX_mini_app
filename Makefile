# Команды монорепо. `make` без аргументов показывает список.
#
# Требования: docker + docker compose (запуск), uv (Python), pnpm (фронтенд).
# Установка инструментов — в CONTRIBUTING.md.

SHELL := /bin/bash
.DEFAULT_GOAL := help

CORE := apps/core
AI := apps/ai-gateway
MINIAPP := apps/miniapp

.PHONY: help
help: ## Показать список команд
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── окружение ───────────────────────────────────────────────────────────────

.PHONY: env
env: ## Создать .env из .env.example, если его ещё нет
	@if [ -f .env ]; then echo ".env уже есть, не трогаю"; else cp .env.example .env && echo ".env создан из .env.example"; fi

.PHONY: install
install: ## Установить зависимости всех сервисов
	cd $(CORE) && uv sync
	cd $(AI) && uv sync
	pnpm install

# ─── запуск ──────────────────────────────────────────────────────────────────

.PHONY: up
up: env ## Поднять бэкенд локально (Postgres, Redis, Core API, Worker, Beat, AI Gateway)
	docker compose up --build -d
	@echo
	@echo "  Core API         http://localhost:$${CORE_API_PORT:-8010}/docs"
	@echo "  админка          http://localhost:8001"
	@echo "  AI Gateway       только внутри docker-сети (тех. ТЗ 5)"
	@echo
	@echo "  фронтенд поднимается отдельно: make dev-front (или make up-all)"

.PHONY: up-all
up-all: env ## То же плюс фронтенд в контейнере (профиль frontend)
	docker compose --profile frontend up --build -d
	@echo
	@echo "  мини-приложение  http://localhost:5173"

.PHONY: down
down: ## Остановить всё, данные сохранить
	docker compose down

.PHONY: clean
clean: ## Остановить всё и удалить данные Postgres и Redis
	docker compose down -v

.PHONY: logs
logs: ## Логи всех сервисов
	docker compose logs -f

.PHONY: ps
ps: ## Состояние сервисов
	docker compose ps

# ─── проверки ────────────────────────────────────────────────────────────────

.PHONY: test
test: test-core test-ai test-front ## Прогнать все тесты, кроме e2e

.PHONY: test-core
test-core: ## Тесты Core API (интеграционные пропускаются, если нет БД)
	cd $(CORE) && uv run pytest

.PHONY: test-ai
test-ai: ## Тесты AI Gateway
	cd $(AI) && uv run pytest

.PHONY: test-front
test-front: ## Юнит-тесты мини-приложения
	pnpm --filter miniapp test

.PHONY: test-e2e
test-e2e: ## E2E-тесты Playwright на мобильном и десктопном профиле (ТЗ 0.2)
	pnpm --filter miniapp test:e2e

.PHONY: lint
lint: ## Линтеры и проверка типов во всех сервисах
	cd $(CORE) && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd $(AI) && uv run ruff check . && uv run ruff format --check . && uv run mypy
	pnpm --filter miniapp lint
	pnpm --filter miniapp typecheck
	pnpm --filter miniapp format:check

.PHONY: fmt
fmt: ## Отформатировать код во всех сервисах
	cd $(CORE) && uv run ruff format . && uv run ruff check --fix .
	cd $(AI) && uv run ruff format . && uv run ruff check --fix .
	pnpm --filter miniapp format

.PHONY: check
check: lint test ## Всё, что должно быть зелёным перед пушем

# ─── разработка без docker ───────────────────────────────────────────────────

.PHONY: dev-core
dev-core: ## Core API с автоперезагрузкой (Postgres и Redis нужны свои)
	cd $(CORE) && uv run uvicorn navigator.api.app:create_app --factory --reload --port 8000

.PHONY: dev-worker
dev-worker: ## Celery-воркер
	cd $(CORE) && uv run celery -A navigator.worker.celery_app:app worker --loglevel=info

.PHONY: dev-beat
dev-beat: ## Celery Beat
	cd $(CORE) && uv run celery -A navigator.worker.celery_app:app beat --loglevel=info

.PHONY: dev-ai
dev-ai: ## AI Gateway с автоперезагрузкой
	cd $(AI) && uv run uvicorn navigator_ai.main:create_app --factory --reload --port 8100

.PHONY: dev-front
dev-front: ## Dev-сервер мини-приложения
	pnpm --filter miniapp dev

# ─── база и типы ─────────────────────────────────────────────────────────────

.PHONY: seed
seed: ## Залить справочники в базу разработки (идемпотентно)
	cd $(CORE) && uv run python -m navigator.seed

.PHONY: db-shell
db-shell: ## psql в базу разработки
	# Логин и база берутся из окружения контейнера, а не из окружения make:
	# так команда остаётся верной, даже если их переопределили в .env.
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

.PHONY: redis-shell
redis-shell: ## redis-cli
	docker compose exec redis redis-cli

.PHONY: api-types
api-types: ## Перегенерировать типы фронтенда из схемы OpenAPI (тех. ТЗ 8.6)
	# Схема снимается с приложения напрямую: ни поднятый сервер, ни база для
	# генерации типов не нужны — иначе она ломается ровно тогда, когда фронт и
	# бэкенд пишут разные люди.
	cd $(CORE) && uv run python -m navigator.api.openapi > ../../$(MINIAPP)/openapi.json
	pnpm --filter miniapp api:types

.PHONY: requirements
requirements: ## Перегенерировать requirements.txt бэкенд-сервисов из uv.lock
	# Файлы нужны платформам, которые умеют только `pip install -r`
	# (панель Timeweb). Источник истины остаётся uv.lock — правится он,
	# requirements.txt всегда производный. CI проверяет, что они совпадают.
	cd $(CORE) && uv export --frozen --no-dev --no-hashes --format requirements-txt -o requirements.txt
	cd $(AI) && uv export --frozen --no-dev --no-hashes --format requirements-txt -o requirements.txt
