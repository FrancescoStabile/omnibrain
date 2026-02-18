# OmniBrain — Developer Makefile
# Usage: make help

.PHONY: help install dev test lint format build docker docker-local clean

PYTHON := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

help:
	@echo "OmniBrain Development Commands"
	@echo ""
	@echo "  make install       Install Python + Node dependencies"
	@echo "  make dev           Start backend + frontend in dev mode"
	@echo "  make test          Run all tests"
	@echo "  make lint          Lint + type check"
	@echo "  make format        Auto-format code"
	@echo "  make build         Build for production (Node)"
	@echo "  make docker        Build + run with Docker Compose"
	@echo "  make docker-local  Same, but with Ollama (local LLM)"
	@echo "  make clean         Remove build artifacts"

# ── Setup ──────────────────────────────────────────────────────────────────

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	cd web && npm install
	@echo ""
	@echo "✓ Done. Copy .env.example → .env and add your API keys."
	@echo "  cp .env.example .env"

# ── Development ────────────────────────────────────────────────────────────

dev:
	@echo "Starting backend on :7432 and frontend on :3000..."
	@$(VENV)/bin/omnibrain start &
	@cd web && npm run dev

# ── Tests ──────────────────────────────────────────────────────────────────

test:
	$(PYTEST) tests/ -q --tb=short

test-watch:
	$(PYTEST) tests/ -q --tb=short -f

# ── Lint + Format ──────────────────────────────────────────────────────────

lint:
	$(RUFF) check src/ tests/
	cd web && npx tsc --noEmit

format:
	$(RUFF) format src/ tests/
	cd web && npx prettier --write "**/*.{ts,tsx,css}" --log-level warn

# ── Build ──────────────────────────────────────────────────────────────────

build:
	cd web && npm run build

# ── Docker ─────────────────────────────────────────────────────────────────

docker:
	docker compose up --build

docker-local:
	docker compose --profile local up --build

docker-down:
	docker compose down

# ── Cleanup ────────────────────────────────────────────────────────────────

clean:
	rm -rf $(VENV) web/.next web/node_modules __pycache__
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
