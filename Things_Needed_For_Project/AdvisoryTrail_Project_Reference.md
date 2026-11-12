# AdvisoryTrail — Project Reference and Implementation Guide

> **Document purpose:** This is the central project reference for developers, AI coding assistants, reviewers, and future contributors working on AdvisoryTrail. Use it as the source of truth for product scope, architecture, security requirements, milestones, and engineering conventions.
>
> **Project status:** Planning / initial implementation.
>
> **Target timeline:** 5 months for a usable MVP, with an optional sixth month for hardening and a wider beta.
>
> **Team:** 5–6 members.
>
> **Initial product:** A GitHub-integrated security and reliability platform that analyzes pull requests, combines findings from existing scanning tools, prioritizes actionable risks, and reports evidence-backed results to developers.

---

## 1. Project summary

AdvisoryTrail helps software teams understand which security and reliability findings deserve attention when code changes.

It integrates with GitHub repositories, reacts to pull-request events, runs selected scanners in controlled background workers, normalizes their results into a common finding model, compares results with a baseline, and presents the outcome through GitHub Checks and a web dashboard.

AdvisoryTrail is **not** intended to replace every security scanner. Its initial value is the workflow around scanners:

- Identify and report known dependency vulnerabilities.
- Distinguish findings that are new or affected by a pull request from pre-existing findings when evidence supports that distinction.
- Deduplicate equivalent findings from repeated scans or multiple tools.
- Explain findings using traceable source evidence.
- Recommend a next step without claiming more certainty than the evidence supports.
- Give developers a concise, actionable view of risk.

### 1.1 Product vision

Help small software teams ship safer code with less security-tool noise and less manual investigation.

### 1.2 Initial target users

Start with one narrow group:

- Small software teams using GitHub.
- Student or open-source teams maintaining real repositories.
- Early-stage startups or software agencies that want understandable security feedback without operating a complex security platform.

Do not target every enterprise or every programming language in the first release.

### 1.3 Core user story

> As a developer, when I open or update a pull request, I want AdvisoryTrail to scan the relevant dependency changes, show evidence-backed findings, tell me which findings are new or pre-existing when it can determine that reliably, and publish a concise result in GitHub so I can decide what to fix before merging.

### 1.4 Product principles

1. **Evidence before intelligence.** Never invent vulnerability facts or code evidence.
2. **Reuse proven scanners.** Integrate existing tools rather than building a full scanner from scratch.
3. **Secure by default.** Treat repository contents, pull requests, archives, and dependency metadata as untrusted input.
4. **Human control.** Findings and AI suggestions inform decisions; they do not silently modify or deploy code.
5. **Incremental delivery.** Every milestone should produce a working, testable result.
6. **Transparent uncertainty.** Distinguish unknown from safe, and missing evidence from a clean result.
7. **Simple architecture first.** Use a modular monolith and background workers; introduce more infrastructure only when justified.
8. **Privacy and least privilege.** Request the minimum repository permissions and retain only the data needed for the service.

---

## 2. Problem statement and product differentiation

### 2.1 Problem

Software teams can receive security findings from multiple tools. Reports may use different formats, repeat the same underlying issue, lack pull-request context, or require manual investigation. Developers need to determine:

- Is the finding valid and supported by evidence?
- Is it new, pre-existing, resolved, or still uncertain?
- Is a fix available?
- What should be done next?
- Does the issue justify blocking a pull request under the team's policy?

### 2.2 AdvisoryTrail's intended differentiator

AdvisoryTrail combines scanner results and pull-request context into an understandable workflow. Its differentiators are goals to validate with real users, not assumptions that the product is already better than competitors.

Initial differentiators:

1. Pull-request-aware reporting.
2. Stable finding fingerprints and duplicate suppression.
3. Evidence-backed explanations.
4. Clear separation of scanner severity, evidence confidence, change relationship, and policy decision.
5. Useful remediation guidance with human review.
6. A small-team-friendly setup and dashboard.

### 2.3 Competitive landscape

Existing tools already cover parts of this space, including OSV-Scanner, Semgrep, Trivy, GitHub's native security features, and other dependency and static-analysis platforms. AdvisoryTrail should integrate selected tools and focus on the workflow and prioritization layer.

Before committing to a differentiator, research current competing products, licensing, capabilities, pricing, and user complaints. Do not assume the market gap exists without validating it.

---

## 3. MVP scope

### 3.1 P0 — Required for the first usable release

- GitHub App installation on a test repository.
- Secure webhook signature verification.
- Pull-request event handling.
- Idempotent webhook processing.
- Asynchronous scan jobs.
- Dependency scanning for Python and JavaScript/TypeScript projects, subject to supported manifests and scanner capabilities.
- One scanner integration first: OSV-Scanner.
- Common normalized finding schema.
- Stable finding fingerprinting.
- Scan history and status.
- Baseline comparison where evidence permits.
- GitHub Check Run summary.
- Web dashboard for repositories, scans, and findings.
- Basic user authentication and organization/repository access control.
- Logs, retries, timeouts, and clear scan failure states.
- Automated unit and integration tests.
- Security and privacy documentation.

### 3.2 P1 — Add after P0 is reliable

- Cargo/Rust dependency support.
- Semgrep integration for selected supported rules.
- Secret detection using a well-maintained tool, with safe handling of discovered secrets.
- Improved baseline comparison.
- Finding dismissal, notes, and review history.
- Configurable repository policies.
- Notifications and scheduled scans.
- More robust reporting and export.

