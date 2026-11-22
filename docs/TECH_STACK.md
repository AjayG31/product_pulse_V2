# ProductPulse Technical Stack

**Version:** 1.0  
**Status:** Documents user-approved approaches and explicitly lists unresolved selections  
**Decision basis:** [Decision Register](DECISION_REGISTER.md) v1.7, with requirements checked against [PRD](PRD.md) v1.7  
**Confirmation date for approved approaches and PP-001 tooling:** 20, 21, and 22 November 2026

## Purpose and approval boundary

This document records the technical approaches and tooling explicitly approved in the Decision Register and the technical requirements that the PRD imposes. It does not select tools or services that remain unresolved. A listed **Approved approach** is approved at the level stated; exact compatible package releases are to be resolved during project setup and recorded in lockfiles, not inferred here. Approval does not imply an unnamed provider, credential arrangement, or deployment target.

This is a stack specification, not a full system architecture. No application code is created or authorized by this document.

## Approved stack

### Frontend

- **Approved approach:** React + TypeScript, with Recharts for dashboard charts. (ARC-01)
- **Approved tooling (PP-001):** React Router 8.x in client-side library mode for routing, MUI 9.x for UI components, and TanStack Query 5.x for server state; use React state/context for local state. Use compatible stable releases and record exact resolved package versions in the frontend lockfile during project setup. React Router 8.x currently requires React 19.2.7+ and Node 22.22+; resolve exact releases together at setup.
- **PRD requirements:** Desktop-first responsive interface; keyboard-accessible controls; readable chart labels and empty/loading/error states; color plus text for severity; consistent dashboard filters; aggregate polling every 30 seconds and a manual refresh control. (PRD §§6, 13.4)
- **Why it fits a solo-developer capstone:** One UI stack and one chart library cover the dashboard, product views, and incident evidence without adding a separate visualization service.
- **Open details:** Exact chart conventions remain subject to the UI specification.

### Backend and API

- **Approved approach:** Python FastAPI in one backend API for the single-retailer MVP, using the proposed REST surface as its starting contract. (ARC-02)
- **Approved Python tooling (PP-001):** Use CPython 3.12 with uv, `pyproject.toml`, and a checked-in `uv.lock`. Resolve compatible stable dependency releases at project setup and record exact versions in the lockfile; pin the uv executable to a tested release in project tooling setup.
- **PRD requirements:** Enforce authorization and validation on the server; keep OpenAI calls on the backend; paginate applicable endpoints; use consistent error responses and appropriate rate limits. (PRD §§8, 12–13)
- **Security constraints:** Keep provider credentials in protected server-side configuration; use TLS for deployed services, parameterized database access, and least-privilege filesystem permissions for the SQLite database file and persistent storage. Validate uploads and protect CSV exports against formula injection. These are requirements, not additional technology selections. (PRD §13.2; AGENTS.md)
- **Approved authentication approach (SEC-01):** Secure email/password authentication with server-side sessions for Admin and Business User roles; secure password hashes; session cookies with the `Secure` and `HttpOnly` attributes; appropriate CSRF protection; session expiry and logout invalidation; first Admin provisioned by a protected setup command; Admin-managed user creation and deactivation; no public self-registration or SSO. Exact session configuration and account recovery belong in `SECURITY.md`.
- **Why it fits a solo-developer capstone:** A single API keeps the request boundary and role enforcement in one place and avoids service-to-service infrastructure.
- **Open details:** Request/response schemas, upload preview/confirmation routes, settings/job contracts, API versioning, and the specific rate-limit policy belong in the API specification.

### Database and migrations

- **Approved approach:** SQLite is the only primary relational database for source records, classifications, incidents, audits, and related analytics. The API and one worker share the same database file on persistent local storage. Use versioned schema migrations. (ARC-03)
- **PRD requirements:** Preserve referential integrity and traceability from source to classification, cluster, and incident. Enforce the source identity pair and retain ingestion, classification, coverage, conflict, and notification records needed by the workflows. (PRD §§7, 11)
- **Why it fits a solo-developer capstone:** SQLite avoids a separately operated database service for the single-instance, non-production 10,000-record MVP while supporting the required links and audit history.
- **Approved ORM (PP-001):** SQLAlchemy 2.x for relational data access.
- **Approved migration tool (PP-001):** Alembic 1.x for versioned schema migrations. Resolve compatible stable releases during project setup and record exact versions in `uv.lock`.

