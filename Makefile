# ============================================================================
# Chem-Vault2 Development Makefile
# ============================================================================
# Quick reference:
#   make up        — start Postgres + Valkey, run migrations
#   make dev       — install deps, start backend + frontend in background
#   make stop      — stop backend + frontend dev servers
#   make test      — run all backend unit tests + import-linter
#   make nuke      — destroy everything (volumes, containers) and start fresh
#   make restart   — nuke + up + dev
#
# Secrets are read from .env (gitignored). Copy .env.example to .env and fill in.
# ============================================================================

# Load .env into Make variables (if the file exists)
ifneq (,$(wildcard ./.env))
  include .env
  export
endif

BACKEND  := cd backend
FRONTEND := cd frontend
LOGDIR   := .logs

.PHONY: help up down install dev dev-be dev-fe stop migrate test test-api test-all lint nuke restart status logs logs-dev

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ─────────────────────────────────────────────

up: ## Start Postgres + Valkey + Infisical, run migrations, bootstrap secrets
	docker compose up -d postgres valkey infisical-db infisical
	@echo "Waiting for Postgres to be healthy..."
	@until docker compose exec postgres pg_isready -U chemvault -q 2>/dev/null; do sleep 1; done
	@echo "Postgres ready"
	$(BACKEND) && uv run alembic upgrade head
	@echo "Migrations applied"
	@./scripts/bootstrap-infisical.sh

down: ## Stop all containers (keep data)
	docker compose down

status: ## Show container status
	docker compose ps

logs: ## Tail container logs
	docker compose logs -f postgres valkey infisical

# ── Dependencies ──────────────────────────────────────────────

install: ## Install all dependencies (backend + frontend)
	$(BACKEND) && uv sync
	$(FRONTEND) && pnpm install

# ── Development Servers ────────────────────────────────────────

dev: install stop ## Install deps, stop old instances, start backend + frontend
	@mkdir -p $(LOGDIR)
	@echo "Starting backend on :8000..."
	@nohup sh -c '$(BACKEND) && uv run uvicorn chem_vault.interface.app:app --reload --port 8000' \
		> $(LOGDIR)/backend.log 2>&1 & echo "$$!" > $(LOGDIR)/backend.pid
	@echo "Starting frontend on :3000..."
	@nohup sh -c '$(FRONTEND) && pnpm dev' \
		> $(LOGDIR)/frontend.log 2>&1 & echo "$$!" > $(LOGDIR)/frontend.pid
	@sleep 1
	@echo ""
	@echo "  Backend:  http://localhost:8000  (PID $$(cat $(LOGDIR)/backend.pid))"
	@echo "  Frontend: http://localhost:3000  (PID $$(cat $(LOGDIR)/frontend.pid))"
	@echo ""
	@echo "  make logs-dev  — tail server output"
	@echo "  make stop      — stop both servers"

dev-be: ## Start backend only
	@mkdir -p $(LOGDIR)
	@nohup sh -c '$(BACKEND) && uv run uvicorn chem_vault.interface.app:app --reload --port 8000' \
		> $(LOGDIR)/backend.log 2>&1 & echo "$$!" > $(LOGDIR)/backend.pid
	@echo "Backend started on :8000 (PID $$(cat $(LOGDIR)/backend.pid))"

dev-fe: ## Start frontend only
	@mkdir -p $(LOGDIR)
	@nohup sh -c '$(FRONTEND) && pnpm dev' \
		> $(LOGDIR)/frontend.log 2>&1 & echo "$$!" > $(LOGDIR)/frontend.pid
	@echo "Frontend started on :3000 (PID $$(cat $(LOGDIR)/frontend.pid))"

stop: ## Stop backend + frontend dev servers
	@if [ -f $(LOGDIR)/backend.pid ] && kill -0 $$(cat $(LOGDIR)/backend.pid) 2>/dev/null; then \
		kill $$(cat $(LOGDIR)/backend.pid) 2>/dev/null; \
		echo "Backend stopped (PID $$(cat $(LOGDIR)/backend.pid))"; \
	fi
	@if [ -f $(LOGDIR)/frontend.pid ] && kill -0 $$(cat $(LOGDIR)/frontend.pid) 2>/dev/null; then \
		kill $$(cat $(LOGDIR)/frontend.pid) 2>/dev/null; \
		echo "Frontend stopped (PID $$(cat $(LOGDIR)/frontend.pid))"; \
	fi
	@rm -f $(LOGDIR)/backend.pid $(LOGDIR)/frontend.pid
	@lsof -ti:8000 | xargs kill 2>/dev/null || true
	@lsof -ti:3000 | xargs kill 2>/dev/null || true

logs-dev: ## Tail dev server logs
	@tail -f $(LOGDIR)/backend.log $(LOGDIR)/frontend.log 2>/dev/null || \
		echo "No logs found. Run 'make dev' first."

migrate: ## Run Alembic migrations
	$(BACKEND) && uv run alembic upgrade head

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

nuke: stop ## Destroy containers, volumes, and all data
	docker compose down -v --remove-orphans
	rm -rf $(LOGDIR)
	rm -f .infisical-bootstrapped
	@sed -i '' '/^INFISICAL_/d' .env 2>/dev/null || true
	@echo "All containers and volumes removed"

restart: nuke up dev ## Nuke + start fresh + dev servers
