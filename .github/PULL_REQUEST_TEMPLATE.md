<!--
Thanks for contributing! Keep the diff focused and use a Conventional Commits
title (lowercase subject), e.g. "fix(api): return 404 for unknown period".
-->

## What & why

<!-- What does this change and why? Link any related issue, e.g. "Closes #123". -->

## How was it tested?

<!-- Commands you ran, new/updated tests, manual steps. -->

## Checklist

- [ ] `make pre-pr` passes locally (check + Playwright e2e + full-stack smoke)
- [ ] Added/updated tests for the change
- [ ] Updated docs (README / docstrings) if behavior changed
- [ ] Regenerated any drift-gated artifacts (OpenAPI schema, typed client,
      migrations, dependency locks) and committed them
- [ ] Commit messages follow Conventional Commits (lowercase subject)
