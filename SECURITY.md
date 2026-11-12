# Security policy

## Supported versions

AdvisoryTrail is developed on `main`; security fixes land there first. If you run a fork or a pinned
release, rebase on `main` to receive them.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Use GitHub's private reporting channel instead: **Security → Advisories → Report a vulnerability** in
this repository. That opens a private thread with the maintainers.

Include:

- the affected endpoint, page or service,
- the impact you believe it has (data exposure, privilege escalation, SSRF, …),
- reproduction steps or a proof-of-concept,
- the version/commit you tested.

You can expect an acknowledgement within a few days and a fix or a mitigation plan in the following
weeks, depending on severity. Credit is given in the advisory unless you prefer to stay anonymous.

## What AdvisoryTrail already does

| Control | Where |
| --- | --- |
| Session tokens are signed JWTs; `SECRET_KEY` never leaves the server | `services/api/app/auth.py` |
| Every findings, scan and repository route requires a session; reviews record the real actor | `routers/findings.py`, `routers/scans.py`, `routers/repositories.py` |
| GitHub webhook deliveries are verified with HMAC-SHA256 before processing | `routers/webhooks.py` |
| Outbound webhook URLs reject loopback, private, link-local and metadata addresses (SSRF) | `services/net_guard.py` |
| Rate limits on login, two-factor, registration and repository connection | `services/rate_limit.py` |
| Security headers, `Cache-Control: no-store` on API responses, 2 MB request body cap | `app/main.py` |
| Repository input restricted to `github.com` with an existence and access check | `services/github_repos.py` |
| Secrets only in `.env` (git-ignored) with a pre-commit secret guard | `.githooks/pre-commit` |

## Hardening a deployment

- Run the stack behind HTTPS (a reverse proxy or tunnel); the bundled nginx serves plain HTTP.
- Set a strong `SECRET_KEY` and `GITHUB_WEBHOOK_SECRET` (the wizard generates both).
- Use a GitHub token scoped to the repositories you actually scan.
- Replace MailHog with a real SMTP server for anything beyond local development.
- Keep PostgreSQL on a private network; the published port is for local development only.
- Back up the `advisorytrail_db_data` volume before destructive operations such as
  `./advisorytrail reset-data`.
