# BuildShield — Security & Reliability Platform

BuildShield is a GitHub-integrated security and reliability platform. It sits on top of
existing dependency scanners: it normalizes their output, removes duplicate findings,
keeps pull-request context (new vs. pre-existing risk) and produces evidence-backed
reports, policies and audit trails for small teams.

## Quick start (Docker)

Works the same on Windows (PowerShell or CMD), macOS and Linux. You only need
[Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with
the Compose plugin.


```bash
git clone <this-repository> buildshield
cd buildshield
docker compose up --build
```


That single command:

1. starts PostgreSQL and the MailHog mail catcher,
2. runs the **setup wizard**, which asks for your GitHub token, webhook URL and admin
   account, writes `.env` for you, generates the signing and webhook secrets, creates
   the first admin user and, when it can, registers the GitHub webhook,
3. applies database migrations and starts the API,
4. builds and serves the dashboard.


| Service | URL |
| --- | --- |
| Dashboard | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Mail inbox (MailHog) | http://localhost:8025 |
| PostgreSQL | `localhost:5433` |

The wizard prints the admin password once, at the end of its output. Keep it.

The wizard prints the admin password once, at the end of its output. Keep it.

> First run takes a few minutes: the API image installs osv-scanner and the dashboard
> runs a Node build. Later starts are seconds.

### If you run it detached

docker compose up -d has no terminal to prompt on, so the wizard generates secure
defaults and prints the admin password in the logs (docker compose logs setup). To be
guided through GitHub instead, run the wizard on its own first:

bash
docker compose run --rm setup          # interactive, asks for token/webhook/admin
docker compose up -d

### Re-running the setup wizard

Configuration already exists? Reconfigure deliberately:

bash
# Windows PowerShell / CMD
docker compose run --rm -e BUILDSHIELD_RECONFIGURE=1 setup

# macOS / Linux
docker compose run --rm -e BUILDSHIELD_RECONFIGURE=1 setup


Setup runs on every docker compose up but exits immediately when .env is complete,
so it never blocks or overwrites your values.