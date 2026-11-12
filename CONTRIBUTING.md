# Contributing to AdvisoryTrail

Thanks for helping out. This document covers the local workflow, the checks a change is expected to
pass, and how to report problems.

## Reporting an issue

Open an issue with:

- what you expected and what happened,
- the exact steps to reproduce (repository visibility, branch and the scan you ran help a lot),
- the relevant API log lines (`./advisorytrail logs api`), with any tokens or secrets removed.

Security problems must not be reported in a public issue — see [SECURITY.md](SECURITY.md).

## Development environment

Everything runs in Docker; Python and Node are not required on the host.

```bash
docker compose up --build          # dashboard :3000, API :8000, docs :8000/docs
./advisorytrail status               # container and endpoint health
./advisorytrail logs api             # follow backend logs
```

For dashboard work with hot reload:

```bash
cd advisorytrail-dashboard
npm install
npm run dev
```

## Checks before opening a pull request

```bash
# Backend: unit and API tests
docker compose exec api python -m pytest -q

# Dashboard: type-check, production build, lint
cd advisorytrail-dashboard
npm run build
npm run lint
```

A pull request should pass all three. If a check cannot run in your environment, say so in the
description instead of skipping it silently.

## Working on the scanner

- Scans run through `osv-scanner`; advisory metadata (severity, summary, fixed version) comes from
  the OSV.dev API. Keep both calls in `services/api/app/services/scanner.py`.
- Findings are stored per advisory, one row each. Grouping for the UI happens in
  `advisorytrail-dashboard/src/pages/Findings.tsx`.
- Review writes must go through `PATCH /api/v1/findings/{id}` or `PATCH /api/v1/findings/bulk`; never
  mutate status from the client only.

## Coding conventions

- **Python:** type hints on public functions, `async def` for I/O, no blocking calls in request
  handlers. User-facing errors should say what the user can do next.
- **TypeScript:** no `any` (lint enforces it); model API payloads with the row types in
  `src/types.ts`. Components live in `src/components`, pages in `src/pages`.
- **SQL:** use bound parameters through SQLAlchemy; migrations belong in
  `services/api/app/migrations.py` so existing databases upgrade in place.
- **Secrets:** never commit `.env`, tokens, webhook secrets or private keys. Enable the guard once
  per clone with `git config core.hooksPath .githooks`.

## Commit messages

Use a short imperative subject line and explain *why* in the body when it is not obvious:

```
Validate repository access before connecting

Private repositories were accepted as soon as GitHub returned 200, so a
token without pull access created a card that could never be scanned.
```

## Pull requests

1. Fork the repository and branch from `main`.
2. Keep the change focused; split unrelated refactors into their own pull request.
3. Describe the behaviour change and the checks you ran.
4. Link the issue it closes, if there is one.

## Contributers
1. Umang-sudo-su
2. Saksham-bot-design
3. shraddha-x
4. ayushmansarkar5-stack
5. Shivam-22-su
6. Urshita-M
