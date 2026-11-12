# AdvisoryTrail — Web Dashboard UI Design & Component Specification

> **Document Purpose:** Comprehensive frontend UI architecture, Material 3 Expressive design system specification, and marker-by-marker functional reference for the AdvisoryTrail React + TypeScript web dashboard (`apps/web/`).
>
> **Target Audience:** Member 2 (Frontend Developer), Member 1 (Umang — Backend & Database Lead), and all teammates integrating scanner, risk-engine, and GitHub Check Run workflows.
>
> **Repository Location:** Save as `docs/UI_DESIGN.md` in the AdvisoryTrail monorepo.


## 1. Design System & Visual Language (Material 3 Expressive)

AdvisoryTrail's web dashboard (`apps/web/`) uses a unified **Material 3 Expressive (Material You)** design language across all six views. Every screen shares the exact same application shell, tonal surface hierarchy, typography scale, and semantic status colors so developers can triage pull-request dependency risks without visual noise.

### 1.1 Core Product UX Guardrails

1. **Never Confuse a Failed Scan with a Clean Scan:** A scan that times out, crashes, or encounters a malformed manifest (`failed`, `timed_out`, `partial`) is visually isolated in high-contrast amber or coral tonal containers and never counted toward `Clean PRs` or shown with a green `0 Findings` badge.
2. **Separate Risk Dimensions:** Rather than collapsing risk into an opaque score (such as `93/100`), the UI displays **Severity**, **Confidence**, **Change Relationship**, **Remediation Availability**, and **Policy Decision** as distinct, inspectable pills backed by a plain-language priority reason.
3. **Traceable Evidence Before Intelligence:** Every finding card links directly to the scanner engine (`osv-scanner`), external advisory (`GHSA` / `CVE`), manifest file path, and deterministic `sha256` fingerprint.

### 1.2 Tonal Color Palette & Surface Tokens

| Token Name | Hex Value | Usage in AdvisoryTrail UI |
| :--- | :--- | :--- |
| `surface-background` | `#F8F7FC` | Main application canvas background and outer window shell |
| `surface-container-low` | `#F1EEF9` | Left navigation rail and secondary card containers |
| `surface-container-high` | `#E6E0F4` | Table headers, card section headers, and filter bar containers |
| `primary-container` | `#D8C8FF` | Active left-sidebar navigation pill (`28px` border radius) and primary action buttons |
| `on-primary-container` | `#21005D` | High-contrast label and icon color inside active lavender pills |
| `status-success-tonal` | `#C8E6C9` / `#1B5E20` | `Succeeded` scan badges, `Installed` app pills, and fixed version diffs |
| `status-warning-tonal` | `#E6A845` / `#3E2723` | `Failed / Incomplete Scans` hero alert card, isolation banners, and `Partial` scan badges |
| `status-critical-tonal` | `#FFDAD6` / `#93000A` | `Critical` / `High` severity badges, `Failed - Timeout` pills, and `BLOCK` policy outcomes |
| `status-running-tonal` | `#D3E3FD` / `#041E49` | `Running` scan badges and active queue progress bars |

### 1.3 Typography & Shape Tokens

| Element | Font Family | Size / Weight | Usage |
| :--- | :--- | :--- | :--- |
| **Page Title** | Google Sans / Inter | `28px` (`1.75rem`), Medium (`500`) | Top bar view title (`Dashboard`, `Repositories`, `Scans`, `Findings`, `Policies`, `Audit Logs`) |
| **Card Header** | Google Sans / Inter | `18px` (`1.125rem`), Medium (`500`) | Section container titles (`Live Pull Request Scan Queue`, `Scan Executions`) |
| **Hero Metric** | Google Sans Display | `36px` (`2.25rem`), SemiBold (`600`) | Top-level KPI counters in Tab 1 (`4`, `7`, `142`, `2`) |
| **Body & Table Cell** | Inter / Roboto Flex | `14px` (`0.875rem`), Regular (`400`) | Descriptions, priority reasons, actor emails, justification notes |
| **Code & Provenance** | JetBrains Mono | `13px` (`0.8125rem`), Medium (`500`) | Commit SHAs (`a1b2c3d`), package versions (`1.26.4 -> 1.26.19`), manifest paths, `sha256` fingerprints |

