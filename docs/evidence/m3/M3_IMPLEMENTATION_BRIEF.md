# ProductPulse M3 Implementation Brief

**Prepared:** 24 November 2026  
**Status:** Approved for bounded implementation; work is underway
**Scope requested:** PP-018, PP-034, PP-035, PP-015, PP-036  
**M1/M2:** Complete  
**PP-007:** Done

## 1. Approval boundary

This brief records the bounded scope, readiness, order, acceptance checks, evidence, exclusions, and stop conditions for M3. The Product Owner's dispositions through 24 November are recorded in Decision Register v2.3 and aligned in the affected specifications and tickets. The Product Owner explicitly approved the bounded five-ticket M3 milestone on 24 November 2026; execution remains subject to each ticket's readiness and dependency gates.

This brief is not approval to start implementation. The Product Owner approved PP-005's attempt selection within each applicable taxonomy version and, on 24 November, approved how each aggregation context selects and retains its applicable version. The policy requires an explicit `taxonomy_version_id` per context, selects only the latest validated COMPLETED classification for that exact version by `completed_at DESC` then binary `classification_id DESC`, has no cross-version fallback, reports records without a valid classification for that version as unclassified, and keeps historical aggregates version-scoped. Taxonomy changes do not reclassify history; historical M3 recomputation cannot create/update incidents, notify, or activate detection. The source and version selection must be snapshotted into durable work and persisted with results. PP-015 is now `IR after PP-018`; PP-036 remains `IR after PP-015`. The initial taxonomy seed and `other_product_defect` issue-code policy remain pending and outside M3's classifier/activation scope. No other PP-005 decision is inferred.

## 2. Approved M3 decision baseline

- **INGESTION:** max_attempts=3 total claims per work run, including the initial claim. Admin recovery creates a new audited run under the same ingestion job and is permitted only for safely replayable work.
- **RECONCILIATION and M3 historical DETECTION:** max_attempts=3 total claims per job type. Retry only known-safe transient failures.
- **Linkage-triggered historical recomputation:** use exact approved identifiers; preserve LINKAGE_PENDING when links remain unresolved; rebuild affected aggregates from source facts; leave coverage UNKNOWN where it is not established; do not create/update incidents, send notifications, or activate detection.
- **Dependencies:** PP-018 is an explicit PP-015 dependency.
- **PP-036:** retain the existing DAI-01/02 conflict-resolution rules without expanding scope.
- **Classification attempt authority:** latest validated definitive completion within each applicable taxonomy version, ordered by persisted completion time and unique classification ID; exclude failed, pending, invalid, and needs-review attempts; retain immutable history, count once per applicable aggregation context, and prohibit historical recomputation side effects.

The existing PP-007 worker parameters remain unchanged: 5-second poll, 5-minute lease, 60-second renewals, startup/every-60-second reconciliation, 5-second SQLite busy timeout, at most 2 additional rolled-back SQLITE_BUSY retries for an idempotent unit, and 5/15/45-second eligible retry delays. PP-014's CLASSIFICATION work remains at max_attempts=3 total, separate from the newly approved INGESTION budget.

## 3. Readiness and dependencies

| Ticket | Current readiness | Dependencies / gate |
|---|---|---|
| PP-018 | Done — 24 November 2026; see `docs/evidence/m3/PP-018.txt` | PP-010, PP-014, and PP-007 were Done at start. Worker retry rules passed; PP-035 owns the Admin recovery endpoint and audited new-run behavior per Product Owner clarification. |
| PP-034 | Done — 24 November 2026; see `docs/evidence/m3/PP-034.txt` | PP-013, PP-014, and PP-004 were Done; SEC-P04 matched the approved Security/API parser contracts at start. |
| PP-035 | Done — 24 November 2026; see `docs/evidence/m3/PP-035.txt` | PP-012, PP-014, PP-007, and PP-018 were Done at start; API, Data Model, UI, Security, and PRD contracts reviewed. Safe replay eligibility uses the worker-persisted explicit replay-safe marker and fails closed otherwise. |
| PP-015 | Done — 24 November 2026; see `docs/evidence/m3/PP-015.txt` | Fresh start-time check passed; PP-011, PP-014, PP-004, and PP-018 were Done. PP-005's within-version attempt rule and explicit per-context version rule are approved. DAI-06 UNKNOWN coverage is preserved; seed, issue-code, model, and classifier/provider execution remain outside scope. |
| PP-036 | Done — 24 November 2026; see `docs/evidence/m3/PP-036.txt` | Fresh start-time check passed after PP-015. PP-012, PP-014, and PP-004 were Done. DAI-01/02 rules are approved and remain unchanged. |