### 3.3 P2 — Future work, not MVP blockers

- Container image scanning.
- Infrastructure-as-code scanning.
- Advanced dependency reachability analysis.
- AI-assisted finding explanations and remediation proposals.
- Organization-wide policies and analytics.
- Enterprise SSO, advanced retention, and compliance-oriented reporting.
- Additional source-control platforms.
- Deployment and incident telemetry correlation.

### 3.4 Explicit non-goals for MVP

- Building a new general-purpose vulnerability scanner.
- Guaranteeing that a repository is secure.
- Automatically merging or deploying fixes.
- Running arbitrary pull-request code to test it.
- Automatically installing dependencies from untrusted pull requests.
- Claiming a vulnerability is exploitable without supporting evidence.
- Predicting production incidents from source code alone.
- Supporting every language, package manager, cloud, and repository host.
- Using Kubernetes, Kafka, or microservices solely for perceived sophistication.

### 3.5 MVP acceptance criteria

The MVP is acceptable when all of the following work in a test installation:

1. An authorized user installs the AdvisoryTrail GitHub App on a test repository.
2. Opening or updating a pull request triggers a scan asynchronously.
3. The scan produces a stored report, including an explicit success, partial, or failure status.
4. Findings contain a scanner/source identifier and traceable evidence when available.
5. Repeated webhook deliveries do not create duplicate scan jobs.
6. The GitHub Check Run updates with a concise result.
7. The dashboard displays scan status, findings, severity, evidence, and advisory links.
8. Repeated scans do not create duplicate active findings for the same issue.
9. The product distinguishes a clean scan from a failed or incomplete scan.
10. Security tests demonstrate that one organization cannot access another organization's records.
11. Untrusted repository content is not executed with privileged access.
12. A new pilot team can complete setup using documentation without a developer manually operating every scan.

---

## 4. Architecture

### 4.1 High-level flow

```text
GitHub App
   |
   | signed webhook
   v
FastAPI webhook service
   |
   | validate signature, event, installation and repository access
   | deduplicate delivery
   v
PostgreSQL event/job record ----> Queue (Redis/Celery or equivalent)
                                      |
                                      v
                              Isolated scan worker
                                      |
                         +------------+-------------+
                         |                          |
                         v                          v
                    OSV-Scanner             Future scanner adapters
                         |                          |
                         +------------+-------------+
                                      |
                                      v
                          Finding normalization layer
                                      |
                                      v
                     Fingerprinting + baseline comparison
                                      |
                                      v
                           Policy / priority engine
                                      |
                     +----------------+----------------+
                     |                                 |
                     v                                 v
             GitHub Check Run                    Web dashboard
```

### 4.2 Recommended initial stack

| Layer | Initial choice | Notes |
|---|---|---|
| Frontend | React + TypeScript | Dashboard and finding workflows |
| API | Python + FastAPI | Webhooks, REST API, authorization |
| Database | PostgreSQL | Application records, scan state, findings |
| Background work | Redis + Celery, or another well-understood queue | Asynchronous scans, retries and timeouts |
| Scanner | OSV-Scanner | First dependency-vulnerability integration |
| Additional scanner | Semgrep after P0 | Selected static-analysis rules |
| GitHub integration | GitHub App | Installation, webhooks, check runs |
| Local environment | Docker Compose | Reproducible developer setup |
| CI | GitHub Actions | Tests, linting, type checks and builds |
| Monitoring | Structured logs and an error/metrics service | Keep secrets and sensitive code out of logs |
| Optional language | Rust | Only for a later performance-sensitive component if measurement justifies it |

Use the simplest stack the team can operate. Do not add a Rust service merely because Rust is available. Do not add Kubernetes, Kafka, a vector database, or microservices unless a demonstrated need supports the cost.

### 4.3 Architectural approach

Start as a **modular monolith plus isolated background worker**:

- One API application.
- One web frontend.
- One relational database.
- One queue and worker process.
- Scanner adapters with clear interfaces.

Keep module boundaries clear so a component can be split later if its workload or security boundary warrants it.

### 4.4 Main modules

1. `github_integration`: app installation, webhook validation, GitHub API calls, check runs.
2. `scan_orchestrator`: creates jobs, tracks lifecycle, enforces idempotency and timeouts.
3. `scanner_adapters`: executes tools and parses structured output.
4. `finding_normalizer`: converts scanner-specific output to a common schema.
5. `fingerprinting`: identifies recurring underlying findings.
6. `baseline_engine`: compares results across base and head revisions.
7. `risk_engine`: assigns transparent priority and policy outcomes.
8. `reporting`: dashboard API, summaries and exports.
9. `identity_access`: users, organizations, memberships and authorization.
10. `audit_observability`: audit events, logs, metrics and operational diagnostics.

---

## 5. Repository structure

Suggested initial monorepo:

```text
advisorytrail/
├── apps/
│   └── web/                      # React + TypeScript dashboard
├── services/
│   ├── api/                      # FastAPI application and webhooks
│   └── worker/                   # Background scan execution
├── packages/
│   └── contracts/                # Shared schemas and API documentation
├── scanners/
│   ├── osv/                      # OSV-Scanner adapter
│   └── semgrep/                  # Later integration
├── migrations/                   # Database migrations
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── fixtures/                 # Safe test repositories and sample reports
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── THREAT_MODEL.md
│   ├── API.md
│   ├── DEVELOPMENT.md
│   ├── DEPLOYMENT.md
│   └── DECISIONS.md
├── scripts/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
└── CONTRIBUTING.md
```