### 1.4 Global Application Shell (Persistent Across All 6 Tabs)

- **Left Navigation Rail (`240px` fixed width):** Displays the AdvisoryTrail shield logo at the top, followed by exactly six top-level navigation items:
  1. `Dashboard` (Overview & Live Queue)
  2. `Repositories` (Connected GitHub Repos & Manual Scan Trigger)
  3. `Scans` (Scan Lifecycle & Execution History)
  4. `Findings` (Normalized Vulnerabilities & Evidence Inspector)
  5. `Policies` (Deterministic Risk Rules & Check Run Preview)
  6. `Audit Logs` (Webhook Idempotency & Review History)
- **Active Tab Indicator:** Clicking a navigation item highlights it with a full-width Material 3 lavender pill (`#D8C8FF`) and updates the main viewport without reloading the shell.
- **User & Workspace Footer:** Pinned to the bottom-left of the navigation rail with the authenticated user avatar and organization settings trigger.


## 2. Tab 1: Dashboard Overview (`/dashboard`)



The **Dashboard Overview** is the landing page for developers and security leads. It provides an immediate pulse on pull-request scanning activity, newly introduced dependency vulnerabilities, and any scanner failures requiring investigation.

### Marker (1) — Summary Metric Cards (Hero KPI Row)

- **What It Is:** A 4-column grid of Material 3 tonal cards summarizing organization-wide scan and risk states over the current reporting window:
  - **Card 1 (`Active PR Scans: 4 Running`):** Displays the count of scans currently in `queued` or `running` state with an animated circular progress spinner.
  - **Card 2 (`New PR Vulnerabilities: 7 High/Critical`):** Soft coral tonal card showing the number of open `critical` and `high` dependency vulnerabilities classified as `new` in open pull requests.
  - **Card 3 (`Clean PRs: 142`):** Neutral lavender-white card with a green `Success` pill counting completed PR scans that finished with status `succeeded` and zero blocking findings.
  - **Card 4 (`Failed / Incomplete Scans: 2 - Needs Attention`):** High-contrast amber card specifically isolating scans that ended in `failed`, `timed_out`, or `partial` state.
- **How It Works:**
  - On mount, the frontend fetches aggregated metrics from `GET /api/v1/scans?summary=true` (or computes aggregates from the active repository/scan state).
  - Clicking **Card 2** navigates directly to **Tab 4 (Findings)** pre-filtered by `change_relationship=new&severity=critical,high`.
  - Clicking **Card 4** navigates directly to **Tab 3 (Scans)** pre-filtered by `status=failed,timed_out,partial` so engineers can inspect worker timeouts or malformed lockfiles immediately.

### Marker (2) — Live Pull Request Scan Queue

- **What It Is:** A real-time activity card listing active and recently completed pull-request scan jobs (`PR #142: Bump cryptography` on `acme/payment-service`, `PR #89: Update PyJWT` on `acme/auth-service`, `PR #204: Upgrade urllib3` on `acme/web-client`).
- **How It Works:**
  - Each row displays a Git pull-request icon, PR number and title, repository slug (`owner/name`), monospace commit SHA pill (`sha-a9b1c`), lifecycle status pill (`Running` in blue, `Completed` in green), and a horizontal progress bar.
  - While any job in the list has status `queued` or `running`, the React component polls `GET /api/v1/scans?limit=6` every `3000ms` (or listens via Server-Sent Events) to update the status pill and progress bar automatically.
  - Clicking any row navigates to that scan's detailed report in **Tab 3 (Scans)** or **Tab 4 (Findings)**.

### Marker (3) — Recent Repository Health & Findings Breakdown