DAI-06 coverage granularity/completeness/calibration remains Pending Calibration, but does not block the approved fail-closed recomputation behavior: do not infer coverage and retain UNKNOWN when evidence does not establish it. The AI model identifier, provider choices, notification policies, thresholds, held-out evaluation gates, and BATCH_POLL retry budget remain pending and outside M3.

## 4. Recommended execution order

Implementation is one ticket at a time. Recheck readiness at each ticket start; the dependency-correct sequence is:

1. **PP-018** — establish durable worker claim, lease, reconciliation, and retry mechanics for approved work types.
2. **PP-034** — implement partial acceptance and safe rejection report; this ticket is independent after its completed dependencies.
3. **PP-035** — implement Admin ingestion status and the safe-recovery API/UI, including the audited new-run behavior, after PP-018 passes.
4. **PP-015** — implement reference imports, linkage reconciliation, and historical aggregate rebuilding after PP-018 passes, applying the explicit version-scoped contract.
5. **PP-036** — implement the separate Admin source/mapping conflict APIs after PP-015 passes.

Dependency graph: PP-018 → PP-035; PP-018 → PP-015 → PP-036; PP-034 is independent. The non-ticket taxonomy-version applicability gate is resolved. PP-018 and PP-034 are Done; PP-035 and PP-015 are `IR after PP-018`, and PP-036 is `IR after PP-015`. The milestone is approved; each ticket still requires its start-time recheck.

## 5. Governing contracts

- PRD v1.7; AGENTS.md; DEFINITION_OF_DONE.md.
- Decision Register v2.3; Implementation Plan v1.3.
- Architecture v1.6; Tech Stack v1.2.1.
- API_SPEC.yaml v1.5.4; Data Model v1.5.5; UI_SPEC.md v0.4.3; Security v1.1; AI_SPEC.md v1.2.
- DETECTION_SPEC.md v1.1 remains Draft and v1.0 remains the Approved Design Baseline. Only its specifically marked DAI-06 linkage-recomputation, PP-005 within-version attempt-selection, and 24 November taxonomy-version applicability clauses are approved; no other v1.1 proposal is approved.
- EVALUATION_PLAN.md v0.6 remains Draft. SEC-P04 has been corrected to follow the approved Security/API parser contracts.
- ALERT_SPEC.md v0.3 remains Draft; its cross-reference is aligned but it does not authorize notification behavior.

## 6. Ticket acceptance checks and test plan

Tests named below are to be added or updated within the named ticket. Commands run from the repository root. The current scripts/check.ps1 accepts only M1/M2 ticket IDs, so M3 evidence will use the approved local pytest/Vitest commands directly and retain their output per ticket.

