# AdvisoryTrail

**Dependency security scanning for every GitHub repository you own — with the review trail an audit needs.**

AdvisoryTrail connects to real GitHub repositories, scans their pinned dependencies with
[OSV-Scanner](https://google.github.io/osv-scanner/), turns the results into a per-package advisory
list with real severities and fixed versions, and records every triage decision in an immutable
audit trail. It runs as a single Docker Compose stack: FastAPI, PostgreSQL, a React dashboard and a
local mail sink for testing notifications.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-3776ab.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-19-149eca.svg)](https://react.dev/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ed.svg)](https://docs.docker.com/compose/)

---

## Why AdvisoryTrail

Most scanners stop at "you have a vulnerable dependency". The hard part in a real team is what
happens next: who accepted the risk, why, and can you prove it six months later.

AdvisoryTrail is built around that review step:

- **Real repositories only.** A repository is added only after GitHub confirms it exists and that
  the connected account can read it. Private repositories are supported; typos and inaccessible
  repositories are rejected with a specific reason instead of silently creating a broken entry.
- **One finding per advisory, not per package.** A pinned version such as `handlebars@4.0.5` can
  carry twenty advisories. Each gets its own severity, summary, fixed version and review state, and
  a package-level **bulk action** applies one decision to all of them at once.
- **Everything is audited.** Reviews, policy changes, settings edits, repository connections and
  webhook deliveries land in an audit log with actor, timestamp and justification.

## Features

| Area | What you get |
| --- | --- |
| **Repositories** | GitHub URL or `owner/name` input, real existence + access check, branch verification, duplicate protection, public/private badges |
| **Scans** | Manual and scheduled scans, PR webhook triggers, live progress over server-sent events, duration and findings counts, commit statuses written back to GitHub when the token allows it |
| **Findings** | OSV advisories with real severity, summary and fixed version, grouped by package + version, search and severity/change filters, per-advisory review (Open / Dismissed / False Positive) and package-level bulk review |
| **Policies** | Report / warn / enforce modes with per-rule toggles, persisted and audited |
| **Audit log** | Filterable trail with CSV/JSON export and a signature/deduplication monitor |
| **Accounts** | Session tokens, TOTP two-factor with recovery codes, session listing and revocation, API tokens with scopes |
| **Integrations** | GitHub OAuth or personal access token, webhook registration, outbound webhook endpoints with SSRF protection, email notifications (MailHog locally) |
| **Hardening** | Per-route rate limits, security headers, `no-store` on API responses, request body cap, generic health output, secret-aware pre-commit hook |

## Architecture

```
                     ┌──────────────────────────────┐
   browser  ───────► │  web (nginx + React 19 SPA)  │  :3000
                     └──────────────┬───────────────┘
                                    │ /api proxied to
                     ┌──────────────▼───────────────┐
                     │  api (FastAPI + SQLAlchemy)  │  :8000  ──► OSV-Scanner
                     └──────┬───────────────┬───────┘             (osv.dev API)
                            │               │
              ┌─────────────▼────┐   ┌──────▼────────────┐
              │ PostgreSQL 16    │   │ MailHog (SMTP/UI) │  :1025 / :8025
              └──────────────────┘   └───────────────────┘
```

| Layer | Technology |
| --- | --- |
| Dashboard | React 19, TypeScript, Vite, React Router, Lucide icons, nginx |
| API | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, PyJWT, bcrypt |
| Scanning | [osv-scanner](https://google.github.io/osv-scanner/) CLI + the OSV.dev API for advisory detail |
| Data | PostgreSQL 16 |
| Email | MailHog in development, any SMTP server in production |

## Quick start

**Prerequisites:** Docker Desktop (or Docker Engine + Compose v2). Nothing else needs to be installed —
Python and Node run inside containers.

```bash
git clone https://github.com/Umang-sudo-su/advisorytrail.git
cd advisorytrail
docker compose up --build
```

The first run starts the `setup` service, which asks for:

1. a GitHub personal access token (optional, but needed for private repositories and commit statuses),
2. a webhook secret (generated for you by default),
3. the admin username, email and password.

It writes `.env` at the repository root, applies migrations and creates the admin account. The
stack is then reachable at:

| Service | URL |
| --- | --- |
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| MailHog inbox | http://localhost:8025 |
| PostgreSQL | `localhost:5433` |

Sign in with the admin account you created and connect your first repository.

### Launcher (optional)

`./advisorytrail` (macOS/Linux) and `advisorytrail.cmd` (Windows) wrap the common operations:

| Command | Purpose |
| --- | --- |
| `./advisorytrail` | Start the whole stack (default) |
| `./advisorytrail status` | Container and endpoint health |
| `./advisorytrail logs [service]` | Follow logs (`api`, `web`, `db`, `mailhog`) |
| `./advisorytrail restart` | Restart application services |
| `./advisorytrail monitor` | Watch health and restart failed services |
| `./advisorytrail doctor` | Diagnose Docker and the configuration |
| `./advisorytrail reset-data` | Delete all data and recreate the admin account |
| `./advisorytrail open` | Open the dashboard in your browser |
| `./advisorytrail stop` | Stop the stack |

## Configuration

`docker compose up --build` generates `.env` for you; [`.env.example`](.env.example) documents every
variable. Re-run the wizard to change values:

```bash
docker compose run --rm -e ADVISORYTRAIL_RECONFIGURE=1 setup
```

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signing key for API session tokens (generated by the wizard) |
| `GITHUB_WEBHOOK_SECRET` | HMAC secret GitHub signs webhook deliveries with |
| `GITHUB_TOKEN` | Personal access token used to read manifests, verify repositories and set commit statuses |
| `GITHUB_REPOSITORY` | Optional `owner/name` the webhook is attached to |
| `PUBLIC_BASE_URL` | URL GitHub can reach, used for webhook callbacks |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | Optional GitHub OAuth app for the Connect button |
| `SMTP_*` | Real email delivery; leave blank to use MailHog |
| `WEB_PORT` / `API_PORT` / `DB_PORT` | Published host ports (default `3000` / `8000` / `5433`) |

**Token scopes.** Classic tokens need `repo` (private repositories, commit statuses) and
`admin:repo_hook` only if AdvisoryTrail should create the webhook for you. Without write access,
commit statuses are skipped and the API logs the exact reason (`GitHub refused it (HTTP 403); the
connected token needs write access to owner/repo`).

## Using AdvisoryTrail

### Connect a repository

Paste `https://github.com/owner/repository` or `owner/repository`, choose the branch and submit.
AdvisoryTrail verifies with GitHub that:

- the URL points at `github.com` (other hosts are refused),
- the repository exists,
- the connected account can read it (private repositories need `pull`),
- the branch exists,
- it is not already connected.

Each failure returns its own message, for example `GitHub could not find owner/repo. Check the owner
and name; if the repository is private, the connected GitHub account (account) may not have access
to it.`

### Scan

Use **Trigger Local Scan** on a repository card or open a pull request on a repository with a webhook
configured. Scans run in the background, stream progress to the dashboard, and finish with counts per
severity. Scanning a repository twice is safe — findings are stored per scan and grouped for review.

### Review findings

Findings are grouped by `package@version`. The detail panel lists **every advisory** affecting that
version with its own severity, summary, fixed version and three review pills:

- **Open** — not triaged yet,
- **Dismissed — Risk Accepted** — accepted with a recorded decision,
- **False Positive** — not applicable.

Dismissing one advisory leaves the others open. For a package with several advisories, the
**Set all N advisories** row applies one decision to the whole package in a single request. A list
row only shows a review badge once the entire group is settled, so a partially reviewed package can
never look finished. Every change is written to the audit log with the signed-in account as actor.

## API

Interactive documentation lives at `/docs`. The main routes:

| Method | Route | Description |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Password sign-in (returns a token or a 2FA challenge) |
| `POST` | `/api/v1/auth/2fa/verify` | Complete a two-factor challenge |
| `GET` | `/api/v1/auth/me` | Current account |
| `GET`/`POST`/`DELETE` | `/api/v1/repositories/` | List, connect and remove repositories |
| `GET`/`POST` | `/api/v1/scans/` | List and trigger scans |
| `GET`/`DELETE` | `/api/v1/scans/{id}` | Scan status and deletion |
| `GET` | `/api/v1/findings/` | Findings with advisory detail |
| `PATCH` | `/api/v1/findings/{id}` | Review one advisory |
| `PATCH` | `/api/v1/findings/bulk` | Review every advisory of a package at once |
| `GET` | `/api/v1/stats/` | Dashboard counters and severity breakdown |
| `GET` | `/api/v1/audit-logs/` | Filterable audit trail (`/export` for CSV or JSON) |
| `GET`/`PUT` | `/api/v1/policies/` | Policy mode and rules |
| `POST` | `/api/v1/webhooks/github` | Signed GitHub delivery endpoint |
| `GET` | `/api/v1/events` | Server-sent events for live refresh |
| `GET` | `/health` | Liveness probe |

All endpoints except `/health`, `/api/v1/webhooks/github` and the auth endpoints require a session
token (`Authorization: Bearer <token>`).

## Security

- Session tokens are signed JWTs; only the server holds `SECRET_KEY`.
- Reviews and scans require an authenticated session and record the real actor.
- Webhook deliveries are verified with HMAC-SHA256 before any work happens.
- Outbound webhook URLs are validated against loopback, private, link-local and metadata addresses
  to block server-side request forgery.
- Login, two-factor, registration and repository-connection routes are rate limited.
- Security headers are set on every response; API responses are `Cache-Control: no-store`.
- Secrets live in `.env`, which is git-ignored. `git config core.hooksPath .githooks` enables a
  pre-commit guard that blocks staged environment files and credential-looking strings.

Found a vulnerability? Please read [SECURITY.md](SECURITY.md) before opening a public issue.

## Development

Run the stack with `docker compose up --build`; the API reloads through a rebuild.

**Backend**

```bash
docker compose exec api python -m pytest -q        # 36 tests
cd services/api && uvicorn app.main:app --reload   # only when running outside Docker
```

**Dashboard**

```bash
cd advisorytrail-dashboard
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production bundle
npm run lint
```

## Project structure

```
.
├── advisorytrail-dashboard/        React + TypeScript dashboard (Vite, nginx image)
│   └── src/
│       ├── pages/                Dashboard, Repositories, Scans, Findings, Policies, AuditLogs, Settings, Login
│       ├── components/           Layout, status badges, page states, live indicator
│       ├── api.ts                Typed API client and session storage
│       └── useFetch.ts           Polling + live-refresh data hook
├── services/api/                 FastAPI application
│   ├── app/
│   │   ├── routers/              auth, repositories, scans, findings, policies, settings, audit logs, webhooks, events, stats
│   │   ├── services/             scanner, GitHub repository validation, rate limiting, URL guard, notifications, scheduler, TOTP
│   │   ├── scanners/             OSV-Scanner adapter
│   │   └── setup_wizard.py       First-run configuration
│   └── tests/                    Pytest suite
├── tools/advisorytrail_launcher.py Cross-platform launcher behind `./advisorytrail`
├── docker-compose.yml            The whole platform in one file
└── .env.example                  Documented configuration template
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, local
checks and commit conventions.

## License

Released under the [MIT License](LICENSE).

## Acknowledgements

AdvisoryTrail stands on [OSV](https://osv.dev/) and [osv-scanner](https://github.com/google/osv-scanner)
for vulnerability data, and on FastAPI, SQLAlchemy, React, Vite and PostgreSQL.