- **What It Is:** A multi-widget analytical card on the right half of the canvas divided into three sub-sections:
  1. **Health Trends Line Chart:** Plots clean scans vs. vulnerable scans across recent months (`Jan`–`May`).
  2. **Severity Breakdown Donuts & Bars:** Visualizes the proportion of `High` (red), `Medium` (amber), and `Low` (green) findings across active repositories.
  3. **Recently Scanned Repositories List:** Shows connected repositories (`acme/payment-service`, `acme/auth-service`, `acme/web-client`, `acme/data-ingestor`) alongside their latest scan health indicator pill.
- **How It Works:**
  - Aggregates finding counts grouped by `severity` from the `findings` table (`SELECT severity, COUNT(*) FROM findings GROUP BY severity`) and latest scan statuses per repository from `GET /api/v1/repositories`.


## 3. Tab 2: Repositories (`/repositories`)



The **Repositories** tab manages connected GitHub repositories, displays detected dependency manifest files supported by OSV-Scanner, and allows developers to trigger on-demand local or branch scans during Phase 1 and Phase 2.

### Marker (1) — Search Bar, Ecosystem Filter & Connect Action

- **What It Is:** A top control bar containing:
  - **Search Input (`Search repositories...`):** Filters the repository grid client-side or via query parameter `?q=` by repository owner or name.
  - **Ecosystem Segmented Filter (`Ecosystems | All Ecosystems`):** Filters repositories by detected package ecosystem (`PyPI / Python`, `npm / Node.js`, `Cargo / Rust`).
  - **Primary Action Button (`+ Connect GitHub Repository`):** Expressive lavender pill button on the far right.
- **How It Works:**
  - In **Phase 1 (Local Prototype)**, clicking `+ Connect GitHub Repository` opens a modal that submits `POST /api/v1/repositories` with `{ "owner": "acme", "name": "payment-service", "default_branch": "main", "local_path": "..." }` to register a local or test repository record in PostgreSQL.
  - In **Phase 2 (GitHub App Integration)**, the button redirects to the GitHub App installation flow (`https://github.com/apps/advisorytrail/installations/new`) and syncs connected repositories via installation webhooks.

### Markers (2), (3) & (4) — Connected Repository Tonal Cards

- **What They Are:** A 2x2 responsive grid of Material 3 tonal cards representing individual repositories (`acme/payment-service`, `acme/web-dashboard`, `acme/auth-worker`, `acme/data-ingestor`).
  - **Marker (2) — Healthy Repositories (`Succeeded`):** Cards for `acme/payment-service` and `acme/web-dashboard` showing the GitHub octocat icon, green `Installed` badge, default branch pill (`main`), detected manifest chips (`requirements.txt`, `poetry.lock`, `package-lock.json`, `yarn.lock`), a green `Succeeded` latest scan pill, and a `+ Trigger Local Scan` button.
  - **Marker (3) — Failed Scan State (`Failed - Timeout`):** Card for `acme/auth-worker` (`requirements.txt`, `pipfile`) highlighting a coral `Failed - Timeout` badge under `Latest scan` so the team immediately sees that its last scan did not complete cleanly.
  - **Marker (4) — Partial Scan State (`Partial`):** Card for `acme/data-ingestor` (`poetry.lock`, `pyproject.toml`) displaying an amber `Partial` badge when one manifest was parsed but another encountered an error.
- **How It Works:**
  - Populated by calling `GET /api/v1/repositories`, which joins the `repositories` table with the most recent record in `scans` (`ORDER BY created_at DESC LIMIT 1`).
  - Clicking **`+ Trigger Local Scan`** sends `POST /api/v1/repositories/{repository_id}/scans` with the target commit SHA or manifest path. The backend creates a `scans` record with status `queued`, invokes the `scanners/osv/` adapter (synchronously in Phase 1 or via Celery worker in `services/worker/`), persists normalized `findings`, and updates the card's status badge.


## 4. Tab 3: Scans — Lifecycle & History (`/scans`)



The **Scans** tab provides a complete operational audit of every scan execution, enforcing Section 7.1 of the AdvisoryTrail specification (`queued`, `running`, `succeeded`, `partial`, `failed`, `cancelled`, `timed_out`).

