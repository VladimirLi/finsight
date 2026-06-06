.DEFAULT_GOAL := help
.PHONY: help install backend-install frontend-install \
        check pre-pr lint typecheck deadcode test format security drift docs changelog \
        backend-lint backend-format backend-typecheck backend-deadcode backend-test backend-cov backend-security \
        backend-docs migrate revision migrate-check lock lock-check \
        frontend-lint frontend-format frontend-typecheck frontend-deadcode frontend-test frontend-cov \
        frontend-audit frontend-size frontend-docs api-types-check \
        e2e e2e-install e2e-fixture smoke quickstart \
        spell secrets-scan openapi openapi-check env-check \
        docker-build docker-up docker-down docker-logs dev-backend dev-frontend

VENV := backend/.venv
PY := $(abspath $(VENV)/bin)
COV_MIN := 85
LOCK_PY ?= python3.13   # locks are canonical on the CI/Docker Python (3.13)

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------------- install
install: backend-install frontend-install ## Install all dev deps + pre-commit
backend-install: ## Create venv, install backend dev deps, install pre-commit
	python -m venv $(VENV)
	$(PY)/pip install -U pip
	$(PY)/pip install -r backend/requirements-dev.txt
	$(PY)/pip install pre-commit && $(PY)/pre-commit install && $(PY)/pre-commit install --hook-type commit-msg || true
frontend-install: ## Install frontend deps
	npm --prefix frontend ci

# ----------------------------------------------------------------- aggregate
check: lint typecheck deadcode test security drift ## Run EVERYTHING (CI parity)
pre-pr: check e2e smoke ## Pre-PR gate: full check + Playwright e2e + full-stack smoke (all must pass before a PR)
lint: backend-lint frontend-lint            ## Lint both stacks
typecheck: backend-typecheck frontend-typecheck ## Typecheck both (mypy+pyright / tsc)
deadcode: backend-deadcode frontend-deadcode ## Dead-code scan (vulture / knip)
test: backend-cov frontend-cov              ## Test both (coverage-gated)
format: backend-format frontend-format      ## Auto-format both
security: backend-security frontend-audit spell secrets-scan ## All security/audit scans
drift: openapi-check env-check migrate-check api-types-check lock-check ## All drift gates
docs: backend-docs frontend-docs            ## Build both docs sites
changelog: ## Regenerate CHANGELOG.md via git-cliff
	git-cliff -o CHANGELOG.md

# ----------------------------------------------------------------- backend
backend-lint: ## ruff check
	cd backend && $(PY)/ruff check app tests scripts
backend-format: ## ruff format
	cd backend && $(PY)/ruff format app tests scripts
backend-typecheck: ## mypy --strict + pyright --strict
	cd backend && $(PY)/mypy app && $(PY)/pyright app
backend-deadcode: ## vulture
	cd backend && $(PY)/vulture
backend-test: ## pytest (no coverage gate)
	cd backend && $(PY)/pytest
backend-cov: ## pytest with coverage gate ($(COV_MIN)% on the core)
	cd backend && $(PY)/pytest --cov=app --cov-report=term-missing --cov-fail-under=$(COV_MIN)
backend-security: ## bandit (SAST) + pip-audit (dep vulns)
	cd backend && $(PY)/bandit -c pyproject.toml -r app -q && $(PY)/pip-audit
backend-docs: ## Build backend docs (mkdocs --strict)
	cd backend && $(PY)/mkdocs build --strict
migrate: ## Apply DB migrations to head
	cd backend && $(PY)/alembic upgrade head
revision: ## Autogenerate a migration (use msg="...")
	cd backend && $(PY)/alembic revision --autogenerate -m "$(msg)"
migrate-check: ## Drift gate: migrations match the models
	cd backend && DATABASE_URL="sqlite:///./_drift.db" $(PY)/alembic upgrade head && \
	  DATABASE_URL="sqlite:///./_drift.db" $(PY)/alembic check; rm -f backend/_drift.db
