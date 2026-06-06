# Contributing to finsight

Thanks for your interest in contributing! This document explains how to set up
your environment, the quality bar, and how to propose changes.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a bug** or **request a feature** via [issues](../../issues) (templates
  are provided).
- **Improve docs**, fix typos, or clarify behavior.
- **Submit a pull request** for a bug fix or feature.

For anything large, please open an issue first to discuss the approach before
writing code.

## Getting set up

Prerequisites: **Python 3.13**, **Node 24** (an `.nvmrc` is provided — run
`nvm use`), and **Docker** (only for the full-stack/e2e tests).

```bash
make install      # backend venv + dev deps + pre-commit hooks; frontend npm ci
make dev-backend  # run the API (uvicorn) in one terminal
make dev-frontend # run the Vite dev server in another
```

Just want to run the app? `make quickstart` boots everything locally with a
local LLM and **no API keys** (see the [README](README.md#run-it-locally--no-api-keys)).

## Quality gates

Every change must pass the full gate. `pre-commit` runs the fast checks on each
commit; run the rest before pushing:

```bash
make check    # lint, types, dead-code, tests+coverage, security, drift gates (CI parity)
make pre-pr   # make check + Playwright e2e + full-stack docker smoke
```

Before opening a PR, **`make pre-pr` must pass.** See the
[test pyramid](README.md#testing-the-pyramid) for the layers (unit → integration
→ HTTP e2e → browser e2e → full-stack smoke). The browser extraction test runs
against a local Ollama model and is opt-in via `RUN_LLM_E2E=1`.

What the gate enforces (see the table in the README): Ruff + ESLint, mypy +
pyright + strict `tsc`, Vulture + Knip, pytest + Vitest with coverage floors,
Bandit + pip-audit + npm audit, gitleaks, spell-check, and **drift gates** that
regenerate artifacts (OpenAPI schema, typed client, migrations, locks) and fail
on any diff — so regenerate and commit those when you change the relevant source.

## Commit messages

This repo uses [Conventional Commits](https://www.conventionalcommits.org/) and
enforces them with commitlint. The subject must be **lowercase**.

```
feat(ratios): add interest-coverage ratio
fix(api): return 404 for unknown period
docs: clarify provider switching
```

`CHANGELOG.md` is generated from these messages via git-cliff.

## Pull requests

1. Fork and create a branch off `main`.
2. Make your change with tests; keep the diff focused.
3. Ensure `make pre-pr` is green.
4. Open the PR and fill in the template. Link any related issue.

CI runs the same gates on every PR. A maintainer will review as soon as they can.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE) that covers this project.