### Marker (1) — Scan Lifecycle State Filter Pills

- **What It Is:** A horizontal strip of Material 3 filter chips showing live counts per scan state:
  - `All Scans` (active with a dark border and lavender fill)
  - `Queued (1)`
  - `Running (2)`
  - `Succeeded (142)` (with green status dot)
  - `Partial (1)`
  - `Failed / Timed Out (2)` (with red status dot)
- **How It Works:**
  - Clicking any pill updates the URL search parameter (`?status=failed,timed_out`) and queries `GET /api/v1/scans?status=...` with pagination (`limit` and `offset`).
  - Keeping `Partial` and `Failed / Timed Out` as first-class filter pills ensures failed scanner executions are never buried or conflated with successful zero-finding scans.

### Marker (2) — Failure Isolation Warning Banner

- **What It Is:** A full-width amber tonal banner (`#E6A845`) with an exclamation icon reading: *"Failed or incomplete scans are isolated from clean scans so errors are never mistaken for clean results."*
- **How It Works:**
  - Appears automatically whenever the current scan list contains one or more scans in `failed`, `timed_out`, or `partial` status.
  - Educates developers and pilot users on AdvisoryTrail's core reliability guarantee (MVP Acceptance Criterion #9: *"The product distinguishes a clean scan from a failed or incomplete scan"*).

### Marker (3) — Scan Executions Table

- **What It Is:** A structured Material 3 data table listing individual scan runs (`#1042` down to `#1038`) across seven columns:
  1. **Scan ID:** Short identifier (`#1042`) mapped to the UUID primary key in the `scans` table.
  2. **Repository & PR:** Pull-request number and title (`PR #142: Bump cryptography`, `PR #89: Update PyJWT`) above the repository path (`github.com/org/repo-a`).
  3. **Base vs Head SHA:** Monospace lavender pill showing the exact commit comparison (`a1b2c3d -> f9e8d7c`) used by the baseline engine.
  4. **Scanner Engine:** Pinned scanner name and version pill (`osv-scanner v1.9.0`) stored on the scan record for reproducibility.
  5. **Status:** Color-coded lifecycle pill (`Succeeded` in green, `Running` in blue with spinner, `Failed - Timeout` in coral, `Partial` in amber).
  6. **Findings:** Displays `2 High` (in red text) when vulnerabilities are found, `0 Findings` (in neutral gray) **only** when status is `Succeeded` or `Running`, and a dark pill `Incomplete` when status is `Failed - Timeout` (never showing `0 Findings` on a failed scan!).
  7. **Duration:** Total wall-clock execution time (`1m 12s`, `45s`, `5m 03s` when hitting the 5-minute worker timeout).
- **How It Works:**
  - Backed by `GET /api/v1/repositories/{repository_id}/scans` and `GET /api/v1/scans/{scan_id}`.
  - Clicking a row opens the scan's normalized findings in **Tab 4 (Findings)** filtered by `scan_id`.


## 5. Tab 4: Findings & Evidence Inspector (`/findings`)



The **Findings** tab is the core developer triage workspace. It pairs a filterable master list of deduplicated dependency vulnerabilities with a deep-dive **Evidence Inspector** panel.

### Marker (1) — Change Relationship & Severity Filter Bar

- **What It Is:** A top tonal card split into two filter groups:
  - **Change Relationship (Left):** Pills for `New in PR (2)` (highlighted in lavender), `Existing (4)`, `Resolved (1)`, and `Unknown (0)`.
  - **Severity (Right):** Outlined pills for `Critical`, `High`, `Medium`, and `Low`.
- **How It Works:**
  - Implements Section 9.3 of the AdvisoryTrail specification (Baseline Comparison):
    - `New in PR`: Finding fingerprint appears in the PR `head_sha` scan (`f9e8d7c`) but was absent from the successful `base_sha` scan (`a1b2c3d`).
    - `Existing`: Finding fingerprint was already present in `base_sha` and remains in `head_sha`.
    - `Resolved`: Finding fingerprint was in `base_sha` and is absent from a **successful** `head_sha` scan.
    - `Unknown`: Baseline scan is missing, incomplete, or failed—AdvisoryTrail never guesses that a finding is new or resolved without evidence.
  - Passes `?change_relationship=new&severity=high` to `GET /api/v1/scans/{scan_id}/findings`.