### SQLite operating requirements

- SQLite is the MVP’s only primary relational database. Do not add another database or introduce Redis, Celery, Kafka, or a separate broker for this MVP.
- Enable SQLite foreign-key enforcement (`PRAGMA foreign_keys=ON`) on every database connection. Use WAL mode where supported and configure an explicit busy timeout on each relevant connection. The timeout duration remains an implementation parameter to specify and verify.
- Keep write transactions short. Never keep a database transaction open while calling OpenAI or an email provider: read/claim and commit, perform the external call without a transaction, then open a new short transaction to persist the result.
- Preserve uniqueness, idempotency, referential integrity, and audit traceability with relational constraints and stable event/source identities. When an incident state change requires a notification, persist the state change and its outbox event in one atomic SQLite transaction; if either local operation fails, neither commits (ARC-07). SQLite-compatible job claiming, retry, lease, stale-work recovery, and outbox processing must account for its single-writer behavior.
- Run the API and one separately running worker against the same database file on one application instance. The file must live on persistent local storage accessible to both processes and survive restarts/redeployments. Do not assume multi-instance access or a network filesystem.
- **Approved file artifacts (OPS-06):** Store uploaded CSV bytes and generated rejection-report bytes in a protected persistent local filesystem directory accessible to the API and worker. Keep it outside public/static delivery and out of Git. SQLite stores opaque artifact identifiers and metadata only; it never stores those file contents as BLOBs. Resolve identifiers only on the backend under the configured storage root, without accepting client paths. Preserve hashes, sizes, actor/timestamps when available, preview/hash integrity, and audit lineage.
- **Artifact publication:** Write to a temporary file within the protected storage filesystem, verify its bytes/hash, and atomically publish it under a server-controlled opaque identifier before committing the SQLite reference. If the metadata transaction fails, remove the newly published file; reconcile crash-created unreferenced files without deleting files that SQLite still references. Exact expiry and retention remain open under OPS-03.
- SQLite permits only one writer at a time. API and worker writes may serialize or contend; use short writes and a busy timeout, and measure the PRD performance targets under representative API/worker activity. Do not increase worker concurrency or add infrastructure as an unreviewed contention workaround.
- Avoid PostgreSQL-specific SQL, advisory locks, `SKIP LOCKED`, JSONB, and PostgreSQL-specific migration features. Exact background-job claim semantics, lease duration/renewal, stale-lease recovery, `SQLITE_BUSY` retry behavior, and reconciliation cadence remain for a downstream specification; notification lease recovery is defined in `ALERT_SPEC.md`.
- **Backup and restore:** Treat the SQLite database and its referenced artifact files as one consistent recovery set. Quiesce API, worker, and artifact publication/deletion while taking a coherent set; use a SQLite-consistent backup method (for example, SQLite’s backup API) or stop writes and checkpoint WAL before a coordinated snapshot. Do not copy only the main database file while active WAL writes may exist. Restore the database and artifact directory from the same set with API and worker stopped; do not mix database, sidecar, and artifact files from different snapshots. Verify SQLite integrity and foreign keys, then verify each referenced artifact resolves and its stored hash matches before restarting. Exact mechanism, cadence, and retention remain open under OPS-03.
- **Reset and rollback:** Restrict reset/reseed to the non-production synthetic environment. Take a consistent backup first when audit/evaluation evidence must be retained. Stop API and worker before replacing/resetting the file. Before a schema-changing release, preserve a compatible recovery snapshot; application rollback does not itself reverse schema changes. After restore/reset/rollback, verify integrity and foreign keys before restarting both processes. Backup cadence, retention, and the specific backup mechanism remain unselected under OPS-03.

### Linkage and source-coverage methodology

