# M2 implementation brief — Authentication and initial CSV ingestion

**Authorization:** Product Owner approval in the 22 November 2026 request.
**Scope:** PP-012 → PP-013 → PP-014, one ticket at a time.
**Workspace:** `D:\product_pulse_V2`

This repository record captures the reviewed M2 scope, the Product Owner's milestone authorization, and the per-ticket verification plan.

## Governing baseline and readiness

- PRD v1.7; Security v1.1; API_SPEC v1.5.1; Data Model v1.5.1; UI_SPEC v0.4; Architecture v1.4; TECH_STACK v1.1.1; Decision Register v1.9; Implementation Plan v0.9; Definition of Done.
- PP-003 and PP-004 are Done with approved decisions recorded 22 November 2026. PP-010 is Done with M1 evidence.
- PP-012 is Implementation Ready after PP-003 and PP-010. Recheck before start.
- PP-013 was rechecked Implementation Ready after PP-004, PP-010, and PP-012, then marked Done after passing PP-013 evidence on 22 November 2026.
- PP-014 dependency evidence passed after PP-013. The Product Owner resolved its queue-budget gate on 22 November 2026 by approving `max_attempts=3` total claimed attempts (initial attempt plus up to two additional attempts) for PP-014 `CLASSIFICATION` work items. This value is snapshotted only; queue execution, retries, backoff, leases, recovery, and provider calls remain excluded and other OPS-02 values remain pending for PP-007.
- PP-014 completed on 22 November 2026 after its full local acceptance script, security/dependency checks, transaction/chunk/idempotency coverage, and API contract lint passed; see `docs/evidence/m2/PP-014.txt` and the consolidated `docs/evidence/m2/M2_MILESTONE_REPORT.md`.
- SEC-01/02, DAI-01/02/08, and OPS-06 are approved at the recorded scope. The PP-014 `CLASSIFICATION` queue snapshot is approved at `max_attempts=3`; worker claiming, retry execution/backoff, leases/recovery, other retry values, detection/calibration, notification, deployment, and artifact-retention decisions remain gated.

## Bounded scope

- **PP-012:** protected one-time first-Admin command; login, server-side sessions, logout, CSRF and same-origin checks; backend role/state enforcement; Admin create/list/deactivate/reset APIs; write-only temporary-password handling and forced-change API/UI; auth and security tests.
- **PP-013:** protected artifact publication and resolution; Admin template/download and upload/mapping/immutable-preview flows for the five approved upload kinds; strict parser/hash/idempotency validation; upload authorization and preview UI/tests.
- **PP-014:** Admin confirmation of valid feedback previews only; explicit processing mode; exact staged-byte hash recheck; stable job identity; idempotent replay; accepted feedback, ingestion job, and one stable durable `CLASSIFICATION` queue item with `max_attempts=3` persisted consistently under SQLite.
- **Exclusions:** OpenAI calls or classification execution, retries/backoff, worker claiming or lease/recovery behavior, detection, incidents, notifications, user-management screen, rejection-report generation/download, reference-import confirmation/reconciliation, unrelated application features, GitHub Actions, Playwright, commit, push, merge, and deployment.
- **PP-014 queue boundary:** DAI-07/API require durable automatic classification dispatch. PP-014 creates one `CLASSIFICATION` work item atomically with feedback persistence and snapshots the PO-approved `max_attempts=3`; it does not execute or claim that work. The OPS-02 approval is scoped to these queue items; all other retry/recovery parameters remain pending for PP-007.
- **Approved PP-012 implementation detail and limitation:** The pre-login CSRF value is a stateless HMAC-signed token valid for 10 minutes. Login limits use in-process state for the approved single-instance milestone; that state resets when the API process restarts. Durable limits require separate Security/Data Model approval. The signing key is process-local as well, so a restart invalidates outstanding pre-login tokens.

## Acceptance checks and retained evidence

Each command is run before marking its ticket Done. The script transcript is retained in the linked evidence file and includes the source snapshot SHA-256.

| Ticket | Readiness and criteria-to-check mapping | Local acceptance command and evidence |
|---|---|---|
| PP-012 | Recheck PP-003/PP-010 and approved SEC-01/02. AC1–2: setup/login/session/cookie/CSRF/RBAC FastAPI tests. AC3–5: account lifecycle, reset/change/revocation, password secrecy/audit tests. AC4–5: login and forced-change React Testing Library tests. AC6–7: fail-closed scope assertions and evidence record. | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Ticket PP-012 -EvidencePath docs/evidence/m2/PP-012.txt` |
| PP-013 | Recheck PP-004/PP-010 and passing PP-012 evidence. AC1–2: parser, five templates, upload limit/encoding/mapping/hash/idempotency, authorization and artifact integrity API tests. AC3–4: dependency/gate and security tests; upload/mapping/preview React Testing Library tests. | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Ticket PP-013 -EvidencePath docs/evidence/m2/PP-013.txt` |
| PP-014 | Done. PP-013 evidence passed before start. AC1–2: valid feedback confirmation, mode validation, hash mismatch, stable job replay, duplicate/no-overwrite, 250-row lookup bounds, 500-row chunks, and rollback before/after queue creation passed in SQLite tests. AC3–4: fail-closed exclusions and dependency evidence recorded. | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Ticket PP-014 -EvidencePath docs/evidence/m2/PP-014.txt`; Redocly lint passed. |

Every ticket also runs applicable frontend tests/build, Bandit, pip-audit, npm audit, and the source fingerprint through `scripts/check.ps1`. Keep raw passwords, session/CSRF values, raw feedback, credentials, and local storage paths out of application logs and API responses. The final report records review findings, any unavailable checks, unresolved gates, and risks.