### Marker (2) — Normalized Dependency Findings List (Master List)

- **What It Is:** A selectable list of normalized findings on the bottom-left (`urllib3 (1.26.4 -> Fixed: 1.26.19)` and `pyjwt (2.3.0 -> Fixed: 2.4.0)`).
- **How It Works:**
  - Each row shows the package name, installed version, fixed version from OSV metadata, a `NEW` change-relationship pill, and a `HIGH` severity badge.
  - Selecting a row highlights it with a lavender outline border and loads its full provenance record (`GET /api/v1/findings/{finding_id}`) into Marker (3) on the right.
  - Duplicate findings across repeated scans are suppressed using the `fingerprint` column (`sha256` hash of `scanner + rule_id + ecosystem + package_name + manifest_path`).

### Marker (3) — Finding Detail & Evidence Inspector (Detail Panel)

- **What It Is:** A comprehensive inspection card on the bottom-right divided into four structured sections:
  1. **Deterministic Priority Reason:** Plain-language explanation generated by the risk engine: *"High-severity advisory introduced in head commit; fixed version 1.26.19 available."*
  2. **Traceable Source Evidence:** Displays the exact provenance fields stored in PostgreSQL:
     - **Scanner:** `osv-scanner`
     - **Manifest Path:** `services/api/requirements.txt`
     - **Advisory Link:** Clickable external link `GHSA-34jh-p97f-mpxf` (pointing to `https://osv.dev/vulnerability/GHSA-34jh-p97f-mpxf`)
     - **Fingerprint:** `sha256:8f9d2a...` (stable across line-number shifts)
  3. **Remediation Diff:** Inline code block showing the exact version bump required in `requirements.txt` (`+ urllib3==1.26.4 -> urllib3==1.26.19`).
  4. **Human Review Status (`Open` | `Dismissed - Risk Accepted` | `False Positive`):** Interactive pill selector at the bottom of the inspector.
- **How It Works:**
  - When a developer clicks `Dismissed - Risk Accepted` or `False Positive`, the UI sends `POST /api/v1/findings/{finding_id}/review` with `{ "status": "dismissed", "reason": "..." }`.
  - In accordance with Section 6.2 of the Project Reference (*"Keep user dismissal and acceptance decisions separate from scanner output"*), this writes a new record to the `finding_states` and `audit_logs` tables rather than mutating or deleting the original scanner finding.


## 6. Tab 5: Policies & Risk Engine (`/policies`)



The **Policies** tab configures the deterministic rules engine (Section 10 of the Project Reference) that translates normalized findings and scan states into GitHub Check Run outcomes (`informational`, `warn`, or `block`).

### Marker (1) — Deterministic Policy Mode Selector

- **What It Is:** A top tonal card with a 3-way segmented control:
  - `Report Only`: Publishes neutral/informational GitHub Check Runs without failing pull requests (recommended default for new pilot teams).
  - `Warn on PR`: Posts warning annotations on pull requests when policy rules trigger.
  - `Enforce Blocking Check Runs` (selected): Returns a failing (`action_required` / `failure`) GitHub Check Run conclusion when blocking rules match, preventing merge under branch protection.
- **How It Works:**
  - Updates the organization or repository policy configuration in PostgreSQL and governs how `services/api/` and the `github_integration` module report status back to the GitHub Checks API.

### Marker (2) — Transparent Risk & Policy Rules Matrix

- **What It Is:** A card displaying explicit, human-readable boolean rules with Material 3 toggle switches (`Three active policies`):
  - **Rule 1:** `New Critical/High Vulnerability with Fixed Version -> BLOCK PR Check Run` (Toggle ON)
  - **Rule 2:** `Pre-existing Vulnerability in Baseline -> WARN ONLY` (Toggle ON)
  - **Rule 3:** `Failed or Timed-Out Scan -> INCOMPLETE CHECK (Never mark clean)` (Toggle ON & locked by safety policy)
