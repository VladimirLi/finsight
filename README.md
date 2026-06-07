# finsight

[![CI](https://github.com/VladimirLi/finsight/actions/workflows/ci.yml/badge.svg)](https://github.com/VladimirLi/finsight/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![Node 24](https://img.shields.io/badge/node-24-339933)

Upload PDF financial statements, extract the data with OCR + a provider-agnostic LLM
layer, and compute financial ratios **deterministically in Python** (never via an LLM).
Any ratio whose required inputs are missing is reported as `unavailable` with the exact
list of missing line items — never a fabricated number.

## Architecture

```
PDF upload
   │
   ▼
OCR / PDF parsing        app/ocr/*        (PyMuPDF + pdfplumber, OCR fallback via Tesseract)
   │   ParsedDocument (pages, tables, text + per-page provenance)
   ▼
LLM extraction           app/llm/*, app/extraction/*
   │   Provider-agnostic (Anthropic | OpenAI / OpenAI-compatible | Ollama).
   │   Maps raw statement text into the CANONICAL schema.
   ▼
Canonical schema         app/schemas/financials.py
   │   FinancialStatement = { canonical_key: FinancialValue(value, source_page,
   │                          source_label, confidence, edited_by_user) }
   │   Users can review/correct values before they feed the ratio engine.
   ▼
Deterministic ratio engine   app/ratios/*
   │   Each ratio declares its required canonical inputs and a pure Python
   │   compute() function. The engine screens for missing inputs / zero
   │   denominators / non-finite results BEFORE computing.
   ▼
Ratio report             RatioResult[] with status = ok | unavailable | undefined
                         (unavailable carries the precise missing_inputs list)

Accounting validation    app/validation/*
                         Deterministic identity checks (assets = liabilities + equity,
                         subtotals foot to totals, gross_profit = revenue − COGS, …)
                         within a rounding tolerance → ok | mismatch | unavailable,
                         surfaced in the Review UI to flag inconsistent extractions.
```

Ratios and accounting checks are **always** computed by vetted Python formulas, so identical
inputs always produce identical, explainable outputs. The LLM is used only for extraction,
never for math.

The HTTP API is described by the backend's **OpenAPI schema** — browse it live at
`http://localhost:8000/docs`, or read the committed `backend/openapi.json` (from which the
frontend's types are generated). It is the single source of truth for request/response shapes.

## Run it locally — no API keys

The fastest way to try finsight. The **only prerequisite is Docker**; a local LLM
(Ollama) is started for you, so **no API keys are required**:

```bash
./scripts/quickstart.sh      # or: make quickstart
```

This builds and starts the whole stack (PostgreSQL + backend + frontend + a local
Ollama model) and prints the URL when ready (default <http://localhost:3000>). The
first run downloads the model (~2 GB). Use a different model with
`LLM_MODEL=llama3.1 ./scripts/quickstart.sh`. Stop with
`docker compose --profile local-llm down` (add `-v` to wipe data).

Prefer a cloud model instead? Set `LLM_PROVIDER`/`LLM_MODEL` + the matching API
key in `.env` (see [Provider switching](#provider-switching-llm_provider--llm_model)).

## Developing

Prerequisites: **Python 3.13** (available as `python` on your `PATH`), **Node 24**
(`nvm use`), **Docker**, and the host CLI tools **gitleaks** + **git-cliff**
(`brew install gitleaks git-cliff`) used by the secrets-scan and changelog targets.
See [CONTRIBUTING.md](CONTRIBUTING.md#getting-set-up) for details.

```bash
make install     # backend venv + dev deps + pre-commit; frontend npm ci
make dev-backend # uvicorn (in one terminal)
make dev-frontend# vite     (in another)
make check       # run every quality gate (CI parity); `make help` lists all targets
```

## Backend

Requires Python 3.13+ (the project standardizes on 3.13 across CI, Docker, and the lockfiles).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt for runtime only
cp .env.example .env          # then edit .env (see provider switching below)
uvicorn app.main:app --reload
```

Database schema: `init_db()` (create-all) is used for local SQLite; the production /
Docker path applies **Alembic** migrations (`make migrate`). Add a migration after model
changes with `make revision msg="..."`.

The API is served at `http://localhost:8000` (health check: `GET /api/health`).
On startup the upload directory is created and the SQLite database is initialised
automatically.

### Optional heavy dependencies

The OCR/PDF libraries (`pymupdf`, `pdfplumber`, `pytesseract`, `pillow`) and the LLM
SDKs (`anthropic`, `openai`, `httpx`) are imported **lazily**, so the app starts and the
core/ratio code runs without them installed. They are only needed when you actually run
the end-to-end extraction pipeline. OCR fallback additionally requires the system
`tesseract` binary (e.g. `brew install tesseract` on macOS); set `TESSERACT_CMD` in
`.env` if it is not on your `PATH`.

### Tests

```bash
cd backend
python -m pytest -q                              # full suite (121 tests, no network/OCR/LLM)
python -m pytest --cov=app --cov-fail-under=85   # coverage-gated (core)
```

Tests are deterministic: a `FakeLLMProvider` drives the extraction pipeline, Hypothesis
property-tests the ratio engine, and Schemathesis fuzzes the API against its own OpenAPI.

## Provider switching (LLM_PROVIDER / LLM_MODEL)

finsight is provider-agnostic. Select the extraction backend with two env vars in `.env`:

| Provider                                  | `LLM_PROVIDER` | Example `LLM_MODEL` | Credentials / config                                                   |
| ----------------------------------------- | -------------- | ------------------- | ---------------------------------------------------------------------- |
| Anthropic                                 | `anthropic`    | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY`                                                    |
| OpenAI                                    | `openai`       | `gpt-4o`            | `OPENAI_API_KEY`                                                       |
| OpenAI-compatible (vLLM, LM Studio, etc.) | `openai`       | server-specific     | `OPENAI_API_KEY` + `OPENAI_BASE_URL` (e.g. `http://localhost:1234/v1`) |
| Ollama / local                            | `ollama`       | `llama3.1`          | `OLLAMA_BASE_URL` (default `http://localhost:11434`)                   |

No code changes are needed to switch providers — only `.env`. The current provider is
echoed by `GET /api/health` as `llm_provider`.

## Frontend

Requires Node 24+ (the current LTS; matches CI and Docker). An `.nvmrc` pins the
version — run `nvm use` (installing it first with `nvm install` if needed).

```bash
cd frontend
npm install
npm run dev          # Vite dev server (proxies /api to the backend)
```

Production build:

```bash
npm run build        # tsc -b && vite build  →  dist/
```

The frontend (React + Vite + **strict** TypeScript) talks to the backend over its REST API.
API types are **generated** from the backend's OpenAPI schema (`npm run gen:api-types` →
`src/api/openapi.d.ts`), so client/server types can't drift. Styling uses **Panda CSS** with `strictTokens` — off-design-system values are a
compile error. It renders the review/correction UI (with accounting-check flags), company
history, and ratio trends.

## Developer tooling & quality gates

Everything below runs locally via `make <target>` and in CI (`.github/workflows/ci.yml`),
and the fast checks run on commit via `pre-commit`. `make check` runs the lot.

| Area             | Backend                                              | Frontend                                       |
| ---------------- | ---------------------------------------------------- | ---------------------------------------------- |
| Lint             | Ruff (incl. pydocstyle `D`)                          | ESLint (`strictTypeChecked` + `jsx-a11y`)      |
| Format           | Ruff format                                          | Prettier                                       |
| Types            | **mypy** (strict+extra) **and** **pyright** (strict) | `tsc` (strict + `noUncheckedIndexedAccess`, …) |
| Tests            | pytest + coverage gate (85%)                         | Vitest + coverage gate + axe a11y              |
| Dead code        | Vulture                                              | Knip                                           |
| Security (SAST)  | Bandit                                               | —                                              |
| Dependency vulns | pip-audit + Dependabot                               | npm audit + Dependabot                         |
| Secrets          | gitleaks (repo-wide)                                 | gitleaks                                       |
| Spelling         | codespell + cspell                                   | codespell + cspell                             |
| Bundle budget    | —                                                    | size-limit + Lighthouse CI                     |
| Docs             | MkDocs (mkdocstrings)                                | Typedoc                                        |
| Commits          | commitlint (conventional) + git-cliff changelog      |                                                |

### Drift gates (`make drift`)

Generated artifacts are kept honest by _regenerate → `git diff --exit-code`_:

- **OpenAPI schema** — `backend/openapi.json` matches the live FastAPI app
- **Frontend API types** — `openapi.d.ts` matches `openapi.json`
- **DB migrations** — `alembic check` (models match migrations)
- **`.env.example`** — documents every `Settings` field

## Testing (the pyramid)

Tests are layered, widest tier first:

1. **Unit / property** — pure ratio & validation engines, schema coercion
   (Hypothesis property tests, Schemathesis API fuzzing). Most numerous.
2. **Integration** — `backend/tests/test_service.py` drives the full
   parse → extract → persist pipeline against an in-memory DB with deterministic
   OCR/LLM fakes.
3. **HTTP E2E** — `backend/tests/test_api_e2e.py` exercises the whole
   upload → poll → review → ratios → validation journey through the real FastAPI
   routes (`TestClient`), still deterministic and network-free. Runs in CI.
4. **Browser E2E (Playwright)** — `frontend/e2e/`:
   - `app.spec.ts` — UI smoke (routing, company CRUD) against the real backend;
     runs in CI (no model needed).
   - `extraction.spec.ts` — the full upload → extract → review flow against a
     **locally-deployed Ollama** model, using a **real company filing** (the
     consolidated statements sliced from Berkshire Hathaway's annual report).
     Opt-in via `RUN_LLM_E2E=1`; self-skips if Ollama or the fixture is absent.
5. **Full-stack smoke** — `scripts/smoke.sh` builds and boots the whole
   `docker-compose` stack (postgres + backend + frontend), waits for health, and
   asserts the API answers through the nginx proxy and the SPA is served.

```bash
make e2e-install   # one-time: install Playwright's Chromium
make e2e-fixture   # fetch the real filing fixture (git-ignored, not vendored)
make e2e           # Playwright (UI smoke; set RUN_LLM_E2E=1 + Ollama for extraction)
make smoke         # full-stack docker-compose smoke test
make pre-pr        # the pre-PR gate: make check + make e2e + make smoke
```

**Before opening a PR, `make pre-pr` must pass** — it runs every quality gate
plus the browser E2E and the full-stack smoke test.

## Docker

```bash
cp backend/.env.example .env          # set POSTGRES_PASSWORD + provider keys
make docker-up                        # postgres + backend (runs migrations) + frontend
```

`docker-compose.yml` builds the backend (with `tesseract` + Alembic entrypoint), the
frontend (nginx serving the built SPA), and PostgreSQL. Images are linted with hadolint
and scanned with trivy in CI.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the
quality gates, and the PR workflow, and please follow the
[Code of Conduct](CODE_OF_CONDUCT.md). To report a vulnerability, see
[SECURITY.md](SECURITY.md).

## License

Released under the [MIT License](LICENSE).