| Ticket / mapped requirements | Acceptance checks and planned automated tests | Commands and evidence |
|---|---|---|
| **PP-018** — AC02, AC07; F04/F05 | Worker shares the API SQLite file; claims one item atomically; honors PP-007 timeouts, leases, renewals, polling, reconciliation, stale-owner rejection, restart recovery, and provider-call transaction boundaries. Verify CLASSIFICATION remains 3 total; INGESTION is 3 per run; RECONCILIATION and historical DETECTION are 3 per type; a NULL/BATCH_POLL budget is never claimed. Verify only safe INGESTION replay and known-safe-transient RECONCILIATION/DETECTION retries. Exhaustion remains visible and terminal. | Add tests/test_worker_runtime.py and tests/test_retry_budgets.py. Run uv run --locked pytest tests/test_worker_runtime.py tests/test_retry_budgets.py -q, then uv run --locked pytest -q. Retain docs/evidence/m3/PP-018.txt, including restart/recovery observation, commands/results, exact revision identity, review, and relevant security checks. |
| **PP-034** — AC03, AC23; F02/F03; SEC-AC07/15 | Partial acceptance and safe reasons match the approved parser/mapping contract. Rejection CSV includes rejected/conflicting rows only, excludes duplicate no-ops and raw feedback, escapes included user-controlled cells, and leaves source data unchanged. Parser-boundary, formula, authorized-download, integrity, and Business User denial cases pass. | `uv run --locked pytest tests/test_ingestion_preview.py tests/test_ingestion_reports.py tests/test_migrations.py -q` — 15 passed; full backend — 88 passed; `npm test -- --run` — 3 passed; `npm run build`, Bandit, and pip-audit passed. Retained report bytes/hash and review: `docs/evidence/m3/PP-034.txt`. |
| **PP-035** — AC04/16; F03/F15; SEC-AC04 | Admin job status, safe error code, upload kind, report link, and server-derived eligibility. A recovery creates one audited INGESTION run under the same stable job with 3 claims; original mode, preview, idempotency, and source identities remain unchanged, with no duplicate persisted rows. Permanent, unknown, abandoned, inconsistent, and active outcomes fail closed. The UI exposes Retry only when eligible and displays new-run ID/current 409 reason. | `uv run --locked pytest tests/test_ingestion_retries.py -q` — 8 passed; full backend — 96 passed; `npm test -- --run` — 4 passed; `npm run build`, Bandit, pip-audit, and npm audit passed. Evidence and source fingerprint: `docs/evidence/m3/PP-035.txt`. |
| **PP-015** — AC19; F07 | Exact approved identifiers; unresolved records remain LINKAGE_PENDING; recomputation uses persisted source facts; each classification-backed context requires its explicit taxonomy version and durable DETECTION job/result contract; latest qualifying completion is selected only within that version using completed_at DESC then binary classification_id DESC; no fallback; unclassified records remain excluded from definitive defect counts; historical results remain version-scoped and cannot affect incidents, notifications, or activation; coverage stays UNKNOWN; approved retry cap remains 3 for known-safe transient failures. | Implemented and mapped in `docs/evidence/m3/PP-015.txt`. Focused reconciliation/migration/ingestion checks — 24 passed; retry/worker checks — 5 passed; full backend — 103 passed; Bandit — no issues across 5,784 lines; pip-audit — no known vulnerabilities. Source fingerprint: `35c386d44052e63edb71e75367a6dc3160a1c6fcf4da0ffaec0f5ef6fcce0d60`. |
| **PP-036** — AC03/19/23; F03/F07 | Admin-only conflict list/detail/resolve APIs preserve DAI-01/02 exactly. SOURCE_PAYLOAD allows KEEP_EXISTING/DISMISS only and never applies incoming text. REFERENCE_MAPPING allows KEEP_EXISTING/DISMISS/APPLY_INCOMING_REFERENCE only when expected existing-value hash matches; stale application returns 409. Audit actor/reason and immutable preview/provenance are retained. Keep this domain separate from linkage reconciliation. | Implemented and mapped in `docs/evidence/m3/PP-036.txt`. Focused conflict API tests — 5 passed; full backend — 108 passed; Bandit — no issues across 6,170 lines; pip-audit — no known vulnerabilities. Source fingerprint: `32948066ad89880724a9d722ae501e5a04dde20a91ed22a7feadb82eff217a97`. No UI work is included in this API ticket. |

For every ticket, map each ticket criterion C1–C4 to its passing automated checks; retain command lines, result summaries, exact revision identity (Git revision if available, otherwise a documented source fingerprint), security/review findings, and evidence links. Run Bandit and dependency checks when the affected backend/frontend surface changes. A failed, skipped, unavailable, or unreviewed required check blocks that ticket. UI tests are required only where that ticket changes UI behavior; PP-036 remains API-only.

## 7. Specification-change check

The approved M3 decisions require aligned worker, data, API, detection, and UI contracts. Data Model v1.5.5 and API_SPEC.yaml v1.5.4 express the per-run/per-job-type budgets, nullable budget for unbudgeted work, audited ingestion recovery run under the stable job, historical linkage-recomputation boundary, and the explicit taxonomy-version context. AI_SPEC.md v1.2, DATA_MODEL.md v1.5.5, API_SPEC.yaml v1.5.4, and UI_SPEC.md v0.4.3 record version-scoped selection and unclassified reporting. The draft ALERT_SPEC v0.3 and EVALUATION_PLAN v0.6 were also updated to remove obsolete statements that cross-version applicability is unresolved; both documents remain Draft and no alert, model, evaluation, or activation gate was approved by those edits. These updates record the exact Product Owner dispositions; they do not expand them.