- **How It Works:**
  - Evaluates four independent inputs for each finding (`severity`, `confidence`, `change_relationship`, `fixed_version != null`) plus the overall `scan.status`.
  - Avoids black-box ML scoring so any developer can understand why a pull request was blocked or warned.

### Marker (3) — GitHub Check Run Output Preview

- **What It Is:** A live preview card at the bottom of the screen rendering a simulated GitHub Pull Request check widget (`AdvisoryTrail PR Security Check — Failed: Policies enforced. New Critical Vulnerability found. Checked 14 files | 1 critical block`).
- **How It Works:**
  - Dynamically updates as the user toggles policy modes in Marker (1) or rules in Marker (2), showing the exact title, summary, and conclusion that AdvisoryTrail's `github_integration` module will send to `POST /repos/{owner}/{repo}/check-runs`.


## 7. Tab 6: Audit Logs & Webhook Deliveries (`/audit-logs`)



The **Audit Logs** tab satisfies the security, idempotency, and compliance requirements in Sections 6.1, 7.2, and 12.2 of the AdvisoryTrail specification.

### Marker (1) — Event Category Filter Bar & Export

- **What It Is:** A top filter bar with category chips (`All Events`, `Finding Reviews & Dismissals`, `GitHub Webhooks`, `Policy Changes`, `Tenant Access`) and a lavender `Export JSON/CSV` action pill on the right.
- **How It Works:**
  - Queries `GET /api/v1/audit-logs?category=...` scoped strictly to the authenticated user's `organization_id` (enforcing server-side tenant isolation).
  - Clicking `Export JSON/CSV` downloads the filtered audit trail for security reviews.

### Marker (2) — Webhook Idempotency & Security Monitor

- **What It Is:** A horizontal health strip displaying two real-time security metrics from the `webhook_deliveries` table:
  - `Verified Signatures: 100%` (with green checkmark pill, confirming HMAC-SHA256 verification of `X-Hub-Signature-256` against the raw request body).
  - `Deduplicated Delivery IDs: 2,408` (counting total GitHub `X-GitHub-Delivery` UUIDs safely recorded with a database uniqueness constraint so retried webhooks never spawn duplicate scan jobs).
- **How It Works:**
  - Directly surfaces MVP Acceptance Criterion #5 (*"Repeated webhook deliveries do not create duplicate scan jobs"*).

### Marker (3) — Chronological Audit Trail Table

- **What It Is:** An immutable, timestamped log table with five columns:
  1. **Timestamp:** UTC/local ISO timestamp (`2026-10-31 10:15:32`).
  2. **Actor:** User email (`umang@advisorytrail.dev`) or system principal (`github-webhook-bot`).
  3. **Action:** Color-coded action pill (`FINDING_DISMISSED` in coral, `WEBHOOK_DELIVERY_DEDUPLICATED` in indigo, `SCAN_QUEUED` in neutral lavender).
  4. **Resource ID:** Target entity identifier (`vuln-998122`, `wh-delivery-88a`, `repo-sha-a9b1c`).
  5. **Justification:** Human-entered review reason (`False positive identification`) or system note (`Automatic deduplication`, `Automatic trigger on PR open`).
- **How It Works:**
  - Populated from the `audit_logs` table (`id`, `organization_id`, `actor_id`, `action`, `resource_id`, `justification`, `created_at`).


## 8. API & Database Mapping Summary Across All 6 Tabs