Adjust the structure when implementation reveals a better boundary. Keep secrets, private keys, actual tokens, production data, and real vulnerability credentials out of source control. `.env.example` must contain placeholders only.

---

## 6. Data model

Use PostgreSQL for the initial application database. Use migrations rather than manually changing production schemas.

### 6.1 Core entities

| Entity | Purpose | Example fields |
|---|---|---|
| `users` | Dashboard identities | `id`, `email`, `created_at` |
| `organizations` | Tenant/team | `id`, `name`, `plan`, `created_at` |
| `memberships` | Organization access | `user_id`, `organization_id`, `role` |
| `installations` | GitHub App installation | `id`, `organization_id`, `github_installation_id` |
| `repositories` | Connected repositories | `id`, `installation_id`, `owner`, `name`, `default_branch` |
| `pull_requests` | Pull-request metadata | `id`, `repository_id`, `number`, `head_sha`, `base_sha` |
| `webhook_deliveries` | Delivery idempotency | `delivery_id`, `event_type`, `received_at`, `status` |
| `scans` | One scan execution | `id`, `repository_id`, `commit_sha`, `status`, timestamps |
| `findings` | Normalized scan result | `id`, `scan_id`, `fingerprint`, `category`, `severity`, `evidence` |
| `advisories` | External advisory metadata | `id`, `source`, `external_id`, `url` |
| `finding_states` | Review/dismissal history | `finding_id`, `status`, `actor_id`, `reason` |
| `audit_logs` | Important user/system actions | `actor_id`, `action`, `resource_id`, `created_at` |

The exact schema should be finalized during Phase 1. Use UUIDs for internal IDs where useful, unique constraints for external IDs, indexes for frequent lookups, and foreign keys to enforce consistency.

### 6.2 Important data-model rules

- Separate scan executions from findings so findings can be compared over time.
- Keep original scanner output or a safely minimized evidence record for traceability.
- Use a stable fingerprint for finding identity; do not rely solely on a line number.
- Store scanner name, scanner version, rule/advisory identifier, and source revision.
- Keep user dismissal and acceptance decisions separate from scanner output.
- Scope all organization-owned queries to the authorized tenant.
- Define data retention and deletion behavior.
- Do not put private repository access tokens or app private keys in ordinary database fields without a secure secrets design.

### 6.3 Example normalized finding

This is an illustrative schema only, not a real vulnerability report:

```json
{
  "fingerprint": "sha256:example-fingerprint",
  "category": "dependency_vulnerability",
  "severity": "high",
  "confidence": "high",
  "title": "Vulnerable dependency version detected",
  "package": {
    "name": "example-package",
    "installed_version": "1.2.0",
    "fixed_version": "1.2.3"
  },
  "source": {
    "scanner": "osv-scanner",
    "rule_id": "EXAMPLE-ADVISORY",
    "advisory_url": "https://example.com/advisory"
  },
  "evidence": {
    "manifest": "package-lock.json",
    "introduced_in_commit": null
  },
  "change_relationship": "unknown",
  "status": "open"
}
```

Only populate fields when supported by evidence. A dependency vulnerability detected in the head revision is not automatically a vulnerability introduced by the pull request.

---

## 7. Scan lifecycle and API design

### 7.1 Scan lifecycle

Use explicit scan states, for example:

- `queued`
- `running`
- `succeeded`
- `partial`
- `failed`
- `cancelled`
- `timed_out`

A scan with a scanner failure must not be represented as a clean scan.

### 7.2 Webhook flow

1. Receive the raw HTTP request.
2. Verify the GitHub webhook signature using the raw body and configured webhook secret.
3. Validate the event type, delivery ID, installation and repository identifiers.
4. Reject malformed or unauthorized requests.
5. Record the delivery with a uniqueness constraint.
6. Return a successful acknowledgement promptly once the event is safely recorded/queued.
7. Create or enqueue a scan job.
8. Process the job asynchronously.
9. Update scan state and the GitHub Check Run.
10. Record failures without exposing secrets or sensitive repository contents.

Webhook handlers must be idempotent. GitHub can retry delivery, and the same event may be received more than once.

### 7.3 Suggested initial API endpoints

The names below are proposals. Keep the API documented and consistent.

```text
POST   /webhooks/github
GET    /health
GET    /ready

GET    /api/v1/organizations
GET    /api/v1/repositories
GET    /api/v1/repositories/{repository_id}
GET    /api/v1/repositories/{repository_id}/scans
POST   /api/v1/repositories/{repository_id}/scans
GET    /api/v1/scans/{scan_id}
GET    /api/v1/scans/{scan_id}/findings
GET    /api/v1/findings/{finding_id}
POST   /api/v1/findings/{finding_id}/review
GET    /api/v1/audit-logs
```

All authenticated endpoints must perform server-side authorization. Never trust an organization or repository ID supplied by the client without verifying access.

### 7.4 API conventions

- Version public APIs under `/api/v1`.
- Validate input with typed schemas.
- Use consistent error responses.
- Add pagination to list endpoints.
- Use idempotency controls for operations that may be retried.
- Do not return secrets or unnecessary raw scanner output.
- Generate and maintain OpenAPI documentation.
- Apply rate limits and appropriate request size limits.

---

## 8. Scanner integration

