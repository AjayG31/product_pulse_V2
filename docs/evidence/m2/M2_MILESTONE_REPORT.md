# ProductPulse M2 milestone report

**Milestone:** M2 — Authentication and Initial CSV Ingestion  
**Completion date:** 22 November 2026  
**Authorization:** Product Owner explicitly authorized PP-012, PP-013, and PP-014 in dependency order. PP-014 queue-budget disposition: `max_attempts=3` for its durable `CLASSIFICATION` work items, counting the initial claimed attempt.

## 1. Tickets completed

| Ticket | Result | Acceptance evidence |
|---|---|---|
| PP-012 | Done | [Ticket](../../../tickets/PP-012.md); [local verification transcript](PP-012.txt) |
| PP-013 | Done | [Ticket](../../../tickets/PP-013.md); [local verification transcript](PP-013.txt) |
| PP-014 | Done | [Ticket](../../../tickets/PP-014.md); [local verification transcript](PP-014.txt) |

All three tickets satisfy their mapped acceptance checks and Definition of Done. PP-013 passed before PP-014 began. Detection activation, incident-producing results, automatic notifications, and OpenAI execution remain outside M2 and fail-closed.

## 2. Files created or modified

The principal implementation and evidence files are grouped below.

- **Authentication backend and schema:** `productpulse/auth_api.py`, `productpulse/auth_state.py`, `productpulse/bootstrap_admin.py`, `productpulse/api_common.py`, `productpulse/api_schemas.py`, `productpulse/db_session.py`, `productpulse/database.py`, `productpulse/main.py`, `productpulse/models.py`, `productpulse/settings.py`, `productpulse/security/identity.py`, `productpulse/security/passwords.py`, `productpulse/security/sessions.py`, `productpulse/security/common_passwords.txt`, `migrations/versions/20261122_pp012_auth.py`.
- **CSV preview and confirmation backend:** `productpulse/ingestion/artifacts.py`, `productpulse/ingestion/parser.py`, `productpulse/ingestion_api.py`, `productpulse/ingestion_confirmation.py`, `migrations/versions/20261122_pp013_previews.py`, `migrations/versions/20261122_pp014_confirmation.py`.
- **Frontend:** `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/auth.tsx`, `frontend/src/ingestion.tsx`, `frontend/src/main.tsx`, `frontend/src/test/setup.ts`.
- **Automated tests and local runner:** `tests/test_auth.py`, `tests/test_ingestion_preview.py`, `tests/test_ingestion_confirmation.py`, `tests/test_migrations.py`, `scripts/check.ps1`.
- **Project setup and operator notes:** `pyproject.toml`, `uv.lock`, `README.md`.
- **Decisions, contracts, and plan:** `docs/DECISION_REGISTER.md`, `docs/DATA_MODEL.md`, `docs/API_SPEC.yaml`, `docs/TECH_STACK.md`, `docs/UI_SPEC.md`, `docs/IMPLEMENTATION_PLAN.md`, `tickets/PP-012.md`, `tickets/PP-013.md`, `tickets/PP-014.md`, `docs/evidence/m2/M2_IMPLEMENTATION_BRIEF.md`.
- **Retained evidence:** `docs/evidence/m2/PP-012.txt`, `docs/evidence/m2/PP-013.txt`, `docs/evidence/m2/PP-014.txt`, and this report.

## 3. Tests executed and results

Each ticket ran its local PowerShell command with its transcript retained under `docs/evidence/m2/`. All required checks ultimately passed.

| Ticket | Backend pytest | Frontend Vitest | Build | Security/dependency checks | Source snapshot SHA-256 |
|---|---:|---:|---|---|---|
| PP-012 | 23 passed | 2 passed | Passed | Bandit clean; pip-audit no known vulnerabilities; npm audit 0 vulnerabilities | `2610bde65ac0b55e891c13bda658d604ad641c87290d0f793291de6f5f563409` |
| PP-013 | 32 passed | 3 passed | Passed | Bandit clean; pip-audit no known vulnerabilities; npm audit 0 vulnerabilities | `1c6f8cafe36bec6b72a6fa8fb48318b24a5f73fdc9ffbd417324ed48ad58bc4e` |
| PP-014 | 68 passed | 3 passed | Passed | Bandit clean; pip-audit no known vulnerabilities; npm audit 0 vulnerabilities | `0fb59eb02aa47e86f3682a71f224af324d69aba56671c518bd1178dbfd538a4e` |

