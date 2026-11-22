# Milestone M1 — Application Foundation

**Status:** Complete — all three approved tickets are Done.  
**Product Owner authorization:** Explicitly approved in the request dated 22 November 2026.  
**Scope:** PP-010, PP-011, and PP-023 only.

## Approved scope and exclusions

Execution order is PP-010 → PP-011 → PP-023. PP-011 and PP-023 remain paused until PP-010 is Done with passing acceptance evidence. No authentication, ingestion, OpenAI classification, detection activation, incident-producing detection results, or notifications are included. No migration, external send, hosted CI, Playwright, commit, push, merge, or deployment is authorized by this milestone.

## Readiness and dependency review

| Ticket | Readiness at milestone start | Required recheck and gate |
|---|---|---|
| PP-010 | Implementation Ready; PP-001 is Done and ARC-06 local verification is approved. | Fresh review confirmed the approved stack and local checks. PP-007 still owns SQLite busy-timeout and worker lease/retry/recovery values; no defaults will be added. |
| PP-011 | IR after PP-010; not ready to start until PP-010 acceptance evidence passes. | Build only the synthetic development corpus. EV-01 remains Pending Calibration and the final holdout is explicitly excluded. DAI-06 parameters remain Pending Calibration; coverage metadata records synthetic source truth and does not implement sufficiency decisions. The PP-005 taxonomy seed and DAI-05 model ID remain unresolved; neither is activated or used as classifier output. |
| PP-023 | IR after PP-010; not ready to start until PP-010 acceptance evidence passes. | PB-02 and PB-03 are Approved. The pure helper contract is bounded by PRD AC15/AC22 and those decisions. ALERT_SPEC v0.2 is Draft; no draft-only routing, notification, persistence, or audit behavior will be implemented. |

No pending decision is being approved or inferred by this milestone. If implementation requires an unresolved product/security decision, a Draft-only contract, an unapproved SQLite parameter, or a scope change, stop that ticket and its dependents.

## Governing documents

- PRD v1.7; Implementation Plan v0.7; Decision Register v1.7; Definition of Done.
- TECH_STACK v1.0; Architecture v1.4; API_SPEC v1.4.0; DATA_MODEL v1.4; SECURITY v1.0.
- AI_SPEC v1.0 (conditional design baseline); EVALUATION_PLAN v0.4 (Draft; development data only); ALERT_SPEC v0.2 (Draft; approved PB-02/03 decisions and PRD are the implementation authority for PP-023).

## Acceptance checks, tests, and evidence plan

| Ticket | Acceptance mapping and planned automated checks | Evidence to retain |
|---|---|---|
| PP-010 | C1-C2: pytest/FastAPI TestClient for settings/secrets redaction, log redaction, per-connection SQLite foreign keys, WAL/bootstrap, explicit configured busy timeout with no default, migration entry point, `/health`, and worker entry point. C1-C2: Vitest/React Testing Library for the minimal application shell. C3-C4: local PowerShell runner, Bandit, pip-audit, npm audit, frontend build, and documented checklist. | `docs/evidence/m1/PP-010.txt`, source snapshot digest, updated `tickets/PP-010.md`, review notes. |
| PP-011 | C1-C2: pytest against the generator and generated development corpus: 10,000 records, at least 35 UTC event-time days, REVIEW and RETURN sources, reproducibility, stable IDs, manifest/hash, explicit synthetic coverage truth, and no final holdout lock. C3-C4: local PowerShell runner and applicable Python security/dependency checks. | `docs/evidence/m1/PP-011.txt`, `data/dev/manifest.json` and corpus, source snapshot digest, updated `tickets/PP-011.md`, review notes. |
| PP-023 | C1-C2 / PRD AC15 and AC22: table-driven pytest cases for every approved transition, rejected shortcuts/stale states, the inclusive 30 × 24-hour recurrence boundary, and recurrence after the boundary. Confirm helpers have no I/O or detection/notification side effects. C3-C4: local PowerShell runner and applicable Python security/dependency checks. | `docs/evidence/m1/PP-023.txt`, source snapshot digest, updated `tickets/PP-023.md`, review notes. |