| Tab & Screen | Marker | FastAPI Endpoint (`services/api/`) | PostgreSQL Tables Used |
| :--- | :--- | :--- | :--- |
| **Tab 1: Dashboard** | `(1)` Summary Cards | `GET /api/v1/scans?summary=true` | `scans`, `findings` |
| **Tab 1: Dashboard** | `(2)` Live PR Scan Queue | `GET /api/v1/scans?limit=6` | `scans`, `repositories`, `pull_requests` |
| **Tab 1: Dashboard** | `(3)` Repo Health & Breakdown | `GET /api/v1/repositories` | `repositories`, `scans`, `findings` |
| **Tab 2: Repositories** | `(1)` Search & Connect Repo | `POST /api/v1/repositories` | `repositories`, `installations` |
| **Tab 2: Repositories** | `(2)–(4)` Repo Cards & Trigger | `GET /api/v1/repositories`, `POST /api/v1/repositories/{id}/scans` | `repositories`, `scans`, `findings` |
| **Tab 3: Scans** | `(1)–(3)` Filters, Banner & Table | `GET /api/v1/scans`, `GET /api/v1/scans/{scan_id}` | `scans`, `repositories` |
| **Tab 4: Findings** | `(1)–(2)` Filters & Master List | `GET /api/v1/scans/{scan_id}/findings` | `findings`, `advisories` |
| **Tab 4: Findings** | `(3)` Evidence Inspector & Review | `GET /api/v1/findings/{id}`, `POST /api/v1/findings/{id}/review` | `findings`, `finding_states`, `audit_logs` |
| **Tab 5: Policies** | `(1)–(3)` Mode, Rules & Preview | `GET /api/v1/policies`, `PUT /api/v1/policies` | `organizations`, `repositories` |
| **Tab 6: Audit Logs** | `(1)–(3)` Monitor & Audit Table | `GET /api/v1/audit-logs` | `audit_logs`, `webhook_deliveries` |


## 9. Frontend Directory Structure (`apps/web/`)

To build these six tabs cleanly in React + TypeScript (Vite), organize `apps/web/src/` as follows:

```text
apps/web/src/
├── api/
│   └── client.ts                 # Typed fetch wrapper targeting /api/v1
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx          # Persistent M3 left navigation rail & top bar
│   │   └── StatusBadge.tsx       # Reusable Succeeded / Running / Partial / Failed pills
│   ├── dashboard/
│   │   ├── SummaryHeroCards.tsx  # Tab 1 - Marker (1)
│   │   ├── LiveScanQueue.tsx     # Tab 1 - Marker (2)
│   │   └── RepoHealthCard.tsx    # Tab 1 - Marker (3)
│   ├── repositories/
│   │   ├── RepoFilterBar.tsx     # Tab 2 - Marker (1)
│   │   └── RepositoryCard.tsx    # Tab 2 - Markers (2), (3), (4)
│   ├── scans/
│   │   ├── ScanStatePills.tsx    # Tab 3 - Marker (1)
│   │   ├── FailureBanner.tsx     # Tab 3 - Marker (2)
│   │   └── ScanHistoryTable.tsx  # Tab 3 - Marker (3)
│   ├── findings/
│   │   ├── FindingFilterBar.tsx  # Tab 4 - Marker (1)
│   │   ├── FindingList.tsx       # Tab 4 - Marker (2)
│   │   └── EvidenceInspector.tsx # Tab 4 - Marker (3)
│   ├── policies/
│   │   ├── PolicyModeCard.tsx    # Tab 5 - Marker (1)
│   │   ├── RuleMatrixCard.tsx    # Tab 5 - Marker (2)
│   │   └── CheckRunPreview.tsx   # Tab 5 - Marker (3)
│   └── audit/
│       ├── AuditFilterBar.tsx    # Tab 6 - Marker (1)
│       ├── WebhookMonitor.tsx    # Tab 6 - Marker (2)
│       └── AuditTrailTable.tsx   # Tab 6 - Marker (3)
├── pages/
│   ├── DashboardPage.tsx         # Tab 1 view
│   ├── RepositoriesPage.tsx      # Tab 2 view
│   ├── ScansPage.tsx             # Tab 3 view
│   ├── FindingsPage.tsx          # Tab 4 view
│   ├── PoliciesPage.tsx          # Tab 5 view
│   └── AuditLogsPage.tsx         # Tab 6 view
├── types/
│   └── api.ts                    # Shared TypeScript interfaces matching FastAPI Pydantic models
├── App.tsx
└── main.tsx
```
