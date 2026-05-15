.PHONY: help up down build logs test eval fmt lint typecheck migrate seed clean smoke

help:
	@echo "M.I.R.A. — Make targets"
	@echo "  up         Start all services (docker compose up --build)"
	@echo "  down       Stop and remove containers"
	@echo "  build      Build images without starting"
	@echo "  logs       Tail logs from all services"
	@echo "  test       Run pytest with coverage"
	@echo "  eval       Run LLM-as-judge harness against real agent"
	@echo "  fmt        Format code (ruff format + prettier)"
	@echo "  lint       Lint (ruff check + eslint)"
	@echo "  typecheck  Type check (mypy + tsc)"
	@echo "  migrate    Run alembic upgrade head"
	@echo "  smoke      Hit API endpoints to verify basic functionality"
	@echo "  clean      Remove caches, build artifacts, volumes"

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

test:
	cd backend && pytest -v --cov=app --cov-report=term-missing

eval:
	cd backend && python -m eval.run_eval

fmt:
	cd backend && ruff format app/ tests/ eval/
	cd backend && ruff check --fix app/ tests/ eval/
	cd frontend && npm run format || true

lint:
	cd backend && ruff check app/ tests/ eval/
	cd frontend && npm run lint

typecheck:
	cd backend && mypy app/
	cd frontend && npx tsc --noEmit

migrate:
	cd backend && alembic upgrade head

smoke:
	@curl -s -X POST http://localhost:8000/analyze \
	  -H 'Content-Type: application/json' \
	  -d '{"query":"Analyze Tesla (TSLA)"}' | jq

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.coverage backend/htmlcov
	rm -rf frontend/.next frontend/node_modules
	docker compose down -v
