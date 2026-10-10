# ─── D7.2: Local developer convenience targets ───────────────────────────────────
# Usage: make <target>
# Requires: Python 3.11+, Node.js 20+, pip, npm

.PHONY: help install test test-verbose lint lint-fix backend-lint frontend-build frontend-lint e2e clean

# ── Defaults ────────────────────────────────────────────────────────────────────
VENV := .venv
PYTHON := $(VENV)/Scripts/python.exe  # Windows; adjust for Linux
FRONTEND := frontend
PYTEST := $(PYTHON) -m pytest

help:
	@echo "Available targets:"
	@echo "  install          Install backend + frontend dependencies"
	@echo "  test             Run pytest (backend tests)"
	@echo "  test-verbose     Run pytest with verbose output"
	@echo "  lint             Run ruff check (backend) + oxlint (frontend)"
	@echo "  lint-fix         Run ruff check --fix (backend auto-fix)"
	@echo "  backend-lint     Run ruff check app/"
	@echo "  frontend-build   Build frontend for production"
	@echo "  frontend-lint    Run frontend linter"
	@echo "  e2e              Run Playwright E2E tests (requires backend running)"
	@echo "  clean            Remove build artifacts and caches"

# ── Dependencies ────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt
	cd $(FRONTEND) && npm install

# ── Testing ────────────────────────────────────────────────────────────────────
test:
	$(PYTEST) app/tests/ -q --tb=short

test-verbose:
	$(PYTEST) app/tests/ -v --tb=short

# ── Linting ────────────────────────────────────────────────────────────────────
backend-lint:
	ruff check app/ --output-format=text

lint: backend-lint
	cd $(FRONTEND) && npm run lint

lint-fix:
	ruff check app/ --fix

# ── Frontend ───────────────────────────────────────────────────────────────────
frontend-build:
	cd $(FRONTEND) && npm run build

frontend-lint:
	cd $(FRONTEND) && npm run lint

# ── E2E ────────────────────────────────────────────────────────────────────────
e2e:
	cd $(FRONTEND) && npm run test:e2e

# ── Cleanup ────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(VENV)/Lib/site-packages 2>/dev/null || true
	rm -rf $(FRONTEND)/node_modules 2>/dev/null || true
	rm -rf $(FRONTEND)/dist 2>/dev/null || true
	rm -rf .pytest_cache 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