PP-015's new PP-018 dependency is recorded in the Implementation Plan and PP-015 ticket. Its required schema/API delta is: store the explicitly chosen `taxonomy_version_id` in immutable detection-rule configuration; require it on DETECTION jobs with a database check, snapshot it before claim, and prevent changes on retry/replay; persist it in each detection result and evidence identity; and include it in result fingerprints/uniqueness so versions cannot merge. Composite foreign keys enforce rule/result/job version agreement, with service validation for the latest qualifying attempt. Detection rule configuration is the explicit source for durable detection contexts; retries and recomputation reuse the stored ID. Read-time dashboard/product contexts are created by a required exact-version request parameter, echoed in `applied_filters` and response items; those endpoints compute query-time views and do not create durable aggregate rows. If any context is materialized in storage, its schema must retain that same ID. Missing or invalid IDs fail the request/job closed with no aggregate result; there is no default to an active/latest version. The read APIs expose per-context unclassified counts. Historical contexts retain their recorded ID, and recomputation cannot cause incident, notification, or activation side effects. The existing product read shape that pooled `taxonomy_versions` is replaced by version-scoped results.

**Existing implementation inspected for scope at brief preparation:** M1/M2 ORM models and migrations existed in `productpulse/models.py` and `migrations/versions/`; `productpulse/worker.py` was a worker entry stub, and there were no detection-result models, handlers, or detection API modules. PP-015 therefore affected the data model/migration path, durable job creation/claim, reconciliation/recomputation service, and aggregate API/query code, plus focused tests such as `tests/test_linkage_reconciliation.py`. PP-018 affected the worker and retry path; PP-034/035 affected ingestion reporting/status and associated APIs/UI; PP-036 adds the separate conflict API/service path and focused tests. Existing relevant automated coverage was under `tests/` and `frontend/src/App.test.tsx`. The schema/API delta above remained bounded to the approved PP-015 contract.

PP-036 remains on the existing DAI-01/02 conflict contract with no scope expansion. DETECTION_SPEC.md v1.1 remains Draft; only the expressly approved linkage-recomputation and PP-005 clauses are marked approved. EVALUATION_PLAN.md v0.6 remains Draft; ALERT_SPEC.md v0.3 remains Draft and its updated cross-reference does not approve alert/provider behavior. SEC-P04 was corrected to match the already-approved Security/API parser rules. No PRD, Security, AI model, alert-provider, calibration, or migration decision was changed. Implementation will require additive schema/API work in PP-015; this brief approves no migration execution or backfill strategy beyond the ticket scope.

## 8. Documentation validation

- Redocly CLI lint passed for the current API_SPEC.yaml v1.5.4. The preserved run output and hash record are in [api_lint.txt](api_lint.txt): validation reported the API description valid, the process exit code was 0, and the recorded SHA-256 `DE385D88904D03F252300122DFB11A21A1FC77290413A48EC6D7CACF4F348A46` matches the current `docs/API_SPEC.yaml`. PowerShell displayed an informational stderr message as `NativeCommandError`; the recorded successful validator output and exit code show this was not a lint failure. Redocly CLI 2.82.0 lint had also passed for API_SPEC.yaml v1.5.3 previously.
- A targeted cross-document assertion scan passed 12/12 checks: exact-version required parameters on dashboard summary/trends and product list/detail, explicit taxonomy ID in immutable rule configuration, unclassified result fields, deterministic binary tie-break/no fallback, persisted Data Model fields, PP-015/PP-036 readiness, pending PP-005 seed/issue-code decisions, and current ALERT_SPEC/EVALUATION_PLAN wording.
- No application tests were run for this documentation-only decision/specification task. Acceptance tests listed above are required implementation work and evidence for the individual tickets.
- The stale-readiness scan found no current M3 statements that leave PP-005 applicability unresolved or block PP-015 on that decision. Dated 22 November/earlier contract references remain only as historical revision evidence.
- This documentation task ran no application test suite and created no application code or migration. No commit, push, or deployment was performed.

## 9. Scope and exclusions

**Included:** the five named tickets; PP-018 worker/retry base; PP-034 rejection reporting; PP-035 Admin ingestion status/recovery; PP-015 reference imports/linkage/historical rebuilding; PP-036 source/mapping conflict APIs; tests and documentation/evidence strictly required by those scopes.

**Excluded:** Remaining PP-005 initial taxonomy seed and `other_product_defect` issue-code decisions; DAI-06 coverage calibration; PB-01 detection thresholds; AI model/taxonomy activation or classification execution; BATCH_POLL retry budget; current-monitoring detection activation; incident creation/update from historical work; notification activation, provider/routing/sink, external sends, or real email; deployment/provider selection; applying any migration before the approved pre-migration coherent database/artifact backup is taken and verified under PP-007/OPS-03/OPS-06; unrelated UI/API/spec changes.