lock: ## Regenerate hashed dependency locks (canonical: Python 3.13, matches CI/Docker)
	@tmp=$$(mktemp -d) && $(LOCK_PY) -m venv $$tmp && $$tmp/bin/pip install -q pip-tools && \
	  cd backend && \
	  $$tmp/bin/pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements.lock requirements.txt && \
	  $$tmp/bin/pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.lock requirements-dev.txt; \
	  rm -rf $$tmp
lock-check: lock ## Drift gate: dep locks match the requirements inputs
	git diff --exit-code backend/requirements.lock backend/requirements-dev.lock || \
	  (echo "dep locks stale — run 'make lock' (needs python3.13) and commit" && exit 1)

# ----------------------------------------------------------------- frontend
frontend-lint: ## eslint
	npm --prefix frontend run lint
frontend-format: ## prettier --write
	npm --prefix frontend run format
frontend-typecheck: ## tsc --noEmit
	npm --prefix frontend run typecheck
frontend-deadcode: ## knip
	npm --prefix frontend run knip
frontend-test: ## vitest run
	npm --prefix frontend run test
frontend-cov: ## vitest run with coverage thresholds
	npm --prefix frontend run test:cov
frontend-audit: ## npm audit (high+)
	npm --prefix frontend run audit
frontend-size: ## bundle-size budget
	npm --prefix frontend run build && npm --prefix frontend run size
frontend-docs: ## typedoc
	npm --prefix frontend run docs
api-types-check: ## Drift gate: frontend OpenAPI types match backend schema
	npm --prefix frontend run gen:api-types
	git diff --exit-code frontend/src/api/openapi.d.ts || \
	  (echo "openapi.d.ts is stale — run 'make -C frontend gen:api-types' and commit" && exit 1)

# ----------------------------------------------------------------- e2e (Playwright)
e2e-install: ## Install Playwright's Chromium browser (one-time)
	npm --prefix frontend run e2e:install
e2e-fixture: ## Fetch a real company filing + slice the financial-statement pages
	$(PY)/python scripts/fetch_e2e_fixture.py
e2e: ## Playwright e2e (UI smoke always; set RUN_LLM_E2E=1 + local Ollama for full extraction)
	npm --prefix frontend run e2e

# ----------------------------------------------------------------- full-stack smoke
smoke: ## Full-stack docker-compose smoke test (build, health, SPA, teardown)
	./scripts/smoke.sh

# ----------------------------------------------------------------- cross-cutting
spell: ## codespell + cspell
	$(PY)/codespell --config .codespellrc backend/app frontend/src README.md
	npx --yes cspell "**/*.{py,ts,tsx,md}" --config cspell.json --no-progress
secrets-scan: ## gitleaks (requires gitleaks on PATH)
	gitleaks detect --config .gitleaks.toml --source . --redact

# ----------------------------------------------------------------- drift gates
openapi: ## Regenerate backend/openapi.json from the live app
	cd backend && $(PY)/python scripts/export_openapi.py
openapi-check: openapi ## Fail if openapi.json is stale
	git diff --exit-code backend/openapi.json || \
	  (echo "openapi.json is stale — run 'make openapi' and commit" && exit 1)
env-check: ## Fail if a Settings field is undocumented in .env.example
	cd backend && $(PY)/pytest tests/test_env_drift.py -q

# ----------------------------------------------------------------- docker / run
quickstart: ## One command, NO API keys: run the whole app locally with a local LLM (Ollama)
	./scripts/quickstart.sh
docker-build: ## docker compose build
	docker compose build
docker-up: ## docker compose up -d (needs POSTGRES_PASSWORD)
	docker compose up -d
docker-down: ## docker compose down
	docker compose down
docker-logs: ## tail compose logs
	docker compose logs -f
dev-backend: ## Run the API (uvicorn --reload)
	cd backend && $(PY)/uvicorn app.main:app --reload
dev-frontend: ## Run the Vite dev server
	npm --prefix frontend run dev