- **Approved unresolved-link behavior (PB-06):** Preserve valid records with unresolved supplier/batch links as `LINKAGE_PENDING`. Include them in distinctly labelled product-level analytics only when `product_id` is valid. Never fabricate supplier or batch identifiers. Do not create product-only incidents or automatic notifications from unresolved-link records. Recompute affected detection results after Admin reconciliation.
- **Approved source-coverage methodology (DAI-06):** Use UTC event timestamps for detection windows, preserve ingestion and processing timestamps, track explicit source-coverage intervals, never interpret missing coverage as zero complaints, recompute affected windows for late-arriving records, and suppress automatic warnings when required baseline coverage is insufficient.
- **Pending Calibration:** Exact coverage granularity, completeness criteria, and calibration parameters remain unresolved and must be specified in `DETECTION_SPEC.md`; these parameters are not Approved by the methodology decision.

### Background processing

- **Approved approach:** Run one separately running background worker. Persist job and notification outbox state in the same SQLite file used by the API. For a notification-triggering incident state change, commit the state change and its associated outbox event atomically in one SQLite transaction. Keep all OpenAI and email-provider calls out of interactive dashboard requests and outside database transactions. (ARC-04, ARC-07)
- **Approved worker selection (PP-001):** One separate Python worker uses a standard-library polling loop over durable SQLite job/outbox records. Do not add a queue, broker, or separate scheduler service. Poll interval and retry, lease, claim, recovery, SQLite busy, and reconciliation parameters remain open under PP-007.
- **PRD requirements:** Support durable job state, retries, failure visibility, reconciliation, historical Batch API processing, incremental processing, and idempotent ingestion and notifications. For each confirmed feedback import, persist an explicit Admin-selected mode: `HISTORICAL_BATCH` automatically dispatches through the Batch API and `INCREMENTAL_RESPONSES` through the Responses API after accepted feedback is persisted. Reference imports have no classification mode; Admin retries preserve the confirmed mode. Business Users cannot initiate or retry ingestion. (PRD §§5, 7.3, 8, 13.3; DAI-07)
- **Why it fits a solo-developer capstone:** One worker and the already-approved SQLite file reduce deployed components while supporting the asynchronous flows and recovery visibility.
- **Approved retry approach:** Use bounded retries for transient provider errors, persist terminal failures for Admin review/retry, keep operations idempotent, and schedule reconciliation. (OPS-02)
- **Open details:** Numeric retry/backoff limits, atomic background-job claim method, background-job lease/renewal/recovery policy, SQLite busy retry policy, and reconciliation cadence remain implementation-specification details. Notification outcome recovery is specified in `ALERT_SPEC.md`. A separate broker or database is not part of the MVP approach and requires a separately approved change.

**Recommended single-writer processing pattern (proposed for downstream review; not an additional approval):** Create each durable job/outbox item with its stable unique identity in a short transaction. The single worker claims an eligible item by recording a lease token and expiry in a short write transaction, then commits before making an OpenAI or email-provider call. It records the result in a new short transaction conditioned on the current lease token. Transient failures update the persisted attempt count and next eligible time; exhausted or permanent failures remain visible for Admin recovery. On restart, expired leases become eligible for reclamation and reconciliation repairs stale or incomplete work. For a notification-triggering incident state change, ARC-07 requires the incident update and outbox event to be persisted atomically; if either local database operation fails, neither commits. The worker performs the provider call only after that transaction commits and records its outcome in a new short transaction. Provider acceptance is not delivery, and exactly-once external delivery is not promised. `ALERT_SPEC.md` defines conservative notification recovery: abandoned IN_PROGRESS attempts become OUTCOME_UNKNOWN and are not automatically resent absent provider verification or an approved policy. Provider verification and external idempotency details remain open. Define background-job lease expiry/renewal, retry limits/backoff, stale-claim policy, and bounded `SQLITE_BUSY` handling before implementation.

### Performance targets to validate