Additional verification: Redocly CLI lint of `docs/API_SPEC.yaml` passed with the recommended configuration; the API description is valid with no reported lint warnings. PP-014's transaction tests confirm a 501-row import with 500-row write chunks, supplier lookups grouped at 250 parameters, linkage lookups grouped at 250 tuples (750 bind values), idempotent queue creation, full rollback after a second-chunk failure, and rollback of the queue item when the final preview confirmation update fails.

The first PP-014 script attempt was stopped by sandbox network restrictions at `pip-audit`; the same full script was rerun with network access and passed pip-audit and npm audit. No required check was skipped. The test suite reports one upstream Starlette/httpx deprecation warning; the frontend build reports a minified bundle-size advisory. Neither failed the check.

## 4. Acceptance criteria satisfied

- **PP-012:** protected first-Admin provisioning; login, server-side sessions, logout, signed 10-minute CSRF and same-origin validation; backend roles; Admin account lifecycle and forced-password-change flows; password secrecy, audit, and denial tests. The Product Owner approved process-local login throttles for this single-instance milestone; they reset on API restart, and durable throttling remains a separately gated change.
- **PP-013:** protected artifacts; the five approved templates; strict CSV parsing and mapping; file/row bounds; immutable hash-bound previews and idempotency; Admin-only access; artifact-integrity, cleanup, and authorization checks.
- **PP-014:** explicit processing mode and exact staged-byte hash confirmation; stable ingestion identity and replay behavior; accepted feedback and product placeholders; provenance and known-only supplier/batch linking; one durable `CLASSIFICATION` queue item in the same SQLite transaction with `status=QUEUED`, `attempt_count=0`, and persisted `max_attempts=3`.
- **PP-014 transaction boundary:** one SQLite `BEGIN IMMEDIATE` transaction covers the ingestion job, feedback chunks, products, queue item, and preview state. Chunks bound memory and bind counts; no per-chunk commit occurs, so all-or-nothing consistency and idempotency are preserved.
- **Scope controls:** no worker claim/retry/backoff/lease/recovery logic, OpenAI calls, classification execution, detection activation, incidents, or notifications were implemented.

## 5. Review findings, deviations, and remaining risks

- **Resolved review findings:** PP-012 logout/status and security-token behavior were aligned with the approved contract; PP-013's low-confidence Bandit SQL warning was removed through parameterized SQLAlchemy predicates; PP-014 supplier lookups were bounded to the documented 250-row limit and the post-queue rollback boundary was added to automated coverage. Final Bandit and acceptance checks pass.
- **Approved implementation details:** the Product Owner explicitly approved PP-012's stateless 10-minute signed pre-login CSRF token and process-local login limits for this single-instance milestone, and approved `max_attempts=3` only for PP-014-created classification queue items. These dispositions are recorded in the applicable documentation.
- **Operational risk:** a 50,000-row import keeps SQLite's writer lock for one transaction. It uses bounded in-memory chunks but does not commit between them; splitting commits would violate the all-or-nothing consistency contract.
- **Pending work:** PP-007 still owns other retry budgets, backoff, worker claim/lease/recovery, SQLite busy behavior, reconciliation, and backup/retention details. PP-018 and any worker execution remain gated on their prerequisites. Classification authority/model details, calibration/evaluation, detection, and alert/provider decisions remain pending under their owning tickets.
- **Tooling advisories:** Starlette's TestClient/httpx deprecation and Vite's bundle-size advisory remain for later maintenance. Git was unavailable on PATH, so no Git status/diff was produced; exact implementation source fingerprints are retained with every ticket's passing transcript.
- **External actions:** no commit, push, merge, GitHub Actions, Playwright, deployment, or external publication was performed.

## 6. Recommended next milestone

Resolve PP-007's operational decisions before authorizing worker claim/retry/recovery work such as PP-018. In parallel, perform a fresh readiness review for the next bounded ingestion tickets (for example, rejection reporting/partial acceptance) and authorize only tickets whose specifications and dependencies are closed. Keep classification execution, detection activation, incidents, and notifications gated until their separate decision and evaluation requirements pass.
