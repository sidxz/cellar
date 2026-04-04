# ============================================================================
# Chem-Vault2 Development Makefile
# ============================================================================
# Quick reference:
#   make up        — start Postgres + Valkey, run migrations
#   make dev       — start backend + frontend (requires `make up` first)
#   make test      — run all backend unit tests + import-linter
#   make nuke      — destroy everything (volumes, containers) and start fresh
#   make restart   — nuke + up + dev
# ============================================================================

COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml
BACKEND := cd backend
FRONTEND := cd frontend

.PHONY: help up down dev dev-be dev-fe migrate test lint nuke restart seed status logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ─────────────────────────────────────────────

up: ## Start Postgres + Valkey, run migrations, seed
	docker compose up -d postgres valkey
	@echo "⏳ Waiting for Postgres to be healthy..."
	@until docker compose exec postgres pg_isready -U chemvault -q 2>/dev/null; do sleep 1; done
	@echo "✅ Postgres ready"
	$(BACKEND) && uv run alembic upgrade head
	@echo "✅ Migrations applied"

down: ## Stop all containers (keep data)
	docker compose down

status: ## Show container status
	docker compose ps

logs: ## Tail container logs
	docker compose logs -f postgres valkey

# ── Development Servers ────────────────────────────────────────

dev: ## Start backend + frontend (parallel, requires `make up` first)
	@echo "Starting backend on :8000 and frontend on :3000..."
	@trap 'kill 0' INT TERM; \
		($(BACKEND) && DATABASE_URL=postgresql+asyncpg://chemvault:chemvault@localhost:5432/chemvault \
			SENTINEL_SERVICE_KEY=sk_5sdLzYlegEgpEFGzlmZNX3zwq4YZ6b4MJttehFKepgk \
			SENTINEL_URL=https://sentinel.orca-03.biobio.tamu.edu \
			uv run uvicorn chem_vault.interface.app:app --reload --port 8000) & \
		($(FRONTEND) && pnpm dev) & \
		wait

dev-be: ## Start backend only
	$(BACKEND) && DATABASE_URL=postgresql+asyncpg://chemvault:chemvault@localhost:5432/chemvault \
		SENTINEL_SERVICE_KEY=sk_5sdLzYlegEgpEFGzlmZNX3zwq4YZ6b4MJttehFKepgk \
		SENTINEL_URL=https://sentinel.orca-03.biobio.tamu.edu \
		uv run uvicorn chem_vault.interface.app:app --reload --port 8000

dev-fe: ## Start frontend only
	$(FRONTEND) && pnpm dev

migrate: ## Run Alembic migrations
	$(BACKEND) && DATABASE_URL=postgresql+asyncpg://chemvault:chemvault@localhost:5432/chemvault \
		uv run alembic upgrade head

# ── Testing ────────────────────────────────────────────────────

test: ## Run unit tests + import-linter
	$(BACKEND) && uv run pytest tests/unit/ -v --tb=short && uv run lint-imports

test-api: ## Run API tests (requires `make up`)
	$(BACKEND) && uv run pytest tests/api/ -v --tb=short

test-all: ## Run all tests
	$(BACKEND) && uv run pytest -v --tb=short && uv run lint-imports

lint: ## Run import-linter only
	$(BACKEND) && uv run lint-imports

# ── Cleanup ────────────────────────────────────────────────────

nuke: ## Destroy containers, volumes, and all data — start fresh
	@echo "🔥 Nuking everything..."
	docker compose down -v --remove-orphans
	@echo "✅ All containers and volumes removed"

restart: nuke up dev ## Nuke + start fresh + dev servers

# ── Seed Data ──────────────────────────────────────────────────

seed: ## Seed test data (organization + sample molecules) via API
	@echo "Seeding data via API (backend must be running on :8000)..."
	@echo "This requires you to be logged in (Sentinel auth tokens)."
	@echo "Use the UI to create an Organization first, then register molecules."