The approved project-local commands are `scripts/check.ps1 -Ticket PP-010`, `scripts/check.ps1 -Ticket PP-011`, and `scripts/check.ps1 -Ticket PP-023`. The runner uses pytest/FastAPI TestClient, Vitest/React Testing Library, Bandit, pip-audit, and npm audit as applicable. It will not invoke GitHub Actions, Playwright, ZAP, Locust, or pending evaluation gates.

At each ticket checkpoint, the evidence will record the exact command, result, dependency/tool versions, and SHA-256 identity of the relevant source snapshot. Git is not available in this environment; no commit identity will be fabricated. The report will be completed after the per-ticket review and test results are retained.

## Consolidated milestone review

**Outcome:** PP-010, PP-011, and PP-023 are Done in the approved order. Each ticket passed its required readiness/dependency gate immediately before implementation. No specification was changed, no pending decision was approved, and no milestone scope expansion was needed.

### Ticket outcomes and acceptance evidence

| Ticket | Outcome and acceptance evidence | Automated results |
|---|---|---|
| PP-010 | Done. Foundation, environment-only backend settings, redacted logs, configured SQLite bootstrap, health/API and worker entry points, minimal React shell, local test setup and pre-merge checklist. No auth, ingestion, classification, detection activation, incident-producing path, or notifications. | `scripts/check.ps1 -Ticket PP-010`: pytest **11 passed** (one Starlette deprecation warning); Vitest **1 passed**; TypeScript check and Vite production build passed; Bandit clean; pip-audit no known vulnerabilities; npm audit **0 vulnerabilities**. Lockfile/setup checks passed. See [ticket](../tickets/PP-010.md) and [test evidence](evidence/m1/PP-010.txt). |
| PP-011 | Done. Deterministic development-only corpus: 5,000 REVIEW and 5,000 RETURN records, 35 UTC event dates for each source, six PRD defect-family concepts, normal/non-defect/ambiguous/late/data-quality cases, unresolved-link fixtures, separate scenario-truth sidecar, fixture-only coverage declarations, and no final holdout lock. | `scripts/check.ps1 -Ticket PP-011`: pytest **6 passed**; Bandit clean; pip-audit no known vulnerabilities. The first PyPI lookup was blocked by sandbox networking and is preserved; the full check passed on rerun. See [ticket](../tickets/PP-011.md), [check evidence](evidence/m1/PP-011.txt), [restricted attempt](evidence/m1/PP-011-network-restricted.txt), and [corpus manifest](../data/dev/manifest.json). |
| PP-023 | Done. Pure incident transition validator checks the approved sequence and rejects invalid/stale states with safe result codes. Pure recurrence helper applies the inclusive 30 × 24-hour boundary using timezone-aware UTC instants. No persistence, auth endpoint, detection application, or notification behavior. | `scripts/check.ps1 -Ticket PP-023`: pytest **23 passed**; Bandit clean; pip-audit no known vulnerabilities. See [ticket](../tickets/PP-023.md) and [test evidence](evidence/m1/PP-023.txt). |

Combined Python regression: `.tools/bin/uv.exe run --locked pytest -q -p no:cacheprovider --basetemp <workspace temp>` — **40 passed**, one existing Starlette/HTTPX deprecation warning. Transcript: [M1 regression evidence](evidence/m1/M1-regression.txt). PP-023's final source snapshot fingerprint is SHA-256 `a3caaed860c642a1f1a83a96b1daef057311979cf0c12333c49cacd00228aee6` (59 files). Git is unavailable; no commit ID is claimed.

### Files created or modified