### 8.1 First scanner: OSV-Scanner

Use OSV-Scanner as the first dependency-scanning engine. Review its official documentation and supported ecosystems/manifests before deciding exactly which lockfiles to support.

Implementation tasks:

1. Pin and document the scanner version.
2. Create a scanner adapter with a narrow interface.
3. Invoke the scanner in a controlled worker environment.
4. Prefer structured output over scraping terminal text.
5. Apply execution time, output-size and resource limits.
6. Capture exit status and classify errors correctly.
7. Parse scanner output into the normalized schema.
8. Test parsing with checked-in sample output fixtures.
9. Keep scanner execution and output parsing separate.
10. Add regression fixtures for known vulnerable and patched dependency states.

Do not install dependencies or execute repository build scripts just to inspect a manifest. Test scanner behavior in a disposable environment.

### 8.2 Scanner adapter interface

Conceptual Python interface:

```python
from typing import Protocol, Any

class ScannerAdapter(Protocol):
    name: str
    version: str

    def scan(self, target: str) -> dict[str, Any]:
        """Run a constrained scan and return structured scanner output."""
        ...
```

This is a starting point, not production-ready code. In production, define timeouts, structured error types, cancellation, output-size limits, environment restrictions, and a typed result schema. Do not let an adapter execute arbitrary shell commands assembled from user input.

### 8.3 Add Semgrep later

Only add Semgrep after the first end-to-end dependency-scanning workflow is reliable. Select rules appropriate to the languages you support. Record rule IDs, locations, and evidence. Expect false positives and make review and suppression behavior explicit.

### 8.4 Future language support

Potential order based on team skills and pilot demand:

1. Python manifests.
2. JavaScript/TypeScript lockfiles.
3. Rust/Cargo.
4. Java package ecosystems.
5. Container and infrastructure artifacts.

Actual support depends on the scanner and format version. Test each ecosystem rather than advertising support based only on the programming language name.

---

## 9. Finding normalization, deduplication, and baseline comparison

### 9.1 Normalize, do not erase provenance

Each normalized finding should retain its original source information. A finding should be traceable to the scanner and advisory or rule that produced it.

Suggested fields:

- `category`
- `severity`
- `confidence`
- `title`
- `description`
- `scanner_name`
- `scanner_version`
- `rule_id` or advisory ID
- `package_name` and affected version, if relevant
- `file_path` and location, if relevant
- `evidence`
- `remediation`
- `fingerprint`
- `first_seen_at`
- `last_seen_at`
- `change_relationship`
- `review_status`

Use `unknown` when evidence is insufficient. Do not turn unknown into safe.

### 9.2 Fingerprinting

A fingerprint should be stable enough to identify the same underlying issue across repeated scans but specific enough not to merge distinct issues.

For dependency findings, a fingerprint may use a normalized combination of advisory ID, package identity, dependency path when available, and relevant artifact context. For code findings, use rule ID, normalized path, and stable source context rather than only line number.

Test fingerprints against:

- Same finding in repeated scans.
- Line numbers shifting after an unrelated edit.
- Two different vulnerable packages.
- Same advisory affecting different dependency paths.
- A finding that is fixed and later reintroduced.

### 9.3 Baseline comparison

Compare scan results for the base and head commits when feasible. Use the following relationships:

- `new`: supported evidence indicates it appears only in the head result.
- `existing`: present in the baseline and still present.
- `resolved`: present in the baseline and absent from a successful head scan.
- `changed`: evidence indicates the finding's relevant attributes changed.
- `unknown`: a reliable comparison cannot be made.

A missing result caused by a failed or partial scan is not proof that a finding was resolved.

---

## 10. Risk and policy engine

Build a deterministic, explainable rules engine before adding machine learning.

Keep these dimensions separate:

1. **Severity:** the scanner/advisory's technical severity, when available.
2. **Confidence:** the strength and completeness of the evidence.
3. **Change relationship:** new, existing, resolved, changed, or unknown.
4. **Remediation:** fixed version, mitigation, or no known fix.
5. **Policy decision:** informational, warn, or block, according to a configured team policy.

Do not produce an opaque score such as `93/100` unless its meaning has been defined, tested, and documented.

Every priority decision should have a reason, such as:

- “High-severity advisory; a fixed version is reported by the source.”
- “Finding existed in the base revision.”
- “Change relationship could not be established because the baseline scan was incomplete.”
- “This repository policy blocks new critical findings.”

Policy enforcement should be configurable and conservative. A failed scan should be reported as failed or incomplete, not as success. Avoid blocking all pull requests by default before teams understand the signal quality.

### 10.1 Evaluation dataset

Create a small, version-controlled set of safe test fixtures containing:

- Known vulnerable dependency versions.
- Corresponding patched versions.
- Pre-existing findings.
- New dependency changes.
- Clean projects.
- Malformed manifests.
- Scanner failures and timeouts.
- Duplicate findings from sample reports.

Record expected outcomes and run these tests whenever the scanner adapter, normalizer, fingerprint logic, or policy engine changes.

### 10.2 Metrics

Measure:

- Finding precision on reviewed test cases.
- False-positive rate.
- Detection of known fixture findings.
- Duplicate rate.
- Percentage of findings with usable evidence.
- Scan success and timeout rates.
- Median and p95 scan duration.
- Cost per scan.
- Developer time to investigate.
- Pilot retention and repeat usage.

Do not claim production security effectiveness from a small synthetic test set alone.