No change may alter PP-007 worker parameters, PP-014's CLASSIFICATION max_attempts=3, DAI-01/02 conflict options, or the approved single-instance SQLite architecture.

## 10. Risks and stop conditions

- **Version-context schema work:** the applicability policy is approved, but implementation must persist the explicit version selection across context, durable job, result, evidence, and API reads. Do not infer a version from active/latest configuration, backfill by guessing, fall back to another version, or combine historical results. Missing context version fails closed. The initial seed and issue-code policy remain pending; do not activate candidate codes.
- **Migration execution hold point:** before applying an Alembic migration, quiesce API, worker, and artifact mutations; take the approved SQLite `Connection.backup()` snapshot with referenced artifacts as one recovery set; verify database integrity, foreign keys, artifact presence, and stored hashes. The backup-before-migration procedure is approved; the gate applies at migration execution and does not authorize migration work in this task.
- **Coverage/calibration pending:** unknown coverage must remain UNKNOWN; insufficient coverage cannot be interpreted as zero. Keep detection fail-closed; do not enable incident-producing current results.
- **Safe retry boundaries:** never replay an ingestion run with a permanent or unknown outcome. New Admin recovery gets a fresh audited run; it does not reset the prior run's attempts or duplicate accepted source rows.
- **SQLite single-writer behavior:** keep transactions short, use existing PP-007 lease and busy policies exactly, and stop if contention/recovery cannot meet acceptance without changing approved parameters.
- **Security or authorization defect:** stop affected work immediately, retain safe evidence, and report the issue. Do not bypass or expand scope.
- **Required check failure/unavailability:** fix only within the approved ticket/milestone. Otherwise stop that ticket and its dependents; do not mark it Done.
- **Approved-spec change needed:** stop affected work and request separate explicit Product Owner approval before changing the specification or dependent code.
- **Any newly surfaced decision, dependency, or scope conflict:** pause the affected ticket and its dependents. Continue only independent approved tickets with clear gates.
- **Consequential external action:** no commit, push, merge, deployment, real email, provider provisioning, or unapproved spend.

## 11. Milestone approval and execution status

On 24 November 2026, the Product Owner explicitly approved **Milestone M3 — Complete Ingestion & Background Worker** for PP-018, PP-034, PP-035, PP-015, and PP-036, in that execution order. This approval authorizes only the bounded ticket scope and exclusions above. Each ticket passed its fresh readiness/dependency check immediately before start and has retained acceptance evidence. PP-018 and PP-034 were Implementation Ready at approval; PP-035 and PP-015 were `IR after PP-018`; PP-036 was `IR after PP-015`.

Execution update, 24 November 2026: PP-034 is Done with acceptance evidence in `docs/evidence/m3/PP-034.txt`. PP-018 is Done with worker retry rules and checks recorded in `docs/evidence/m3/PP-018.txt`. The Product Owner clarified that PP-018 owns worker retry rules and PP-035 owns the Admin recovery endpoint and audited new-run behavior. PP-035 passed its start-time check and is Done with evidence in `docs/evidence/m3/PP-035.txt`. PP-015 passed its fresh start-time check and is Done with evidence in `docs/evidence/m3/PP-015.txt`; its implementation covers reference confirmation, taxonomy/classification persistence, linkage reconciliation, and historical recomputation. PP-036 passed its fresh dependency/readiness check and is Done with evidence in `docs/evidence/m3/PP-036.txt`. The consolidated milestone review and recommendations are in `docs/evidence/m3/M3_COMPLETION_REPORT.md`. No approved requirement or specification was changed.

**Sequencing note:** The execution register and retained evidence timestamps indicate PP-034 was recorded complete before PP-018, despite the requested PP-018 → PP-034 order. This variance is recorded in `docs/evidence/m3/M3_COMPLETION_REPORT.md`; PP-034 passed its independent readiness/acceptance gates, and later dependent tickets followed their required gates.

PP-005's decision-resolution ticket is Done because the approved attempt-authority and taxonomy-version applicability dispositions, alternatives, tradeoffs, and affected-contract alignment are recorded. The initial taxonomy seed and `other_product_defect` issue-code policy remain explicitly pending and outside M3's classifier/activation scope. DAI-06 coverage calibration remains pending but does not block the approved fail-closed recomputation mechanics. M3 does not authorize detection activation, incident-producing current results, automatic notifications, OpenAI calls, migration execution without the backup hold point, or any other listed exclusion.
