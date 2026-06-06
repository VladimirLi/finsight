# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities.

Report them privately instead, via either:

- GitHub's [private vulnerability reporting](../../security/advisories/new)
  (Security → Report a vulnerability), or
- email to **vladimir@arkus.ai**.

Please include enough detail to reproduce — affected component (backend / frontend /
extraction pipeline), steps, and impact. I'll acknowledge your report as soon as I
can and keep you updated on the fix.

## Scope notes

finsight processes user-uploaded PDFs and can call external/local LLM providers.
When reporting, it's especially helpful to flag issues involving file handling,
SSRF via provider/base URLs, prompt-injection leading to unsafe behavior, or
exposure of secrets/keys.

## Supported versions

This is an actively developed project; fixes land on the `main` branch. There is
no long-term-support branch yet, so please test against the latest `main`.