---

## 11. AI features — optional and evidence-grounded

AI is not a prerequisite for the MVP. Add it only after deterministic reports are trustworthy.

Potential AI-assisted features:

- Plain-language summaries of findings.
- Explanations of why a dependency update matters.
- Targeted test suggestions.
- Draft remediation patches for review.
- Summaries of changes in risk between two commits.

### Rules for AI use

1. Ground the model in actual scanner output, advisories, and relevant code context.
2. Require links or references to the evidence used.
3. Treat repository content, comments, issue text, and dependency metadata as untrusted data, not instructions.
4. Do not send private source code to an external model without explicit authorization and a clear data policy.
5. Never let an LLM independently decide that code is safe.
6. Never automatically apply or deploy an AI-generated patch.
7. Use a human review step and automated tests for suggested fixes.
8. Track hallucinations, unsupported claims, latency, and cost.
9. If evidence is insufficient, the model must say so.

A future AI feature should be evaluated against a deterministic baseline. If it does not measurably reduce investigation time or improve understanding without adding incorrect claims, do not ship it.

---

## 12. Security and threat model

AdvisoryTrail is a security-sensitive product. Its own architecture must not create a path for untrusted repositories to compromise the service.

### 12.1 Main threats

- Forged or replayed webhooks.
- Stolen GitHub App credentials.
- Malicious pull-request content.
- Dependency or manifest parser vulnerabilities.
- Scanner resource exhaustion.
- Command injection or unsafe path handling.
- Cross-tenant data access.
- Sensitive source code or secrets leaking into logs.
- Prompt injection in repository content if AI is added.
- Supply-chain attacks against AdvisoryTrail's own dependencies or build pipeline.

### 12.2 Mandatory controls

#### GitHub integration

- Verify webhook signatures using the raw request body and configured secret.
- Validate event type and installation context.
- Use minimum required GitHub App permissions.
- Store app private keys and tokens in a secrets manager or equivalent protected environment.
- Avoid logging installation tokens, private keys, webhook secrets, or source contents.
- Deduplicate webhook deliveries.
- Rotate credentials and document revocation procedures.

#### Scanner isolation

- Treat repositories, manifests, archives, and pull requests as untrusted.
- Avoid executing repository code during the MVP.
- Run scanner jobs in restricted, short-lived workers/containers.
- Do not use privileged containers.
- Restrict host filesystem access.
- Restrict outbound network access to what is required.
- Apply CPU, memory, disk, output-size, and time limits.
- Avoid mounting secrets into scan containers.
- Never interpolate user-controlled values into shell commands.
- Validate repository paths and guard against path traversal and symlink escapes.
- Use an approved, pinned scanner binary or image and verify its provenance.

#### Application and data

- Enforce authorization server-side on every tenant-owned resource.
- Use parameterized database queries or a safe ORM.
- Protect sessions and authentication flows.
- Encrypt traffic and protect sensitive stored data.
- Apply rate limits and request size limits.
- Use audit logs for important administrative actions.
- Define retention, deletion, backup, and restore procedures.
- Test cross-tenant access explicitly.
- Keep development, test, and production credentials separate.

#### CI/CD

- Pin critical actions and dependencies where practical.
- Run tests, linting, and dependency checks on pull requests.
- Protect production deployment credentials.
- Do not expose secrets to untrusted fork pull-request jobs.
- Require review for changes to workflows and security-critical code.

### 12.3 Security test cases

At minimum, test:

- Invalid webhook signature is rejected.
- Repeated delivery does not duplicate work.
- Unauthorized repository or organization access is denied.
- Malformed scanner output fails safely.
- Oversized inputs and timeouts are handled.
- A failed scan is never shown as clean.
- Scanner process cannot access application secrets.
- Untrusted paths cannot escape the scan workspace.
- Logs redact secrets.
- Repository disconnection prevents future access and follows the documented data policy.

---

## 13. Team responsibilities

Assign clear ownership, but keep integration and reviews shared.

### Member 1 — Technical lead and integration

- Own architecture, module boundaries, API contracts, code review, and technical decisions.
- Coordinate integration and maintain the decision log.
- Help unblock cross-module work.

### Member 2 — Frontend and user experience

- Build the dashboard, repository list, scan history, finding detail pages, filters, and review flows.
- Add loading, empty, error, partial, and failed states.
- Ensure the interface does not confuse a failed scan with a clean scan.

### Member 3 — Backend and database

- Own FastAPI, data model, migrations, authentication, authorization, and API contracts.
- Implement scan state and finding lifecycle.
- Enforce tenant isolation.

### Member 4 — GitHub integration

- Own GitHub App registration, webhook validation, event processing, check runs, and installation lifecycle.
- Test permission minimization and event retries.
- Maintain GitHub integration documentation.

### Member 5 — Scanner and risk engine

- Own OSV-Scanner integration, parsing, normalized findings, fingerprints, baseline comparison, and deterministic prioritization.
- Maintain test fixtures and evaluation metrics.

### Member 6 — Security, QA, and deployment

- Own threat modeling, isolated worker execution, automated tests, Docker, CI/CD, monitoring, backups, and pilot feedback.
- Review security-sensitive changes.

For a five-person team, combine deployment/QA with the technical lead or backend owner. Share testing and documentation across all members.

### Team working agreements