- **PRD provisional targets:** Dashboard initial-load p95 of 3 seconds or less on the seeded 10,000-record dataset, and new feedback reflected within 60 seconds after successful classification, excluding provider queue delays. Measure event-to-display, ingestion-to-display, and classification-to-display separately. The 30-second poll interval is a UI cadence, not a processing SLA. (PRD §§6.2, 13.1)
- **Status:** These are PRD targets to validate, not new stack selections or guarantees.

### OpenAI integration

- **Approved approach:** Use one supported model and a common versioned classification contract across the historical Batch API path and incremental Responses API path. Evaluate a currently supported model against development data before selecting its identifier. (DAI-05)
- **PRD requirements:** Make calls from the backend; use strict Structured Outputs; store model, prompt/schema version, token usage, latency, and estimated cost; retry transient failures and expose exhausted failures; treat review text as untrusted input. The model classifies feedback but does not compute defect counts, thresholds, authorization, or send email. (PRD §§8, 9, 13)
- **Why it fits a solo-developer capstone:** A shared contract and model across the two paths reduce path-specific behavior and evaluation work.
- **Open decision — model identifier:** No model name or version is approved. Select it through the approved evaluation process and verify its support for the required APIs and strict output contract before implementation.
- **Open details:** Final schema fields, prompt versioning procedure, rate/cost limits, and retry numbers must be specified in the AI and processing specifications.

### Email adapter

- **Approved approach:** Use a backend adapter with a sandbox or local capture sink and a durable notification outbox. Do not configure production external delivery or supplier email for the capstone. Distinguish provider acceptance from delivery. (ARC-05)
- **PRD requirements:** Only Admin-managed approved internal/sandbox recipients; automatic High/Critical notification behavior and cooldown; manual preview with explicit confirmation; server-side recipient authorization; auditable exact content and recipient list; idempotency; no claim that acceptance proves delivery. (PRD §§6.8–10)
- **Why it fits a solo-developer capstone:** It supports an end-to-end notification demo without requiring real messages or production mail operations.
- **Open detail:** The approved approach does not select whether the sink is local or hosted, or name a provider. Keep the adapter boundary and choose the concrete sink in a later approved implementation decision.

### Testing tools and required verification

- **Approved backend/API tools (PP-001):** Use pytest for unit, integration, and API tests; use FastAPI `TestClient` with its HTTPX dependency for API tests.
- **Approved frontend tools (PP-001):** Use Vitest and React Testing Library for React tests; Playwright is rejected. No separate browser E2E framework is selected, and no PRD acceptance criterion specifically requires browser E2E automation. Where visual or interactive criteria require observation, retain the reproducible manual evidence required by the Definition of Done.
- **Approved local check runner (PP-001):** Use repeatable local PowerShell scripts to run checks. Add scripts with the relevant implementation work; this selection does not authorize scripts or tests in this documentation-only follow-up.
- **Other approved checks (PP-001):** Use Bandit, pip-audit, and npm audit for static/dependency security checks. Use OWASP ZAP Baseline and Locust for later-stage security and performance testing. Resolve compatible stable package releases during project setup and record them in lockfiles; pin the ZAP image before later-stage use.
- **Required verification from the PRD and AGENTS.md:** AGENTS.md requires automated tests for new functionality, checks mapped to acceptance criteria, and retained per-ticket evidence. The PRD requires unit, integration, security, and evaluation checks, including strict-schema validity; source-link integrity; duplicate/idempotency behavior; role checks including direct Business User upload attempts; prompt-injection handling; detection and held-out evaluation; notification confirmation/routing states; and performance measurement. Local scripts plus a documented pre-merge checklist and retained evidence are the approved verification and review process. (AGENTS.md; PRD §§14–16)
- **SQLite-specific verification to specify:** Check foreign-key enforcement on every connection, WAL mode where supported, the configured busy timeout, API/worker write contention, idempotent claims and outbox sends, stale-lease/restart recovery, and database integrity after backup/restore/reset/rollback. These are verification requirements, not a selection of test tools.
- **Operating boundary:** ZAP Baseline and Locust are later-stage checks and must target a local synthetic environment or an explicitly approved non-production target. These tools do not replace ticket-specific authorization, input-handling, prompt-injection, formula-injection, or evaluation checks. No detection or notification activation is implied.
- **Open details:** A separate coverage-reporting tool and threshold are not selected.

