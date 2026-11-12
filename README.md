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

### Change ports

Create a .env entry or export the variable before starting:

bash
WEB_PORT=8080 API_PORT=8081 docker compose up --build

## GitHub setup

### 1. Personal access token (used to read manifests and set commit statuses)

1. Open <https://github.com/settings/tokens>.
2. *Generate new token (classic)*.
3. Scopes: repo (read repository contents) and admin:repo_hook (only needed so the
   wizard can create the webhook for you).
4. Copy the token — it starts with ghp_ and is shown once.

Fine-grained tokens work too: grant *Contents: Read* and *Webhooks: Read and write*
for the repository you want to scan.

The token is stored in .env at the repository root (never committed) and can also be
changed later in the dashboard under *Settings → GitHub Integration*.

### 2. Webhook (how GitHub tells BuildShield about pull requests)

If you provide a *publicly reachable* URL during setup (a server domain or a tunnel),
the wizard creates the webhook for you. Otherwise add it by hand:

1. Repository → *Settings → Webhooks → Add webhook*.
2. *Payload URL*: https://<your-domain>/api/v1/webhooks/github
   (for local testing, expose the API with ngrok http 8000 and use the ngrok URL).
3. *Content type*: application/json.
4. *Secret*: the value printed by the wizard (GITHUB_WEBHOOK_SECRET in .env).
5. *Events: *Pull requests and Pushes.
6. Save — GitHub sends a ping; BuildShield replies pong.

GitHub cannot call localhost, so a tunnel or a deployed host is required for live
webhook deliveries. Manual scans from the dashboard work without a webhook.

## Configuration reference

All settings live in .env at the repository root; .env.example documents every key.
The wizard writes: SECRET_KEY, GITHUB_WEBHOOK_SECRET, GITHUB_TOKEN,
GITHUB_REPOSITORY, PUBLIC_BASE_URL, the optional SMTP_* block, and the admin
credentials (printed, not stored).

Email: by default every message is captured by MailHog at <http://localhost:8025>. To
send real mail, provide SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
SMTP_SECURITY (starttls, ssl or none) and SMTP_FROM.


## Running without Docker (development)

Backend:

bash
cd services/api
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then fill in SECRET_KEY and GITHUB_* values
alembic upgrade head
uvicorn app.main:app --reload

Dashboard:

bash
cd buildshield-dashboard
npm install
npm run dev              # http://localhost:5173, expects the API on :8000