- Work in one-week sprints.
- Keep tasks small enough to finish in one to three days where practical.
- Use feature branches and pull requests.
- Require at least one review for every code change.
- Run automated checks before merging.
- Demo working software every week.
- Keep a record of architectural decisions.
- Do not merge features that have not been integrated and tested.
- Maintain a visible backlog with priorities and owners.

---

## 14. Five-month roadmap

### Phase 0 — Planning and validation (Week 1)

**Objectives**
- Validate the problem with developers.
- Select the initial differentiator.
- Agree on MVP scope and explicit non-goals.
- Set up repository, project board, conventions, and architecture.

**Deliverables**
- One-page product brief.
- PRD.
- Initial architecture diagram.
- Threat-model draft.
- Backlog with acceptance criteria.

**Exit gate:** Every member can explain the target user, core workflow, system boundaries, and MVP acceptance criteria.

### Phase 1 — Local scanner prototype (Weeks 2–4)

**Objectives**
- Run OSV-Scanner on controlled test projects.
- Parse structured output.
- Normalize and persist findings.
- Build a minimal dashboard.

**Deliverables**
- Scanner adapter.
- Normalized finding schema.
- PostgreSQL migrations.
- Basic scan API.
- Simple dashboard.
- Unit tests and fixtures.

**Exit gate:** A user can scan a test project, store the report, and view findings without GitHub integration.

### Phase 2 — GitHub integration (Weeks 5–8)

**Objectives**
- Register a development GitHub App.
- Validate webhooks.
- Handle pull-request events.
- Queue scan jobs.
- Publish GitHub Check Runs.

**Deliverables**
- Webhook endpoint.
- Delivery deduplication.
- Queue/worker workflow.
- Installation and repository handling.
- Check Run integration.
- Integration tests for pull-request lifecycle events.

**Exit gate:** A dependency change in a test pull request triggers an automated scan and a visible check result.

### Phase 3 — Risk engine and baseline (Weeks 9–12)

**Objectives**
- Compare findings across revisions.
- Improve fingerprinting and deduplication.
- Introduce deterministic priority and policy rules.
- Improve report explanations and evidence.

**Deliverables**
- Baseline comparison.
- Finding lifecycle and review states.
- Configurable policy behavior.
- Better dashboard filters and detail pages.
- Evaluation dataset and regression suite.

**Exit gate:** Repeated scans produce stable results, and users can understand why findings are prioritized.

### Phase 4 — Reliability and security hardening (Weeks 13–16)

**Objectives**
- Isolate scanner execution.
- Add retries, timeouts, and failure recovery.
- Test authorization and tenant isolation.
- Improve observability and operational safety.

**Deliverables**
- Restricted worker configuration.
- Structured logs and operational metrics.
- Failure recovery tests.
- Backup and restore procedures.
- Security test report.
- Deployment documentation.

**Exit gate:** The system handles common failures without losing records, exposing credentials, or reporting failed scans as clean.

### Phase 5 — Pilot and MVP release (Weeks 17–20)

**Objectives**
- Recruit 3–5 pilot teams.
- Observe actual usage.
- Measure value and identify friction.
- Fix high-impact issues before expanding scope.

**Deliverables**
- Pilot onboarding guide.
- Production-like deployment.
- User documentation.
- Product demo.
- Metrics summary.
- Prioritized post-MVP roadmap.

**Exit gate:** A new pilot team can install and use the core workflow without your team manually operating every scan.

### Optional Month 6

Use the additional month to improve reliability, expand support based on demand, refine the product differentiator, and prepare a broader beta. Do not automatically spend it adding more features.

---

## 15. First seven days: actionable checklist

### Day 1 — Workspace and scope

- [ ] Create a GitHub organization and project repository.
- [ ] Create a project board with Backlog, Ready, In Progress, Review, and Done.
- [ ] Write the product brief and MVP acceptance criteria.
- [ ] Assign primary owners.

### Day 2 — Scanner research

- [ ] Install OSV-Scanner locally.
- [ ] Scan a disposable sample project.
- [ ] Inspect structured output and supported formats.
- [ ] Compare OSV-Scanner, Semgrep, and Trivy.
- [ ] Choose only the first scanner for implementation.

### Day 3 — Design

- [ ] Draw the architecture and data flow.
- [ ] Define scan lifecycle states.
- [ ] Draft the finding schema.
- [ ] Agree on API contracts.
- [ ] Record open questions in `docs/DECISIONS.md`.

### Day 4 — Development setup

- [ ] Create FastAPI and React application skeletons.
- [ ] Set up PostgreSQL and Docker Compose.
- [ ] Add `.env.example` with placeholders only.
- [ ] Configure linting, formatting, tests, and CI.
- [ ] Add database migrations.

### Day 5 — First vertical slice

- [ ] Create a local scan endpoint.
- [ ] Run the scanner through a controlled adapter.
- [ ] Normalize one finding type.
- [ ] Store scan and finding records.
- [ ] Display a report in the dashboard.

### Day 6 — Validation

- [ ] Test vulnerable and patched dependency fixtures.
- [ ] Test empty and malformed scanner output.
- [ ] Test scanner errors and timeouts.
- [ ] Implement stable identifiers and basic duplicate detection.
- [ ] Review logs for accidental sensitive data.

### Day 7 — Demo and next sprint

- [ ] Demonstrate the complete local workflow.
- [ ] Review architecture and technical blockers.
- [ ] Agree on GitHub App integration tasks.
- [ ] Update the backlog with measured findings and next steps.

---

## 16. Testing strategy