### Local verification and pre-merge evidence

- **Approved process (ARC-06 / PRD change RC-01):** Repeatable local PowerShell scripts run automated checks. A documented pre-merge checklist requires all applicable checks to pass on the exact revision proposed for merge and records the commands, revision, results, and evidence. A required failure blocks checklist approval until corrected and rerun.
- **Selected test tools:** Backend/API tests use pytest and FastAPI TestClient; frontend tests use Vitest and React Testing Library. Bandit, pip-audit, npm audit, and later-stage ZAP Baseline/Locust remain in scope as recorded above. No Playwright or browser E2E framework is selected.
- **Explicit exclusions:** Do not use GitHub Actions or another hosted CI service for merge gates. Local verification does not automatically enforce a merge; the documented checklist governs pre-merge approval.
- **Failure/restoration evidence:** Demonstrate a deliberately failing automated test followed by restoration to a passing state, retaining both run results and revision/evidence references. Keep this separate from AC18 deployment rollback and health-check evidence.
- **Implementation boundary:** Introduce scripts with relevant implementation work; this documentation update creates no scripts or tests. Pending evaluation thresholds remain pending and cannot be invented or treated as passed.

### Deployment

- **Approved requirements:** The PRD requires a non-production cloud environment, health checks, protected secrets, logs/usage visibility, a runbook, and a demonstrated rollback as AC18 external engineering evidence. Production deployment and production-ready multi-tenancy are outside the stated MVP scope. AC18 does not define a runtime API endpoint. (PRD §§4, 13.2–13.3, 15 AC18)
- **Approved deployment constraint:** One active application instance must use persistent local storage for the SQLite database file and protected artifact directory, accessible to the API and one worker and retained across restart/redeploy. Do not use network-filesystem or multi-instance assumptions.
- **Preferred proposed topology (OPS-01; not approved):** One Linux VM running Docker Compose, with the API and one worker sharing the same persistent local SQLite storage. The deployment must support protected secrets, health checks, logs, backups, and rollback.
- **Unresolved decision — hosting provider and suitability:** OPS-01 remains **Proposed**. No cloud hosting provider is approved. Select a provider and verify it supports the proposed topology and PRD deployment requirements before deployment approval.
- **Why a minimal deployment is appropriate:** The capstone needs a reviewable non-production demonstration, not production-scale infrastructure. Provider-specific secret handling, volume configuration, health checks, and rollback cannot be finalized until the target is selected and verified.

## Open decisions and downstream dependencies

The following remain open in the Decision Register and are relevant before the stack becomes a complete implementation baseline:

