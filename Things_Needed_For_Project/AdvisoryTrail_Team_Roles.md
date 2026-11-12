# AdvisoryTrail — Six-Member Team Roles & Responsibilities

**Project:** AdvisoryTrail — a security and reliability platform for software teams  
**Team size:** 6 members  
**Purpose:** Define ownership, first deliverables, collaboration rules, and a shared workflow.

> Replace `Member 2` through `Member 6` with teammates' names once roles are agreed. Umang's role is assigned below.

---

## 1. Team role assignments

### Member 1 — Umang: Backend & Database Lead

**Primary ownership:** Backend API, database design, and integration between services.

**Responsibilities**
- Build the backend using Python and FastAPI.
- Design PostgreSQL tables for repositories, scans, findings, and relevant user or installation records.
- Create API endpoints for the frontend to request scan results and statuses.
- Validate requests and responses, and implement consistent error handling.
- Store normalized scanner findings and scan lifecycle states.
- Coordinate API contracts with the frontend, GitHub integration, scanner, and risk-engine owners.
- Review database migrations and backend integration changes.

**Skills to learn or strengthen**
- FastAPI, Pydantic, PostgreSQL, SQLAlchemy, database migrations, pytest, authentication and authorization, Git, and background-job processing.

**Definition of success**
- The backend starts locally, connects to PostgreSQL, accepts valid requests, stores scan data, and returns documented API responses.
- Errors and incomplete scans are represented clearly; a failed scan is never reported as a clean scan.
- Tests cover the main endpoints and database operations.

**First deliverable**
- A working FastAPI service with a health endpoint, an initial database schema, and an endpoint that stores and returns a test finding.

### Member 2 — Frontend Developer

**Primary ownership:** The AdvisoryTrail web dashboard.

**Responsibilities**
- Build the dashboard and navigation.
- Create repository, scan history, scan status, and finding-detail views.
- Display severity, scan outcomes, and new/resolved/unchanged findings.
- Connect the interface to Umang's documented APIs.
- Implement loading, empty, error, and retry states.
- Start with realistic mock data while the backend is under development.

**Skills to learn or strengthen**
- HTML, CSS, JavaScript, React, TypeScript, accessible UI design, and API requests.

**Definition of success**
- A user can navigate the dashboard and understand scan results, including when a scan has failed or is still running.

**First deliverable**
- A dashboard layout with repository and findings views using mock data.

### Member 3 — GitHub Integration Engineer

**Primary ownership:** GitHub App, webhooks, and GitHub Check Runs.

**Responsibilities**
- Learn GitHub Apps, installation permissions, webhooks, and Check Runs.
- Receive relevant repository and pull-request events.
- Verify webhook signatures before processing events.
- Trigger scans through the backend contract agreed with Umang.
- Handle duplicate webhook deliveries idempotently.
- Publish concise scan summaries to GitHub Check Runs.
- Document required GitHub App permissions and setup.

**Skills to learn or strengthen**
- GitHub REST APIs, webhooks, Python or JavaScript, JSON, authentication, and Git.

**Definition of success**
- A test repository event can safely trigger a scan, and a result can be published to GitHub.

**First deliverable**
- A GitHub App proof of concept with a verified webhook receiver and documented event flow.

### Member 4 — Security Scanner Engineer

**Primary ownership:** Running a scanner and extracting structured vulnerability findings.

**Responsibilities**
- Integrate OSV-Scanner for dependency vulnerability detection.
- Test against sample repositories and dependency manifests.
- Convert raw scanner output into the agreed finding format.
- Extract package, installed version, vulnerability identifier, severity when available, and evidence.
- Handle scanner timeouts, invalid input, missing manifests, and non-zero exit codes.
- Document scanner limitations and supported inputs.
- Coordinate the output schema with Member 5 and Umang.

**Skills to learn or strengthen**
- Python, command-line tools, JSON, dependency manifests, vulnerability databases, subprocess safety, and testing.

**Definition of success**
- The scanner produces consistent structured output for known test cases and reports errors distinctly from successful scans with no findings.

**First deliverable**
- A local scanning module that runs OSV-Scanner against a sample repository and returns normalized JSON.

**Important safety rule**
- Do not execute repository scripts or arbitrary project code as part of scanning. Treat repository contents as untrusted input and run scanning with least privilege and resource limits.

### Member 5 — Risk Engine & Findings Intelligence Engineer

**Primary ownership:** Deduplication, comparison between scans, and transparent prioritization.

**Responsibilities**
- Agree on a shared finding format with Member 4 and Umang.
- Create stable fingerprints so the same finding can be recognized across scans.
- Compare a scan with the prior baseline and classify findings as new, resolved, or unchanged where evidence permits.
- Implement understandable, deterministic risk-prioritization rules.
- Record the evidence behind risk decisions.
- Add unit tests for duplicate findings, missing fields, changed package versions, and edge cases.
- Research optional AI explanations only after the deterministic pipeline works.

**Skills to learn or strengthen**
- Python, data structures, algorithms, SQL basics, testing, and security concepts.

**Definition of success**
- Repeated findings are deduplicated consistently, scan comparisons are testable, and prioritization rules are documented rather than presented as unexplained scores.

**First deliverable**
- A standalone Python module that accepts sample findings, fingerprints them, compares two scans, and returns classifications.

### Member 6 — DevOps, Testing & Application Security

**Primary ownership:** Reproducible development, CI, test strategy, and operational safeguards.

**Responsibilities**
- Set up repository conventions, branch protection where available, pull-request templates, and issue templates.
- Create Docker Compose configuration for local development.
- Configure automated tests and CI using GitHub Actions.
- Test API endpoints, scanner failure cases, webhook handling, and integration paths.
- Review secret handling, permissions, tenant isolation, and logs for sensitive data.
- Document local setup, environment variables, test commands, and deployment.
- Coordinate fixes with the relevant module owner.