Testing is part of implementation, not a final phase.

### Unit tests

Cover:

- Severity normalization.
- Fingerprint generation.
- Scanner-output parsing.
- Finding deduplication.
- Baseline comparison.
- Policy decisions.
- Authorization helpers.
- Input validation.

### Integration tests

Cover:

- Database migrations and persistence.
- Queue creation and worker lifecycle.
- Webhook validation and delivery deduplication.
- Scanner adapter execution in a controlled environment.
- GitHub Check Run updates.
- API authorization and pagination.

### End-to-end tests

Cover the main workflow:

1. Install or configure a test GitHub App.
2. Open or update a test pull request.
3. Receive and validate the webhook.
4. Queue and execute a scan.
5. Persist and normalize findings.
6. Update the GitHub Check Run.
7. Display the report in the dashboard.

### Security tests

Cover malformed inputs, oversized artifacts, path traversal, scanner timeouts, cross-tenant access, secret redaction, replayed events, and failure-state handling.

Use safe, intentionally constructed fixtures. Do not test against systems you do not own or have explicit permission to assess.

---

## 17. Deployment and operations

### Initial deployment

- Deploy the React frontend to a suitable frontend host.
- Run FastAPI and the worker as separate processes or containers.
- Use managed PostgreSQL and Redis when practical.
- Store secrets in a secret manager or protected deployment configuration.
- Use Docker for reproducible builds.
- Run migrations through a controlled deployment step.
- Configure HTTPS, backups, and monitoring before inviting external pilot users.

### Operational metrics

Track at least:

- Scan success, partial, failure, and timeout rates.
- Queue depth and queue wait time.
- Median and p95 scan duration.
- API error rates and latency.
- Scanner CPU, memory, disk, and output usage.
- Webhook delivery failures and duplicate deliveries.
- Findings per scan and duplicate rate.
- Infrastructure cost per scan.
- Pilot activation and repeat usage.

### Recovery requirements

Document how to:

- Retry a failed scan safely.
- Reprocess a webhook without duplicating work.
- Rotate GitHub credentials.
- Restore the database from backup.
- Disable a compromised scanner integration.
- Disconnect a repository installation.
- Delete a user's or organization's data according to policy.

---

## 18. Product validation and success metrics

Do not judge success by feature count, lines of code, or whether an AI model is integrated.

### Technical success

- All MVP acceptance criteria pass.
- Known fixture findings are detected as expected.
- Patched fixtures are handled correctly by the selected scanner.
- Failed or incomplete scans are clearly distinguished from clean scans.
- Duplicate scan deliveries do not create duplicate jobs.
- Tenant-isolation and webhook-security tests pass.
- Scan duration and cost are measured.

### Product success

- Developers can install and use the core workflow.
- Users understand the finding and its evidence.
- The report reduces unnecessary investigation compared with their current workflow.
- Pilot teams return to use the product.
- Users can explain which capability is valuable enough to keep using or pay for.

### Pilot target

Aim to recruit 3–5 teams, but treat this as a target, not a guarantee. Record why each team adopts, rejects, or stops using AdvisoryTrail. A pilot that reveals a weak product assumption is useful if the team responds to the evidence.

---

## 19. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Too many features | Freeze MVP scope; require evidence before adding P1/P2 work |
| Existing tools already solve the problem | Validate a narrow differentiator through interviews and competitor research |
| False positives reduce trust | Preserve evidence, measure precision, support review, avoid overconfident claims |
| Scanner execution is unsafe | Isolated workers, least privilege, no arbitrary repository execution, strict resource limits |
| GitHub integration is unreliable | Idempotent events, retries, clear states, integration tests |
| AI hallucinates remediation | Keep AI optional, ground it in evidence, require human review and tests |
| Team members build incompatible modules | Shared schemas, API contracts, weekly integration and code reviews |
| Cloud costs grow unexpectedly | Per-scan limits, queue controls, metrics, quotas and budget alerts |
| No access to real users | Begin customer interviews in Week 1 and recruit pilot users early |
| Sensitive code or secrets leak | Least privilege, redacted logs, explicit data policies, secure secret handling |

---

## 20. Coding standards and AI coding-assistant instructions

This section is intended for any AI coding assistant or new contributor working from this document.

### 20.1 General rules

- Read this document before proposing implementation changes.
- Inspect the existing repository before creating or replacing files.
- Do not assume a feature exists unless it is present in the code or documented tests.
- Prefer small, testable changes over large rewrites.
- Follow existing naming, formatting, and architecture conventions.
- Do not introduce new infrastructure or dependencies without explaining why they are needed.
- Keep API contracts and database migrations synchronized.
- Never hardcode credentials, tokens, or private keys.
- Never claim tests passed unless they were actually run.
- When a command cannot be executed, state that limitation and provide the exact command for the developer to run.
- Do not silently remove security checks or weaken tests to make a feature pass.
- Document any change that alters scope, security boundaries, data retention, or architecture.

### 20.2 Before implementing a feature

The assistant or contributor should:

1. Identify the relevant requirements in this document.
2. Inspect related files and tests.
3. State the proposed design and affected modules.
4. Identify security and failure cases.
5. Implement the smallest useful change.
6. Add or update tests.
7. Run relevant checks.
8. Summarize changed files, test results, limitations, and follow-up tasks.

### 20.3 Pull-request checklist