| Item | Current state | Effect on stack or downstream specifications |
|---|---|---|
| Hosted CI service | Resolved under ARC-06 / PRD change RC-01: no hosted CI merge gates; repeatable local scripts, pre-merge checklist, and evidence are approved | No hosted CI service or workflow is selected or required. Keep the required checks and exact-revision evidence. |
| Coverage reporting | Not selected under PP-001 | No coverage package or numeric coverage threshold is approved; select only if a later ticket requires one. |
| OpenAI model identifier | Evaluation-dependent; DAI-05 approves the selection process, not a model | Select and verify API/schema support before AI integration. |
| Email sink/provider | ARC-05 approach approved; local versus hosted sink not chosen | Select the concrete sandbox/capture target before notification integration. |
| Uncertain provider-send outcomes and external idempotency | Conservative OUTCOME_UNKNOWN recovery Approved; provider verification and external idempotency unresolved | Do not automatically resend an uncertain outcome unless verified or a separately approved policy permits it; do not claim exactly-once delivery. |
| Deployment host | OPS-01 Proposed | Linux VM with Docker Compose is the preferred proposed topology; select and verify a hosting provider before deployment. |
| SQLite concurrency/recovery | ARC-04 approach approved; detailed parameters unresolved | Specify job claiming, lease duration/renewal, stale-work recovery, `SQLITE_BUSY` retry, retry/reconciliation interaction, and recovery testing before implementation. |
| SQLite and artifact backup operations | OPS-03/OPS-06 approaches approved; specific parameters unresolved | Back up and restore the database plus referenced artifact files as one consistent set; cadence, retention, and mechanism remain open. |
| Artifact retention and expiry | OPS-03 parameters open | Keep upload and rejection-report artifacts available for the approved preview/rejection workflow; define expiry, cleanup ordering, and audit effects in the downstream API/operations specifications. |
| Authentication/session details | SEC-01 approach Approved | Exact session configuration and account recovery belong in `SECURITY.md`. |
| Unresolved-link behavior | PB-06 Approved | Product analytics are allowed for valid product identity; no product-only incidents or automatic notifications are generated from unresolved-link records; reconcile and recompute affected results. |
| Coverage parameters | DAI-06 methodology Approved; parameters Pending Calibration | Specify exact granularity, completeness criteria, and calibration parameters in `DETECTION_SPEC.md`. |
| Detection thresholds and minimum counts | PB-01 Pending Calibration | The application must support versioned deterministic configuration; final values remain uncalibrated. |
| Held-out dataset size | EV-01 methodology approved; size parameters Pending Calibration | Blocks final evaluation dataset sizing, not component selection. |

See [Decision Register](DECISION_REGISTER.md) for the recorded options, approvals, and confirmation date. These open items are intentionally not resolved by this stack document.

## Consistency check against the PRD

- SQLite is the only primary relational database. The API and the single worker share one persistent local database file on one application instance; protected upload/rejection-report files use a persistent local directory accessible to both. Foreign keys are enabled on every connection, WAL is used where supported, and write transactions remain short.
- The backend remains the only place for OpenAI credentials/calls, server authorization, deterministic defect calculations, alert thresholds, and notification sending.
- Historical processing uses Batch API; new feedback uses Responses API under the same versioned output contract.
- Admin-only manual CSV ingestion, preview/confirmation, partial acceptance, row-level errors, and job tracking remain in scope.
- A notification-triggering incident state change and its outbox event commit in one SQLite transaction; failures roll back both local changes. OpenAI and email-provider calls remain outside transactions.
- The dashboard’s 30-second polling cadence is a UI refresh cadence, not a processing SLA. PRD performance targets remain measurement targets unless separately calibrated/approved.
- Records with unresolved supplier/batch references are not assigned fabricated identifiers. Valid product identities may appear in product-level analytics with `LINKAGE_PENDING`; unresolved-link records do not create product-only incidents or automatic notifications (PB-06).
- Source-coverage methodology uses explicit UTC intervals and preserves event, ingestion, and processing times; missing coverage is not zero, late arrivals trigger recomputation, and insufficient required baseline coverage suppresses automatic warnings (DAI-06). Exact parameters remain Pending Calibration for `DETECTION_SPEC.md`.
- Only sandbox/internal approved recipients are in scope. No production external email or supplier email is enabled by this document.
- The PRD’s single synthetic retailer, 10,000-record evaluation dataset, P0 scope, and required local evaluation/pre-merge evidence are preserved.

## Source status

- `AGENTS.md` supplies project-level implementation and security constraints.
- `docs/PRD.md` v1.7 remains the requirements source of truth and labels its architecture section as recommended.
- `docs/DECISION_REGISTER.md` v1.7 records the approaches and PP-001 tooling the user approved on 20, 21, and 22 November 2026, plus remaining Open or Pending Calibration choices.
- `docs/ARCHITECTURE.md` v1.4 is Approved. `docs/DATA_MODEL.md` v1.4 and `docs/API_SPEC.yaml` v1.4.0 are Approved — Design Baselines, subject to their documented conditions; v1.1 and v1.1.0 were the previous approved baselines, and intermediate v1.2/v1.3 revisions were not separately approved. The API contract was approved on 21 November 2026; classification label cardinality is capped at two, with one PRIMARY and at most one SECONDARY label.