**Skills to learn or strengthen**
- Git, Docker, GitHub Actions, pytest, environment variables, CI, and application-security fundamentals.

**Definition of success**
- A new teammate can follow the documentation to run the application and tests locally, and CI catches common regressions.

**First deliverable**
- A clean repository workflow, initial CI pipeline, Docker Compose setup, and a concise developer setup guide.

---

## 2. End-to-end workflow

1. **Member 3 — GitHub integration:** Receives and verifies a GitHub event.
2. **Umang — Backend:** Validates the event, creates a scan record, and queues the scan.
3. **Member 4 — Scanner:** Scans supported dependency files and emits structured results.
4. **Member 5 — Risk engine:** Normalizes, deduplicates, compares, and prioritizes findings.
5. **Umang — Backend/database:** Stores results and exposes scan data through documented APIs.
6. **Member 2 — Frontend:** Displays results in the dashboard.
7. **Member 3 — GitHub integration:** Publishes the summary as a GitHub Check Run.
8. **Member 6 — DevOps/testing/security:** Tests the complete flow and maintains CI and setup documentation throughout development.

The first version can use a simple local flow for development, but add a background queue before running potentially slow scans in a deployed environment.

---

## 3. First two weeks: concrete deliverables

| Owner | Deliverable by the end of week 2 |
|---|---|
| Umang | FastAPI service, initial PostgreSQL schema, health endpoint, and first finding endpoint |
| Member 2 | Dashboard layout with repository and findings views using mock data |
| Member 3 | GitHub App proof of concept and verified webhook receiver |
| Member 4 | OSV-Scanner working on a sample repository and returning JSON |
| Member 5 | Finding schema proposal, fingerprinting prototype, and unit tests |
| Member 6 | Repository workflow, Docker Compose, initial CI, and setup guide |

At the end of week 2, hold a short demo. Each member should show what works, what is blocked, and what they need from another member. Mock data is acceptable for early frontend work.

---

## 4. Shared finding format

Before separate modules are built, Members 2, 4, and 5 should agree on a finding contract with Umang. For example:

```json
{
  "fingerprint": "stable-finding-id",
  "type": "dependency_vulnerability",
  "package": "example-package",
  "installed_version": "1.2.0",
  "vulnerability_id": "CVE-YYYY-NNNN",
  "severity": "high",
  "summary": "Illustrative test finding",
  "status": "new"
}
```

This is illustrative test data, not a real vulnerability report. Document required and optional fields, accepted severity values, and how the schema changes over time. Do not silently invent missing scanner evidence.

Suggested scan statuses: `queued`, `running`, `succeeded`, `failed`, `incomplete`.

Suggested finding comparison statuses: `new`, `unchanged`, `resolved`.

Keep **scan status** separate from **finding comparison status**.

---

## 5. Collaboration rules

1. **One shared repository.** Use feature branches and pull requests instead of making unrelated copies.
2. **One owner per module.** Other members can contribute, but the named owner is responsible for keeping the module working.
3. **Agree on contracts early.** Document endpoint paths, request/response examples, finding fields, and scan states before integration.
4. **Integrate weekly.** Do not postpone integration until the final month.
5. **Review important changes.** Pay special attention to authentication, database access, scanner execution, webhooks, and tenant isolation.
6. **Never commit secrets.** Keep local `.env` files out of version control and provide a safe `.env.example` with placeholder values.
7. **Report scan failures honestly.** A timeout, scanner error, or incomplete scan must never appear as a clean scan.
8. **Treat repositories as untrusted input.** Avoid running arbitrary repository code. Use least privilege, timeouts, resource limits, and isolated workers.
9. **Keep work visible.** Each member should update their task with progress, blockers, and evidence of completion.
10. **Keep documentation current.** Update setup instructions and API contracts when behavior changes.

---

## 6. Umang's learning priorities

Recommended order for the backend/database role:

1. **FastAPI fundamentals:** routes, request validation, response models, dependency injection.
2. **PostgreSQL and SQLAlchemy:** tables, relationships, transactions, queries, and migrations.
3. **Pydantic and API contracts:** validate input and define consistent JSON responses.
4. **pytest:** write unit and integration tests for endpoints and database operations.
5. **Background jobs:** learn a queue such as Celery or RQ after the basic API works.
6. **Authentication and authorization:** protect endpoints and ensure users can access only permitted repositories and findings.
7. **Integration and observability:** structured logs, timeouts, retries, and clear failure states.

You do not need to master every topic before starting. Learn what is needed for the next working milestone and apply it directly to AdvisoryTrail.

---

## 7. Definition of done for a task

A task is complete when:
- The implementation matches the agreed requirements.
- Relevant tests pass.
- Inputs and errors are handled intentionally.
- No secrets or sensitive repository data are exposed in logs.
- Documentation or API examples are updated if needed.
- The change is reviewed and merged.
- The owner can demonstrate the result to the team.

---

## 8. Immediate team actions

1. Confirm each member's role and replace the Member 2–6 labels with their names.
2. Create the shared Git repository and agree on branch and pull-request conventions.
3. Have Umang, Member 4, and Member 5 finalize the initial finding schema.
4. Have Umang and Member 2 agree on the first API response shape.
5. Have Member 3 document the GitHub webhook-to-scan flow.
6. Have Member 6 make local setup and CI reproducible.
7. Start with small, demonstrable deliverables and integrate them every week.

**Guiding principle:** Build a dependable end-to-end workflow first. Add advanced scanning, AI explanations, and complex risk scoring only after the basic pipeline works reliably.