- [ ] The change solves a defined user or engineering problem.
- [ ] API and schema changes are documented.
- [ ] Unit or integration tests cover the change.
- [ ] Security implications have been considered.
- [ ] No secrets or private data were added.
- [ ] Error and failure states are handled.
- [ ] Logging avoids sensitive information.
- [ ] Documentation is updated when needed.
- [ ] Relevant checks actually ran.
- [ ] Remaining limitations are stated.

### 20.4 Suggested coding conventions

**Python**
- Use type hints.
- Use a formatter and linter selected by the team.
- Use typed request/response schemas.
- Keep scanner adapters behind clear interfaces.
- Use parameterized database operations.
- Avoid unbounded subprocess execution and arbitrary shell commands.

**TypeScript**
- Enable strict type checking.
- Define types for API responses and UI states.
- Handle loading, empty, partial, error, and success states.
- Avoid using unvalidated API data as trusted input.

**Database**
- Use migrations for schema changes.
- Add constraints and indexes intentionally.
- Test tenant isolation.
- Keep scan history and review decisions auditable.

**Security-sensitive code**
- Require review from another team member.
- Add negative tests as well as happy-path tests.
- Document trust boundaries and failure behavior.

---

## 21. Decisions that must be made before implementation

Do not let unresolved decisions silently become assumptions.

1. **First supported manifests:** Choose the exact Python and JavaScript/TypeScript lockfiles supported by the first scanner integration.
2. **Authentication:** Choose a secure dashboard authentication approach appropriate to the pilot.
3. **GitHub permissions:** Define the minimum permissions required for the exact webhook, content, and Check Run workflow.
4. **Scan scope:** Decide whether the first release scans the head snapshot, compares base and head, or both.
5. **Baseline behavior:** Define what happens when a baseline is unavailable or incomplete.
6. **Policy behavior:** Decide whether the MVP only reports findings or can block merges. Begin in report/warn mode unless pilot evidence supports blocking.
7. **Data retention:** Decide which repository metadata, scanner output, and source-derived evidence are stored, for how long, and how users can delete them.
8. **Hosting and budget:** Choose an environment with sufficient resource isolation for scanner workers.
9. **Licensing:** Review scanner licenses and obligations before redistributing or offering them as part of a commercial service.
10. **AI policy:** Decide whether any code or findings may be sent to an external AI provider. Default to no source-code sharing until reviewed and explicitly authorized.

Record decisions and reasons in `docs/DECISIONS.md`.

---

## 22. Definition of done for the MVP

AdvisoryTrail's MVP is ready for a controlled pilot when:

- [ ] A user can install the GitHub App on a test repository.
- [ ] Pull-request events trigger background scans.
- [ ] Dependency findings are normalized and traceable.
- [ ] Baseline comparison is accurate where supported and returns `unknown` where it is not.
- [ ] Findings are deduplicated across repeated scans.
- [ ] GitHub Check Runs and the dashboard show consistent results.
- [ ] Failed or incomplete scans never appear as clean scans.
- [ ] The scanner worker is isolated and resource-limited.
- [ ] Webhook signatures, tenant isolation, and least privilege are tested.
- [ ] Automated tests run in CI.
- [ ] Monitoring, backups, recovery and data deletion are documented.
- [ ] The setup guide works for a new pilot user.
- [ ] Known limitations are clearly documented.
- [ ] The team has collected feedback from real users and selected the next priorities based on that feedback.

---

## 23. Immediate next actions

The team should now work in this order:

1. Create the GitHub organization and monorepo.
2. Turn Sections 3, 4, 13, and 15 into a prioritized issue backlog.
3. Assign each issue to one owner and define acceptance criteria.
4. Install and test OSV-Scanner on safe sample projects.
5. Build the local scan-to-dashboard vertical slice.
6. Only after that slice works, begin GitHub App integration.
7. Recruit pilot users during the first month rather than waiting for launch.

**First milestone:** by the end of Week 4, a user should be able to scan a test repository, view normalized findings, and inspect a saved report—even if GitHub integration is not finished.

---

## 24. Reference links

Use official documentation as the starting point and verify current capabilities and versions during implementation.

- GitHub Apps: https://docs.github.com/en/apps
- GitHub webhooks: https://docs.github.com/en/webhooks
- GitHub Checks API: https://docs.github.com/en/rest/checks
- FastAPI tutorial: https://fastapi.tiangolo.com/tutorial/
- OSV-Scanner: https://google.github.io/osv-scanner/
- OSV database and API: https://osv.dev/
- Semgrep documentation: https://semgrep.dev/docs/
- Trivy documentation: https://trivy.dev/
- OWASP Cheat Sheet Series: https://cheatsheetseries.owasp.org/
- OWASP Software Supply Chain Security: https://owasp.org/www-project-software-supply-chain-security/
- PostgreSQL documentation: https://www.postgresql.org/docs/
- Docker documentation: https://docs.docker.com/
- React documentation: https://react.dev/
- TypeScript documentation: https://www.typescriptlang.org/docs/

Check current documentation, supported ecosystems, licenses, and version compatibility before choosing production dependencies.

---

## 25. Final product principle

AdvisoryTrail will succeed only if developers trust the results and find them useful.

Prioritize evidence, safe execution, predictable behavior, and a smooth workflow. Deliver a small reliable product, test it with real teams, and expand based on demonstrated needs.

**Do not optimize for the most features. Optimize for the clearest, safest, most useful answer to: “What should I investigate or fix in this pull request, and why?”**