- **Foundation/configuration:** `.env.example`, `.gitignore`, `.python-version`, `README.md`, `pyproject.toml`, `uv.lock`, `tooling/uv.version`, `alembic.ini`, `index.html`, `package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`.
- **Backend and migration entry point:** `productpulse/__init__.py`, `productpulse/settings.py`, `productpulse/database.py`, `productpulse/logging_config.py`, `productpulse/main.py`, `productpulse/worker.py`, `productpulse/incidents.py`, `productpulse/datasets/__init__.py`, `productpulse/datasets/generate.py`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/.gitkeep` (no schema migration was added).
- **Frontend shell:** `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/App.test.tsx`, `frontend/src/test/setup.ts`.
- **Tests and local verification:** `tests/test_settings.py`, `tests/test_logging_config.py`, `tests/test_database.py`, `tests/test_health.py`, `tests/test_migrations.py`, `tests/test_worker_entry.py`, `tests/test_synthetic_data.py`, `tests/test_incident_logic.py`, `scripts/check.ps1`, `scripts/source-fingerprint.ps1`, `docs/PRE_MERGE_CHECKLIST.md`.
- **Synthetic data:** `data/dev/reviews.csv`, `data/dev/returns.csv`, `data/dev/fixture_truth.jsonl`, `data/dev/manifest.json`.
- **Ticket and evidence records:** `tickets/PP-010.md`, `tickets/PP-011.md`, `tickets/PP-023.md`, this report, `docs/evidence/m1/PP-010.txt`, `docs/evidence/m1/PP-010-environment-failure.txt`, `docs/evidence/m1/PP-011.txt`, `docs/evidence/m1/PP-011-network-restricted.txt`, `docs/evidence/m1/PP-023.txt`, and `docs/evidence/m1/M1-regression.txt`.

### Review findings and dispositions

- PP-010's initial frontend type-check issue and pytest temp/cache permission issue were fixed within scope and the ticket's final checks passed. The approved HTTPX-backed TestClient emits one Starlette deprecation warning; it is retained as a warning, not treated as a test failure.
- PP-011 review found a deterministic selector that prevented invalid-timestamp fixtures from being emitted; it was corrected, and tests now assert both malformed-field types. Review also corrected the taxonomy decision reference: PP-005 / AI_SPEC v1.0 governs the unapproved initial taxonomy seed; DAI-05's model identifier is a separate pending decision.
- PP-023 helpers return safe decisions only. Authorization, atomic state compare/update, incident-event persistence, and audit recording remain integration responsibilities for later scoped tickets; the helper does not claim to complete those behaviors.
- No visual/manual check was required. No approval deviation or source-specification change occurred. No GitHub Actions, Playwright, commit, push, merge, external email, or deployment was used.

### Remaining gates, risks, and recommendation

- **Open gates:** PP-005's initial taxonomy seed, DAI-05's model identifier, DAI-06 coverage calibration, EV-01 holdout sizing/representation, PP-007 SQLite/worker operational values, PP-003 authentication/session parameters, PP-004 parser/mapping decisions, and alert routing/provider decisions remain unresolved as recorded in the Decision Register. Detection, incident-producing current results, and automatic notifications remain fail-closed.
- **Risks/limitations:** The corpus is synthetic development data and must not be used as a frozen final holdout or as evidence that detection coverage is sufficient. PP-023 is not an incident API or persistence layer; a future caller must atomically compare the expected state, apply authorization, and write the approved incident history. The Starlette TestClient deprecation warning remains.
- **Recommended next milestone:** Resolve PP-003 and PP-004 first. Then authorize a bounded implementation milestone for PP-012 → PP-013 → PP-014 (Admin authentication/roles, protected CSV upload and preview, then explicit-mode confirmation), rechecking readiness and approvals for each ticket. PP-013 remains gated on both PP-004 and PP-012; do not start it until both are Done/approved as required.

## Ticket checkpoint — PP-010

**Status:** Done  
**Readiness/dependency:** Fresh review passed; PP-001 Done, ARC-06 local verification approved, and M1 explicitly approved.  
**Acceptance:** C1-C4 are satisfied. The implementation adds the selected React/FastAPI foundation, environment-only backend configuration with no operational defaults, redacted application logging, SQLite FK/WAL/bootstrap setup with an explicitly supplied busy timeout, an Alembic schema-version entry point without a migration, API/worker process entry points, the API_SPEC `/health` response, and repeatable local checks/checklist. It adds no authentication, ingestion, classification, detection activation, incident-producing detection path, or notification behavior.

**Checks:** `scripts/check.ps1 -Ticket PP-010` passed. pytest/FastAPI TestClient: 11 passed (one Starlette deprecation warning); Vitest/React Testing Library: 1 passed; TypeScript check and Vite production build passed; Bandit: no issues; pip-audit: no known vulnerabilities; npm audit: 0 vulnerabilities. `uv lock --check`, `npm ci`, and `npm ls --depth=0` passed. Tool versions were CPython 3.12.16, uv 0.13.9, Node 26.13.0, and npm 11.20.0. Final output is [PP-010 test evidence](evidence/m1/PP-010.txt); an initial runner permission failure and its resolution are preserved in [the first-run log](evidence/m1/PP-010-environment-failure.txt).

**Source identity:** SHA-256 `55d6776f0fd8b88a710e80656e519fe5a55eaa2e2b1f33362f5fca10f895a6c4`, as emitted by the local check runner. Git was unavailable, so this is a source snapshot fingerprint and not a commit ID.

**Review / remaining risk:** No in-scope security or authorization boundary was added. The health route returns only coarse process health and a UTC timestamp. No human visual check was required; RTL and production build cover the shell. The approved HTTPX-backed FastAPI TestClient currently emits a Starlette deprecation warning. PP-007 still owns the SQLite busy-timeout and worker lease/retry/recovery values; PP-010 defines no defaults. The worker entry point has no handlers until their approved tickets.

PP-011 and PP-023 remained paused until their fresh readiness checks confirmed PP-010's passing acceptance evidence. Both subsequent checks passed; PP-011 and PP-023 were implemented only after those checkpoints.

## Ticket checkpoint — PP-011

**Status:** Done after PP-010 passed. PP-011's fresh readiness check confirmed PP-010's acceptance evidence and no additional ticket dependency before implementation.

**Acceptance evidence:** `scripts/check.ps1 -Ticket PP-011` passed. The generator produced 10,000 deterministic source records (5,000 reviews, 5,000 returns) spanning 35 UTC event dates per source. Six pytest checks passed; Bandit reported no issues; pip-audit found no known vulnerabilities. The check transcript is [PP-011 local check evidence](evidence/m1/PP-011.txt); a first network-restricted pip-audit attempt and its permitted successful rerun are preserved at [network-restricted attempt evidence](evidence/m1/PP-011-network-restricted.txt). Generated source files and the separate truth sidecar are hashed in [the development manifest](../data/dev/manifest.json).

**Source identity:** SHA-256 `7d0f2d82e398bd717e221e172814f2ce275bfb32b1b27af919c3375964232c39`, 55 files. Git is unavailable; this is a source snapshot fingerprint, not a commit ID.

**Review and boundaries:** The source CSVs have no truth, scenario, taxonomy, or model-output fields. Scenario truth uses PRD §7.4 concepts in a separate JSONL sidecar. The manifest describes complete coverage only for each synthetic fixture feed and does not encode DAI-06 sufficiency. No taxonomy seed, model, final holdout, or evaluation gate is selected. PP-005's initial taxonomy seed, DAI-05's model ID, DAI-06 coverage parameters, and EV-01 holdout parameters remain unresolved. The first review identified a fixture selector that omitted invalid timestamps; it was fixed and verified by tests. The decision reference was corrected to PP-005 / AI_SPEC v1.0 for taxonomy seed, separately from DAI-05 model selection.

PP-023 readiness and dependency review followed this completion checkpoint; both PP-010 and PP-011 evidence passed before PP-023 started.

## Ticket checkpoint — PP-023

**Status:** Done after fresh readiness review. PP-010 and PP-011 were complete; M1 included PP-023; PB-02/PB-03 were Approved. PRD v1.7 and DATA_MODEL v1.4 defined the helper contract. ALERT_SPEC v0.2 remained Draft and was not treated as authority for draft-only behavior.

**Acceptance evidence:** `scripts/check.ps1 -Ticket PP-023` passed: 23 pytest cases, Bandit clean, pip-audit no known vulnerabilities. The helper tests cover all allowed transitions, invalid shortcuts/self-transitions, stale expected status, invalid status, the exact inclusive 30 × 24-hour boundary, just-after-boundary recurrence, different timezone offsets, naive timestamps, and invalid chronology. See [PP-023 test evidence](evidence/m1/PP-023.txt).

**Review and limitations:** Helpers are standard-library-only pure functions. They perform no I/O, persistence, authorization, detection, or notification effects. They return a safe result code for future service handling. The later incident API/service must pair the decision with authorization, an atomic expected-state check/update, and the required durable event/audit record. No unresolved decision blocks this helper-only ticket; PB-04 cooldown and Alert-spec Draft details remain out of scope.

The final cross-ticket Python regression passed with 40 tests and the one documented Starlette deprecation warning. All M1 Definition of Done evidence is retained above and at each ticket link.
