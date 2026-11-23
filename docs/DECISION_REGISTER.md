# ProductPulse Decision Register

**Version:** 2.0  
**Status:** Partially confirmed; approval state is recorded per decision below.
**Purpose:** Capture unresolved product, data, security, architecture, operations, and evaluation decisions before ProductPulse specifications are finalized.  
**Source material:** `AGENTS.md`, `docs/PRD.md` v1.7, `docs/ARCHITECTURE.md` v1.5, the UI/API/Data Model readiness review findings, and user confirmations dated 20, 21, and 22 November 2026.

## How to use this register

The PRD remains the product-requirements source of truth. This register records open choices and practical recommendations; it does not amend the PRD or authorize implementation. A recommendation becomes **Approved** only after the user confirms it. Until then, treat it as a proposal and raise conflicts rather than silently choosing a different behavior.

Statuses:

- **Proposed** — a practical recommendation is recorded but needs confirmation.
- **Approved** — the user explicitly confirmed the recorded approach; any separately listed pending parameters remain open.
- **Pending Calibration** — decide from development data and record the result before held-out evaluation.
- **Deferred** — intentionally outside MVP according to the PRD’s priority/scope; reconsider only through change control.

Impacted specifications name the existing PRD sections and the downstream specification(s) that should capture the decision. Those downstream specifications are not created by this document.

## Baseline requirements preserved from the PRD

These are constraints for later specifications, not open choices in this register:

- Admin-only, manually initiated CSV ingestion in MVP; Business Users cannot upload or trigger ingestion. Server-side authorization is required.
- Validate and preview uploads before explicit confirmation; support partial row acceptance and row-level rejection reasons. Enforce the PRD’s 20 MB and 50,000-row limits.
- Preserve source identity and source text; identical re-uploads are no-ops, changed payloads are conflicts, and unresolved supplier/batch links are not fabricated.
- Use OpenAI on the backend: Batch API for historical backlog and Responses API for new feedback, with a common strict, versioned classification contract. Treat feedback as untrusted input.
- Classification is not the alert engine. Defect counts, thresholds, severity, authorization, and email sends use deterministic backend logic.
- Use UTC event time; preserve ingestion/processing time separately; expose classification and source-coverage gaps; do not present unsupported return/failure rates.
- Maintain source-to-classification-to-cluster-to-incident traceability, audit individual incident actions, and make ingestion and notification handling idempotent.
- When an incident state change requires a notification, commit the incident change and its outbox event atomically in one SQLite transaction; if either local write fails, neither commits. Provider calls remain outside transactions, and external exactly-once delivery is not promised.
- Preserve valid unresolved-link records as `LINKAGE_PENDING`; include them in product-level analytics only when product identity is valid, and do not create product-only incidents or automatic notifications from them. Recompute affected detection results after Admin reconciliation.
- No real customer, C5i, or client data, PII, or PHI. No automatic supplier emails, production email delivery, or external remedial action in MVP.
- Preserve the required P0 capabilities and evaluation evidence. P1/P2 scope remains as prioritized in the PRD unless explicitly changed.

## Product Behavior

### PB-01 — Detection rule calibration and user-visible severity

- **Description:** Finalize the provisional 7-day observation / preceding 28-day baseline rules, minimum counts, severity thresholds, and behavior for zero or insufficient history.
- **Options:** (1) Keep the PRD table unchanged; (2) calibrate values on development planted scenarios, then freeze them before held-out evaluation; (3) defer severity assignment and show trend-only results until calibration is complete.
- **Recommended option:** Use the PRD table as the initial configurable hypothesis, calibrate on development scenarios, then freeze and version it before held-out evaluation. Keep the PRD zero-baseline count gates. With insufficient coverage, show uncertainty and do not send automatic email.
- **Reasoning and trade-offs:** This preserves the specified explainable count-based behavior while avoiding an unsupported performance claim. Calibration takes time and the final thresholds may differ from the demo defaults.
- **Impacted specifications:** PRD §§9.1–9.4, 14.1, 19.1; future Detection Rules and Dashboard/Incident specifications.
- **Status:** Pending Calibration
- **Confirmation date:** 20 November 2026

### PB-02 — Incident transition validation and concurrent actions

- **Description:** Specify valid status transitions, what happens when two users act at once, and how transition attempts are recorded.
- **Options:** (1) Permit only the documented sequence and reject other transitions; (2) permit additional direct transitions; (3) allow last-write-wins updates without conflict handling.
- **Approved approach:** Preserve the documented sequence `NEW → ACKNOWLEDGED → INVESTIGATING → RESOLVED` and `RESOLVED → REOPENED → INVESTIGATING`; validate transitions on the server and reject stale/conflicting updates with an auditable result. Do not add shortcut transitions without approval.
- **Reasoning and trade-offs:** The strict sequence is easiest for a solo developer to test and preserves a clear investigation history. It may require an extra user action in some cases.
- **Impacted specifications:** PRD §§6.4–6.6, 9.3, 11–12, AC15; future Incident Lifecycle and API specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### PB-03 — Recurrence boundary

- **Description:** Confirm the proposed 30-day boundary for reopening a resolved incident versus creating a linked episode.
- **Options:** (1) Keep 30 days; (2) choose a different interval after product review; (3) defer separate episode behavior and keep one incident per cluster for the capstone.
- **Approved approach:** Use the 30-day boundary for reopening the same incident versus creating a linked episode, computed from the stored resolution time and audited as described in the PRD.
- **Reasoning and trade-offs:** The confirmed interval is already consistently described in the PRD and AC22. It is straightforward to demonstrate; changing it requires explicit change control.
- **Impacted specifications:** PRD §§9.3, 14, 15 AC22, 19.1; future Incident Lifecycle and Evaluation specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### PB-04 — Notification trigger and cooldown semantics

- **Description:** Define which rule events create an automatic email, what counts as a repeated same-severity event, and how escalation interacts with cooldown.
- **Options:** (1) Send on every qualifying evaluation; (2) send on initial threshold crossing and severity escalation, then apply the per-incident cooldown; (3) send only when an Admin manually initiates an alert.
- **Approved approach:** Follow the PRD's intended behavior: automatic email for qualifying High/Critical threshold crossings, bypass cooldown for a severity escalation, and suppress repeated same-severity automatic sends for exactly 86,400 seconds per incident and severity, shared across all notification routes. The cooldown is fixed in the MVP and cannot be overridden by notification-rule requests or Admin configuration. Manual sends remain separately confirmed and audited. Define a stable event identity for retries. Audit cooldown suppression with an incident `SYSTEM_DECISION` event.
- **Reasoning and trade-offs:** This limits noise while preserving escalation. The precise treatment of severity decreases, re-crossings after cooldown, and recurrence should be written into the notification specification before implementation.
- **Pending clarification:** The cooldown timestamp anchor, same-severity re-crossing behavior, and other severity edge cases remain open; this approval does not settle them.
- **Impacted specifications:** PRD §§9.2–9.4, 10, 11, 15 AC10–AC14; `docs/ALERT_SPEC.md`, `docs/API_SPEC.yaml`, and `docs/DATA_MODEL.md`.
- **Status:** Approved
- **Confirmation date:** 20 November 2026
- **Clarification date:** 21 November 2026 (per-incident/per-severity scope across routes and suppression audit)

### PB-05 — Dashboard metric definitions and filter behavior

- **Description:** Define the time window, counting unit, eligibility, and warning semantics for every KPI and chart, including “active warnings,” “critical warnings,” and “products at risk.”
- **Options:** (1) Define each measure independently in UI code; (2) create one metric glossary and use it across dashboard, product detail, and incident evidence; (3) remove measures whose definition is not yet settled.
- **Approved approach:** Create a shared metric glossary before the dashboard specification. This approval covers creating the glossary only; no metric definitions are approved by PB-05. The glossary must record each definition's source and status, use the PRD's explicit counting requirements, keep complaint records, return records, and returned units separate, and omit or label unsettled measures rather than imply a failure rate without a valid denominator.
- **Reasoning and trade-offs:** A shared glossary prevents charts and drill-downs from disagreeing. It adds a short specification step and may reduce the initial dashboard surface.
- **Impacted specifications:** PRD §§6.2–6.5, 9.1, 13.4; future Metrics and Dashboard specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### PB-06 — Product-level behavior for unresolved supplier/batch links

- **Description:** Define the product-level analytics and incident boundary for feedback marked `LINKAGE_PENDING` before supplier/batch reconciliation.
- **Options:** (1) Keep the records in product-level analytics only until reconciliation; (2) permit separately labelled product-only incidents using a defined product/issue key; (3) exclude unresolved records from all defect analytics.
- **Approved approach:** Preserve valid records with unresolved supplier/batch links and show `LINKAGE_PENDING`. Include them in distinctly labelled product-level analytics only when `product_id` is valid. Never fabricate supplier or batch identifiers. Do not generate product-only incidents or automatic notifications from unresolved-link records. Recompute affected detection results after Admin reconciliation.
- **Reasoning and trade-offs:** Product-level analytics retain useful evidence while unresolved links remain visible. Suppressing incidents and automatic notifications avoids duplicate or misattributed warnings before linkage is corrected.
- **Impacted specifications:** PRD §§7.2–7.3, 9.1, 11, 15 AC19; `docs/TECH_STACK.md`; `docs/ARCHITECTURE.md`; future `DATA_MODEL.md`, `API_SPEC.yaml`, and `DETECTION_SPEC.md`.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

PB-06 does not approve product-only incidents or automatic notifications from unresolved-link records.

### PB-07 — Solo-developer delivery sequence for P0

- **Description:** Choose a delivery approach that fits one developer without silently reducing the P0 scope.
- **Options:** (1) Build all P0 screens and services in parallel; (2) deliver vertical slices through the required pipeline; (3) remove P0 capabilities to fit an informal schedule.
- **Approved approach:** Preserve all P0 requirements and build in small vertical slices that prove the end-to-end path: synthetic data and identity/linkage, secure Admin ingestion, classification, deterministic detection, dashboard evidence, incident actions, sandbox notifications, then evaluation and deployment evidence. Use the PRD’s suggested phases as a sequence, not a staffing plan.
- **Reasoning and trade-offs:** This gives a solo developer reviewable increments and exposes integration risks early. It does not promise a schedule; the P0 scope remains broad and may require owner-approved scope changes if time is constrained.
- **Impacted specifications:** PRD §§4–5, 14–18; future task plan and ticket acceptance criteria.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### PB-08 — MVP and deferred feature boundary

- **Description:** Confirm that the PRD’s P0/P1/P2 priorities remain the scope boundary for the capstone.
- **Options:** (1) Preserve the PRD priorities; (2) promote selected P1/P2 items into MVP; (3) reduce P0 scope.
- **Approved approach:** Preserve the PRD priorities: defer report export, watched-storage ingestion, and owner assignment/escalation (P1); defer financial impact, advanced forecasting, and natural-language assistant (P2); keep Viewer and SSO out of MVP. Any P0 reduction or promotion requires explicit product-owner approval and updated acceptance criteria.
- **Reasoning and trade-offs:** This is the smallest scope consistent with the stated PRD. Deferral means those capabilities should not be assumed in architecture or tickets.
- **Impacted specifications:** PRD §§3.3–4, 6, 17–19; future MVP Scope and task plan.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### PB-09 — Detection result identity, application, and historical recomputation

- **Description:** Define how detection results are fingerprinted and exposed, how qualifying current results are applied to incident state safely, and how late or changed inputs refresh historical results.
- **Approved approach:** Include classification-completeness assessments, relevant classification state changes, and the coverage-policy version in each deterministic result fingerprint; a transition from pending to definitive no-defect must produce a new result identity. Count feedback once when PRIMARY and SECONDARY labels map to the same logical defect, citing PRIMARY as evidence. A higher-severity qualifying result updates the existing incident severity and appends an audit event while preserving the approved lifecycle; ALERT_SPEC owns escalation notification and cooldown bypass details. Expose read-only, paginated detection results with NO_TRIGGER and INSUFFICIENT_COVERAGE rationale to the existing authorized roles. Recompute affected historical windows after late arrivals and rule changes, retaining prior evidence and audit history; historical results alone never change incidents or create automatic notifications. Only qualifying current monitoring results may be applied to incident/outbox state. Preserve PB-03's 30-day recurrence boundary. Apply current results idempotently and recoverably: a result with pending application is retried even when its result key already exists, and incident state, incident audit, application completion, and required outbox data remain atomic under ARC-07.
- **Reasoning and trade-offs:** A content-derived result identity prevents classification-state changes from reusing stale coverage outcomes. Historical evidence stays reproducible without retroactive notification noise. A durable application state makes worker recovery explicit while retaining the single-writer SQLite design.
- **Impacted specifications:** `docs/DETECTION_SPEC.md`, `docs/DATA_MODEL.md`, `docs/API_SPEC.yaml`, and `ALERT_SPEC.md` for notification escalation/cooldown behavior. This decision does not approve PB-01 thresholds or DAI-06 coverage scope, completeness parameters, or calibration values.
- **Status:** Approved
- **Confirmation date:** 21 November 2026

## Data & AI

### DAI-01 — CSV schemas, reference files, mapping precedence, and parser contract

- **Description:** Finalize review, return, and reference CSV contracts, including parser limits, timestamp/identifier handling, validation, and mapping-conflict application.
- **Options:** (1) Accept only the PRD's proposed review/return columns and no reference files; (2) support documented reference files and define a single deterministic resolution order; (3) allow multiple import formats and operator-selected mappings.
- **Approved approach:** Preserve one documented template per source type and DAI-01's existing precedence: valid identifiers in feedback rows first, otherwise explicit imported reference data. The file-part limit is 20,000,000 bytes (decimal 20 MB), enforced while streaming before parsing; permit at most 50,000 logical data records after the header, counting blank records. Oversize returns 413; row-cap excess returns 422.
  Accept strict UTF-8 only, allowing and stripping one UTF-8 BOM only at byte offset zero; reject malformed UTF-8 and other encodings. Use the RFC-4180-style CSV contract. Pin parser contract identifiers to reviews-v1, returns-v1, product-reference-v1, supplier-reference-v1, and batch-reference-v1; increment the relevant version when parsing, normalization, or validation semantics change.
  Accept RFC 3339/ISO-8601 timestamps only with Z or an explicit offset and no more than three fractional-second digits. Normalize to a UTC instant represented at fixed millisecond precision; reject offset-free values and excess precision without guessing or rounding.
  Enforce decoded field limits without truncation: review/return feedback text 16,384 Unicode code points; identifiers 256 code points; other mapped text 1,024 code points; each decoded field at most 65,536 UTF-8 bytes. Preserve source text and identifier code points. Source/product/supplier/batch identifiers are exact and case-sensitive after CSV/UTF-8 decoding; do not trim, case-fold, or Unicode-normalize them. Reject empty, whitespace-only, or leading/trailing-whitespace identifiers.
  Keep conflicting reference mappings visible for Admin review. KEEP_EXISTING resolves with no data change; DISMISS dismisses with no data change; APPLY_INCOMING_REFERENCE applies only validated incoming reference fields when the expected existing-value hash still matches. Apply atomically, record before/after provenance, and return 409 on stale state.
- **Reasoning and trade-offs:** Decimal MB makes the limit portable and exact; logical-record counting matches CSV data rather than physical newline count, though blank records consume the cap. UTF-8/BOM-only parsing avoids ambiguous transcoding; explicit offsets and millisecond precision keep UTC ordering deterministic but reject some otherwise convertible input. Exact IDs protect source identity and auditability but reject common accidental whitespace. Fixed field limits bound memory and model inputs without losing customer text; large values must be corrected at source. Explicit mapping review costs Admin time but avoids guessing or last-write-wins.
- **Impacted specifications:** PRD §§5.3, 7.1-7.4, 11, 12, 15 AC02-AC04/19/23; docs/API_SPEC.yaml; docs/SECURITY.md; docs/DATA_MODEL.md; docs/UI_SPEC.md; PP-004 and dependent ingestion/conflict tickets.
- **Status:** Approved
- **Confirmation date:** 22 November 2026
### DAI-02 — Duplicate rows and changed-record conflicts

- **Description:** Clarify behavior for repeated identities within one upload and for changed payloads already stored.
- **Options:** (1) Reject all repeated identities in a file; (2) accept one identical row once and report differing rows as conflicts; (3) silently use the last row.
- **Approved approach:** Apply global (source_type, source_record_id) uniqueness. Compare deterministic canonical payload hashes after approved CSV parsing and timestamp normalization, while preserving source text. An identical stored or first-in-file payload is a DUPLICATE_NOOP; it creates no second source record. A differing payload is a SOURCE_PAYLOAD conflict and never overwrites source text/event time. Within a file, the first valid row for an identity is the comparison candidate; later identical rows are no-ops and later differing rows are conflicts. Source conflicts may be resolved by KEEP_EXISTING or DISMISS only; incoming source text cannot be applied.
- **Reasoning and trade-offs:** This keeps reprocessing idempotent and source history trustworthy. First-row precedence is deterministic and avoids last-write-wins, but a malformed first occurrence does not reserve an identity; the first valid row does. Admins may need a later correction workflow, which remains outside this contract.
- **Impacted specifications:** PRD §§7.3, 11, 15 AC03-AC04/23; docs/API_SPEC.yaml; docs/DATA_MODEL.md; docs/UI_SPEC.md; PP-004 and dependent ingestion/conflict tickets.
- **Status:** Approved
- **Confirmation date:** 22 November 2026
### DAI-03 — Classification states and operator recovery

- **Description:** Define stored states and recovery paths for queued, completed, invalid, failed, uncertain, and needs-review classifications.
- **Options:** (1) Use a minimal state model with retry then needs-review; (2) expose separate transient and permanent failure states; (3) map failures to `no_defect`.
- **Approved approach:** Use explicit queued/in-progress, completed, retryable-failed, terminal-failed, and needs-review outcomes; never convert failure or uncertainty to `no_defect`. Semantic uncertainty maps to `NEEDS_REVIEW`. Transient provider/transport failures map to `RETRYABLE_FAILED` only while eligible under the bounded retry policy. Provider refusals, invalid output, source-identity or evidence-validation failures, permanent errors, and exhausted retries map to `TERMINAL_FAILED`; they are never `COMPLETED` or `NO_DEFECT`. Show counts and coverage as required by the PRD. Let Admin retry failed processing as a new immutable classification attempt; define any human relabelling workflow separately before adding it.
- **Reasoning and trade-offs:** Explicit states preserve measurable coverage and prevent silent false negatives. More states require clear UI labels and monitoring.
- **Impacted specifications:** PRD §§6.2, 6.5, 8.1–8.3, 13, 15 AC05/AC07/AC24; future AI Classification and Processing Jobs specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026
- **Outcome-mapping refinement confirmed:** 21 November 2026

### DAI-04 — Taxonomy governance and historical reclassification

- **Description:** Decide who may change taxonomy/issue codes, how changes are versioned, and whether previous records are reclassified.
- **Options:** (1) Freeze taxonomy for MVP after initial approval; (2) allow Admin versioned edits but classify new records only under the new version; (3) automatically reclassify all historical data after every change.
- **Approved approach:** Version and audit Admin-controlled taxonomy changes as the PRD specifies; freeze the initial version for the held-out evaluation. Each classification retains the taxonomy version used. Map each versioned specific issue code to a stable logical defect identifier. Reuse an identifier across versions only when the defect meaning is semantically equivalent; create a new identifier when the meaning changes, and never automatically merge changed meanings. Cluster semantically equivalent defects by the stable identifier. For the MVP, apply a new version only to new/retried classifications unless a separately approved reclassification job is defined.
- **Reasoning and trade-offs:** This limits cost and keeps evaluation reproducible. Historical comparisons across taxonomy versions need to show version context and may not be directly comparable.
- **Impacted specifications:** PRD §§6.7, 8.2–8.3, 9.1, 11, 14, 19; `docs/ARCHITECTURE.md` §§9–10; `docs/DATA_MODEL.md` §§4.5–4.7, 5–6; future AI Classification and Configuration specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026 (taxonomy-version cluster-identity extension confirmed)

### DAI-05 — Model selection and classification contract evolution

- **Description:** Select the supported model and define how the shared Batch/Responses output contract changes over time.
- **Options:** (1) Choose one model supporting required structured outputs and both processing paths; (2) use separate models for historical and incremental work; (3) select a model solely by cost or solely by evaluation score.
- **Approved approach:** Evaluate a currently supported model against the development dataset, require support for the PRD’s strict structured output in both APIs, and use the same model and versioned contract for both paths in MVP. Record model, prompt, schema, usage, latency, and cost. Do not set a model identifier in this register.
- **Reasoning and trade-offs:** One model reduces path-to-path differences and operational work. It may not be cheapest or best for every class; model changes require regression evaluation and version tracking.
- **Impacted specifications:** PRD §§8.1–8.3, 14, 16; future AI Specification and Evaluation Plan.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### DAI-06 — Historical coverage and late-arriving feedback

- **Description:** Define when a 28-day baseline is complete, how source coverage is declared, and how delayed events affect past windows and incidents.
- **Options:** (1) Treat any imported records as coverage; (2) require explicit complete coverage intervals by source and applicable scope; (3) disable baseline-based detection entirely.
- **Approved methodology:** Use UTC event timestamps for detection windows; preserve ingestion and processing timestamps; track explicit source-coverage intervals; do not interpret missing coverage as zero complaints; recompute affected windows for late-arriving records; and do not send automatic warnings when required baseline coverage is insufficient.
- **Classification-count rule:** Exclude pending, failed, needs-review, and otherwise non-definitive classifications from confirmed defect counts. The approved DAI-06 coverage policy determines whether source and classification coverage is sufficient. Automatic detection remains disabled until the required coverage policy and calibration are approved.
- **Pending parameters:** Exact coverage granularity, completeness criteria, and calibration parameters remain unresolved and must be specified in `DETECTION_SPEC.md`. These parameters are not Approved by this methodology confirmation.
- **Reasoning and trade-offs:** Explicit coverage prevents absence of data from being presented as zero defects. Granularity and completeness criteria affect dataset/reconciliation work and require calibration before implementation details are finalized.
- **Impacted specifications:** PRD §§7.4, 9.1–9.2, 11, 15 AC16/AC20–AC21; `docs/TECH_STACK.md`; `docs/ARCHITECTURE.md`; `docs/DETECTION_SPEC.md`, `docs/DATA_MODEL.md`, and `docs/API_SPEC.yaml`.
- **Status:** Pending Calibration
- **Confirmation date:** 20 November 2026
- **Clarification date:** 21 November 2026 (definitive-count exclusion and activation gate; calibration remains pending)

### DAI-07 — Explicit import processing mode and automatic classification dispatch

- **Description:** Select and persist the classification path for each confirmed review/return import while keeping reference-data imports outside the classification flow.
- **Options:** (1) Infer the path from timestamps or file contents; (2) require an explicit mode at Admin confirmation and dispatch automatically; (3) require a separate post-import classification command.
- **Approved approach:** Require an explicit Admin-selected `HISTORICAL_BATCH` or `INCREMENTAL_RESPONSES` mode when confirming a review/return import. After accepted feedback is persisted, automatically queue classification through the corresponding OpenAI Batch API or Responses API path. For Batch work, persist every immutable classification attempt and its source/job relationship before provider submission; use `classification_id` as the Batch `custom_id`; reconcile by that ID, never output order. Persist the uploaded input-file ID before Batch creation and include the stable ProductPulse job ID in Batch metadata so an ambiguous submission can be recovered idempotently. A retry retains the import mode and creates a new immutable classification attempt and ID. Reference-data imports have no classification mode. Business Users cannot initiate, confirm, or retry ingestion.
- **Reasoning and trade-offs:** Explicit mode selection avoids inferring historical intent from timestamps or content and makes retries reproducible. Automatic dispatch keeps classification part of the confirmed ingestion workflow without adding another user action.
- **Impacted specifications:** PRD §§5.1, 5.3, 7.3, 8.1, 15 AC02–AC08; `DATA_MODEL.md`; `ARCHITECTURE.md`; `API_SPEC.yaml`; future ingestion and AI-processing specifications.
- **Status:** Approved
- **Confirmation date:** 21 November 2026 (Batch correlation and recovery refinement confirmed)

### DAI-08 — Interactive CSV column mapping

- **Description:** Specify how the Admin maps uploaded CSV headers to canonical fields for each PRD template.
- **Options:** (1) Accept only fixed canonical headers and validate them; (2) provide an interactive source-column-to-canonical-field mapping with explicit handling for unused columns; (3) infer mappings without Admin review.
- **Approved approach:** Preserve PRD §5.3's explicit "Map / validate columns" step. Admins map source columns by zero-based index and exact header text. Each required canonical target must be mapped exactly once, no canonical target may be used by two source columns, and every source column is explicitly mapped or marked IGNORE only when it is optional. A missing or invalid required mapping blocks confirmation. The server validates the mapping against the uploaded bytes and binds the immutable mapping snapshot, parser contract version, and SHA-256 of the exact staged bytes to the preview. Any byte or mapping change requires a new preview; the same idempotency key and same canonical request returns the original preview, while reuse with different request content returns 409.
- **Reasoning and trade-offs:** This satisfies the PRD workflow while keeping validation and normalization authoritative on the server. Explicit mapping and immutable preview binding make the process reviewable but require a new preview after every correction.
- **Impacted specifications:** PRD §5.3 and §7; docs/UI_SPEC.md, docs/API_SPEC.yaml, and docs/DATA_MODEL.md; PP-004 and dependent ingestion tickets.
- **Status:** Approved
- **Confirmation date:** 22 November 2026
## Architecture

The PRD §16 stack began as a proposal. Entries marked Approved record user-confirmed approaches only. `docs/ARCHITECTURE.md` v1.5 is Approved. On 21 November 2026, `docs/API_SPEC.yaml` v1.4.0, `docs/UI_SPEC.md` v0.3, and `docs/DATA_MODEL.md` v1.4 were approved as conditional design baselines; their prior approved API/Data Model versions were v1.1.0/v1.1, and intermediate revisions were not separately approved. Subsequent approved conditional revisions are API_SPEC v1.5.2, UI_SPEC v0.4.1, and DATA_MODEL v1.5.2. `DETECTION_SPEC.md` v1.0 remains the Approved — Design Baseline; its v1.1 coverage/count clarification is Draft pending review and remains subject to the calibration and pre-implementation dependencies recorded there. Alert and implementation specifications remain separate downstream artifacts.

### ARC-01 — Frontend and charting stack

- **Description:** Select the web UI and charting approach for the desktop-first dashboard.
- **Options:** (1) Adopt the PRD proposal of React + TypeScript and select one charting library; (2) use another familiar web UI stack; (3) build server-rendered pages with limited charting.
- **Approved approach:** Use React + TypeScript with Recharts for dashboard charts. Keep filters, definitions, accessible text labels, and 30-second aggregate polling aligned with the PRD.
- **Approved supporting tools (PP-001, 21 November 2026):** React Router 8.x, MUI 9.x, and TanStack Query 5.x; use React state/context for local state. Resolve exact compatible releases in the frontend lockfile during project setup. The current React Router 8.x baseline requires React 19.2.7+ and Node 22.22+; confirm the exact compatible stable releases when creating the project lockfile.
- **Reasoning and trade-offs:** It matches the existing proposal and supports the dashboard interactions. It introduces frontend tooling and library learning/maintenance for a solo developer.
- **Impacted specifications:** PRD §§6, 13.4, 16; future Architecture and UI specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### ARC-02 — Backend framework and API shape

- **Description:** Choose the backend framework and confirm whether the proposed REST surface is the interface contract.
- **Options:** (1) Adopt Python FastAPI and the proposed REST endpoints; (2) choose another backend framework; (3) combine multiple backend services.
- **Approved approach:** Adopt the PRD’s FastAPI proposal and one backend API for the single-retailer MVP; treat the REST table as a starting contract and add explicit upload-preview/confirm and settings/job details before implementation. Keep OpenAI calls and authorization on the backend.
- **Reasoning and trade-offs:** A single API keeps deployment and authorization simple. One service may become less separable later, which is acceptable for the capstone unless measured needs differ.
- **Impacted specifications:** PRD §§5–6, 8, 12, 16; future Architecture and API specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### ARC-03 — Persistence technology and migration approach

- **Description:** Choose the primary datastore and how schema changes are tracked.
- **Options:** (1) Retain the PRD v1.1 PostgreSQL recommendation (historical option); (2) use SQLite as the only primary relational database for the MVP; (3) use separate databases for analytics and operational records.
- **Approved approach:** Use SQLite as the only primary relational database for the MVP, with one database file shared by the API and worker on persistent local storage. Use relational constraints for source identity, audit, incident, and notification links, and retain versioned schema migrations. Keep analytics in the same database for the 10,000-record capstone. Avoid PostgreSQL-specific SQL and features.
- **Reasoning and trade-offs:** SQLite keeps the 10,000-record, single-developer, non-production MVP's infrastructure small while supporting the required relational integrity and traceability. It permits only one writer at a time, so API and worker writes can contend; short transactions, an explicit busy timeout, and contention/recovery verification are required. It does not support the assumed multi-instance or network-filesystem deployment model. A move beyond this single-instance limit would require a separately approved decision.
- **Approved tooling (PP-001, 21 November 2026):** SQLAlchemy 2.x for ORM/data access and Alembic 1.x for versioned migrations. Resolve exact compatible stable releases and record them in `uv.lock` during project setup.
- **Impacted specifications:** PRD §§7, 11, 13, 16; future Architecture and Data Model specifications.
- **Status:** Approved
- **SQLite decision date:** 20 November 2026
- **PP-007 clarification (22 November 2026):** Use a per-connection SQLite busy timeout of 5 seconds. After a timed-out `SQLITE_BUSY`, roll back the transaction and allow up to 2 additional retries of the same idempotent database unit. The retry budget is separate from durable job retry/backoff and does not authorize retrying other SQLite errors or non-idempotent side effects.

### ARC-04 — Durable background job design

- **Description:** Select the smallest design that supports durable ingestion/classification work, retries, status visibility, reconciliation, and notification outbox delivery.
- **Options:** (1) SQLite-persisted jobs and notification outbox with one separately running worker; (2) a separate durable queue and worker; (3) synchronous processing in API requests.
- **Approved approach:** Use one separately running background worker. Persist durable job and notification outbox state in the same SQLite file used by the API for the initial 10,000-record non-production application. Do not make long OpenAI or email-provider calls part of dashboard requests or hold database transactions open during those calls. For atomic incident-state/outbox persistence, apply ARC-07. Do not add a broker or another database for the MVP.
- **Approved worker implementation (PP-001, 21 November 2026):** Use one separate Python worker with a standard-library polling loop over durable SQLite job/outbox records. Do not add a queue, broker, or separate scheduler service.
- **Reasoning and trade-offs:** This meets the PRD’s durable-state requirement while keeping deployed components low. SQLite serializes writes, so job claims, retries, leases, recovery, and outbox processing must use short transactions and be idempotent. Lock contention may limit throughput. The exact claim/lease and `SQLITE_BUSY` recovery policy remains a downstream specification item; this approval does not settle those implementation parameters.
- **Impacted specifications:** PRD §§5, 8.1, 9.1, 10.3, 11, 13.3, 16; future Architecture and Job Processing specifications.
- **Status:** Approved
- **SQLite job/outbox decision date:** 20 November 2026
- **PP-007 clarification (22 November 2026):** Poll durable jobs/outbox every 5 seconds. Claim one item at a time in a short `BEGIN IMMEDIATE` transaction and persist an owner token with a 5-minute lease. Renew an active lease every 60 seconds, including during long provider calls, in a separate short transaction conditioned on the current owner token. Reject stale-owner result writes. Run reconciliation at worker startup and every 60 seconds while running. Keep all provider calls outside SQLite transactions.

### ARC-05 — Email adapter and non-production delivery target

- **Description:** Select the provider/adapter used by automatic and manual email flows.
- **Options:** (1) Use a sandbox/capture provider; (2) use a local mail sink; (3) use a real internal mail account.
- **Approved approach:** Use a sandbox or local capture sink for all MVP email, with a backend adapter and durable outbox. Do not configure real external delivery for the capstone. Preserve provider-accepted versus delivered status distinctions.
- **Reasoning and trade-offs:** It enables end-to-end demo and retry testing without sending real messages. Provider callbacks and exact delivery behavior may be limited in a sink.
- **Impacted specifications:** PRD §§6.8, 9.4, 10, 11, 16, 18–19; future Notification and Security specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### ARC-06 — Local verification and pre-merge evidence

- **Description:** Record the PRD-approved local verification process for required automated checks, pre-merge review, and deliberate failure/restoration evidence.
- **Product Owner decisions (21 November 2026):** Do not use GitHub Actions or Playwright. Use repeatable local PowerShell scripts to run checks. Backend/API tests use pytest and FastAPI TestClient; frontend tests use Vitest and React Testing Library. Keep the approved application technologies unchanged.
- **Product Owner decision (22 November 2026):** Explicitly approve local automated verification in place of GitHub-hosted CI merge gates, subject to mandatory workshop requirements. Require a documented pre-merge checklist and evidence for the exact proposed revision, and demonstrate a deliberately failing automated test followed by restoration to a passing state.
- **Approved approach:** Use the selected local test runners and repeatable PowerShell scripts for automated checks. A documented pre-merge checklist requires the applicable checks to pass on the exact proposed revision and retains commands, revision, results, and evidence. A failed required check blocks checklist approval until corrected and rerun. No hosted CI service or Actions workflow is used.
- **Boundary:** This changes only the execution and review method. Automated functional, API, security, and evaluation checks remain required. PRD metrics and configured blocking outcomes are preserved; pending evaluation thresholds remain pending. AC18 deployment rollback/health-check evidence remains separate.
- **Workshop review:** PRD §14.1 and the Implementation Plan call for evaluation, security, deployment, rollback, operating-runbook, and live-demo deliverables, including a deliberate failure/restoration demonstration. Those repository sources do not mandate a hosted CI provider or browser E2E evidence, and no standalone workshop rubric was present in the repository. This review is limited to repository materials; any separately issued mandatory workshop rubric remains controlling and must be reconciled before applicable capstone evidence closes.
- **Impacted requirements:** PRD F16, §14.1, AC17, §16, §17, and §18; related implementation and evaluation plans. AC18 remains separate.
- **Status:** Approved — local automated verification and documented pre-merge evidence replace hosted CI merge-gate execution for this capstone.
- **Confirmation date:** 22 November 2026

### PP-001 — Supporting tooling decisions

The Product Owner approved the following selections on 21 November 2026. Package families and compatibility baselines are approved; exact package releases must be resolved during project setup and recorded in lockfiles. Pin the uv executable and any non-package test images in project tooling setup when introduced. No patch versions are assumed here.

| Selection | Product Owner disposition | Evidence reviewed, alternatives, and trade-offs |
|---|---|---|
| Python environment and dependencies | **Approved:** CPython 3.12 with uv, `pyproject.toml`, and `uv.lock`. Pin the uv executable to a tested release in project tooling setup. | uv syncs a project from its lockfile ([uv docs](https://docs.astral.sh/uv/concepts/projects/sync/)). Alternatives: pip plus venv needs separate locking workflow; Poetry is established but adds a different toolchain. |
| SQLite ORM and migrations | **Approved:** SQLAlchemy 2.x and Alembic 1.x. | SQLAlchemy supports the built-in SQLite driver and connection-level foreign-key setup ([SQLite dialect](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)); Alembic supports SQLite batch migrations ([batch migrations](https://alembic.sqlalchemy.org/en/latest/batch.html)). Alternatives: raw `sqlite3` reduces dependencies but adds manual mapping/migration work; SQLModel adds a model abstraction. SQLite remains the only database. |
| Frontend routing, UI, and state | **Approved:** React Router 8.x, MUI 9.x, TanStack Query 5.x, React state/context for local state. Resolve exact React/Node and package releases compatibly at setup. | React Router documents nested routes ([routing](https://reactrouter.com/start/data/routing), [releases](https://reactrouter.com/changelog)); MUI publishes a stable major release schedule ([versions](https://mui.com/material-ui/getting-started/versions/)); TanStack Query handles server-state fetching/cache ([overview](https://tanstack.com/query/v5/docs/framework/react/overview)). Alternatives: manual routing and bespoke components increase maintenance; Redux adds broader state machinery not required for local state. |
| Worker and scheduling | **Approved:** one standard-library Python polling worker over SQLite-persisted jobs/outbox. PP-007 approves 5-second polling, 5-minute leases renewed every 60 seconds, and startup/every-60-second reconciliation. | Uses the approved database and one worker. APScheduler adds a dependency and does not replace durable job/outbox semantics; queue/broker systems are outside the approved architecture. |
| Backend and API tests | **Approved:** pytest and FastAPI `TestClient` (with its HTTPX dependency). | pytest provides reusable fixtures ([docs](https://docs.pytest.org/en/stable/)); FastAPI documents `TestClient` with pytest ([docs](https://fastapi.tiangolo.com/tutorial/testing/)). Backend authorization and API behavior remain tested at the server boundary. The Product Owner selected this pairing; stdlib unittest was not pursued. |
| Frontend tests | **Approved:** Vitest and React Testing Library; Playwright is rejected. | [Vitest](https://vitest.dev/guide/) provides the frontend test runner; [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/) tests rendered React DOM from user-facing interactions. The Product Owner selected this pairing; no separate browser E2E framework is selected, and no PRD criterion explicitly requires browser E2E automation. |
| Local check runner and pre-merge process | **Approved:** repeatable local PowerShell scripts plus a documented checklist and retained evidence. | [PowerShell scripts](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_scripts?view=powershell-7.6) provide a repeatable local command surface. Scripts will be introduced with the relevant implementation work; this documentation task creates no scripts. The checklist requires passing checks on the exact proposed revision and retained commands/results/evidence. Local execution does not provide automatic hosted merge enforcement. |
| Coverage reporting | **Open; intentionally not selected and not required to close PP-001 or start PP-010.** | No PRD or Definition of Done coverage percentage is specified. pytest-cov is an optional reporting plugin ([pytest docs](https://pytest.org/en/stable/how-to/plugins.html)); adding it or a numeric gate is deferred until a ticket demonstrates the need. |
| Security checks | **Approved:** Bandit, pip-audit, and npm audit. | Bandit checks common Python code issues ([docs](https://bandit.readthedocs.io/en/latest/)); pip-audit checks Python dependencies ([project](https://github.com/pypa/pip-audit)); npm audit checks the npm dependency tree ([docs](https://docs.npmjs.com/cli/v11/commands/npm-audit)). These supplement, not replace, security acceptance tests. |
| Later-stage security and performance | **Approved:** OWASP ZAP Baseline and Locust, for later-stage testing only. | ZAP Baseline performs a short passive scan ([docs](https://www.zaproxy.org/docs/docker/baseline-scan/)); Locust defines load scenarios in Python ([docs](https://docs.locust.io/en/stable/)). Alternatives include Semgrep for broader static rules and k6 for JS-based load scenarios; they add policy/runtime choices. Use ZAP/Locust only against local synthetic data or an explicitly approved non-production target. |
| Hosted CI service and merge-gate mode | **Resolved:** No hosted CI service or GitHub Actions. The Product Owner approved local automated verification and documented pre-merge evidence through PRD change RC-01. | No workflow configuration is required. Preserve approved checks, exact-revision checklist evidence, and the deliberately failing automated test followed by restoration to a passing state. This does not change pending metric thresholds or other product/security gates. |

These decisions do not approve deployment, external service provisioning, or exact package patch versions. No hosted CI workflow is used. The later-stage test tools do not enable detection, incident-producing results, or notifications.

### ARC-07 — Atomic incident state and notification outbox

- **Description:** Require durable notification intent to stay consistent with an incident state change that triggers it.
- **Approved approach:** Whenever an incident state change requires a notification, persist the incident state change and its associated notification outbox event in the same atomic SQLite transaction. If either local database operation fails, neither may commit. Keep all OpenAI and email-provider calls outside database transactions; persist provider outcomes in a separate short transaction after the call. Provider availability must not suppress qualifying incident creation or durable outbox intent. An expired SENDING claim with no started attempt returns to QUEUED; an abandoned IN_PROGRESS delivery attempt becomes OUTCOME_UNKNOWN. Do not automatically resend an uncertain outcome unless provider verification or a separately approved policy permits it. Do not claim exactly-once external email delivery.
- **Reasoning and trade-offs:** Atomic local persistence prevents an incident change from committing without its required durable notification event, or an event from committing without the associated incident change. The short SQLite write transaction can contend with API and worker writes, so it must not include network I/O. Local atomicity cannot determine whether a provider accepted a request when its response is uncertain.
- **Impacted specifications:** PRD §§9.4, 10.3, 11; `docs/TECH_STACK.md`; `docs/ARCHITECTURE.md`; `ALERT_SPEC.md`, `DATA_MODEL.md`, and `API_SPEC.yaml` for notification recovery and retry contracts.
- **Pending provider details:** Provider verification capability and recovery after a verified outcome remain provider-specific dependencies. Uncertain outcomes are never automatically resent under this approval.
- **Status:** Approved
- **Confirmation date:** 20 November 2026
- **Clarification date:** 21 November 2026 (expired-lease and uncertain-outcome recovery)

### ARC-08 — Role-visible readiness projection

- **Description:** Provide Admin and Business User roles a coarse, read-only status that distinguishes detection activation and coverage, processing degradation, automatic-notification activation, manual-confirmation availability, and email-provider availability.
- **Options:** (1) Expose only Admin operations data and leave Business Users unable to distinguish readiness states; (2) add an authenticated read-only projection with coarse states and no configuration/provider details; (3) infer readiness in the browser from job counts and incident results.
- **Approved approach:** Add authenticated, read-only `GET /readiness` for Admin and Business User roles. Return separate coarse detection activation and coverage states, processing state, automatic-notification activation, manual-confirmation availability, and email-provider availability. Use `UNKNOWN` whenever readiness cannot be established. Inactive detection is not evidence of zero defects. Do not return provider identity, recipients, routes, Admin-only configuration, credentials, error payloads, or secrets. The projection is informational only; every command continues to enforce authorization and prerequisites server-side. Exact degradation thresholds and provider-health assessment parameters remain pending for the operations specification.
- **Reasoning and trade-offs:** This lets both roles understand inactive detection, insufficient coverage, processing degradation, and provider unavailability without exposing Admin-only operations data. Coarse states avoid a second operations console; assessment thresholds remain an operations decision.
- **Impacted specifications:** `docs/UI_SPEC.md`, `docs/API_SPEC.yaml`, and `docs/DATA_MODEL.md`.
- **Status:** Approved
- **Confirmation date:** 21 November 2026

## Security

### SEC-01 — Authentication, session handling, and initial Admin provisioning

- **Description:** Select secure authentication and define password, session, bootstrap, recovery, and security-event controls for the two MVP roles.
- **Options:** (1) Secure email/password with server-side sessions as D11 proposes; (2) development-only authentication provider; (3) external SSO.
- **Approved approach:** Use secure email/password authentication with server-side sessions for Admin and Business User roles. Hash passwords with maintained argon2-cffi Argon2id using 19 MiB memory, 2 iterations, and parallelism 1; benchmark implementation latency and increase cost if practical, never silently lower it. Rehash on successful login when stored parameters are below the approved parameters. Normalize input to NFC before policy checks and hashing. Require 15-128 Unicode code points; allow spaces and Unicode; reject overlength without truncation; block common/compromised passwords; impose no composition rules or periodic expiry.
  Use 30-minute idle and 8-hour absolute session expiry, concurrent sessions allowed, server-side revocation, and opaque bearer tokens stored only as one-way hashes. Rotate session and CSRF tokens at login and after password reset/change. Set the host-only __Host-productpulse_session cookie with Secure, HttpOnly, SameSite=Lax, Path=/, no Domain, and expiry no later than the remaining idle/absolute lifetime.
  Provide unauthenticated GET /auth/csrf: issue a cryptographically random, HttpOnly, Secure, SameSite=Strict, Path=/, host-only pre-login cookie for 10 minutes and return its matching CSRF value in JSON for memory-only browser use. Require the matching cookie/header, exact same-origin Origin (use Referer only when Origin is absent), and clear the pre-login cookie after login. Bind and rotate the authenticated CSRF value to the session; require it on every cookie-authenticated mutation. Production deployment is same-origin; cross-origin browser access is not enabled by this decision.
  Provision the first Admin with a one-time protected setup command that fails closed if an Admin already exists and reads the password from a secure hidden prompt, never argv, environment, shell history, or logs. Admin-created accounts use only ADMIN/BUSINESS_USER roles; normalize email by trimming outer ASCII whitespace, applying NFC, converting the domain to lowercase IDNA ASCII, then case-folding the full address for email_normalized. Preserve the trimmed entered address and its case for display; do not rewrite plus/dot aliases.
  Deactivate rather than delete or reactivate accounts, revoking all active sessions atomically. Admin-assisted recovery is the only recovery path: an Admin sets a compliant temporary password, all target sessions are revoked, and the account must change it before normal use. The Admin hands the temporary credential directly to the verified user in person outside ProductPulse; do not send email or imply app delivery. Successful password change invalidates all sessions and establishes a fresh session with new CSRF state. Audit successful sign-in/out, account create/deactivate/reset/change, session revocation, and authorization denials in append-only safe audit events. Failed-sign-in and throttle detail uses a restricted redacted security log; neither channel records passwords, email addresses, source IPs, session/CSRF/reset tokens, raw request bodies, or provider secrets.
  Throttle by normalized candidate account: 10 failed attempts in any rolling 15-minute window starts a 15-minute cooldown; also limit 60 login attempts per source IP in any rolling 15-minute window. Return generic login failures and generic 429 responses with Retry-After; apply these limits only to login.
- **Reasoning and trade-offs:** Argon2id gives a modern memory-hard password hash and versioned parameters support upgrades, at the cost of CPU/memory per login. The length-only policy and blocklist reduce common weak choices without composition-rule churn; a local blocklist adds maintenance. Idle expiry limits unattended exposure while the absolute cap bounds long-lived sessions; concurrent sessions simplify multi-device use but require reliable revocation. CSRF bootstrap and same-origin deployment make browser trust explicit but require same-origin hosting. Direct verified handoff avoids unauthorized email delivery but requires an out-of-band in-person process. Account cooldowns slow credential guessing but can temporarily lock out a targeted account; the IP ceiling constrains that abuse. Safe audit detail improves investigation while restricting sensitive login diagnostics.
- **Impacted specifications:** PRD §§3.2, 6.1, 12-13, 19 D11; docs/TECH_STACK.md; docs/SECURITY.md; docs/API_SPEC.yaml; docs/DATA_MODEL.md; docs/UI_SPEC.md; docs/IMPLEMENTATION_PLAN.md; PP-003 and dependent PP-012/PP-029.
- **Status:** Approved
- **Confirmation date:** 22 November 2026
### SEC-02 — Authorization scope and user lifecycle

- **Description:** Specify server-side permissions for every route and clarify user provisioning, deactivation, email identity, and recovery scope.
- **Options:** (1) Implement exactly the Admin/Business User permissions in the PRD with single-retailer access; (2) add per-product/supplier scopes; (3) introduce Viewer or granular permissions in MVP.
- **Approved approach:** Implement only ADMIN and BUSINESS_USER roles with single-retailer data access and backend authorization on every protected route; no Viewer or multi-tenant scopes. Admins create users with compliant temporary passwords and users must change them before normal use; Admins can reset a password through the approved temporary-password handoff. Email identity uses the SEC-01 canonicalization rule and normalized unique key. Deactivation is non-destructive and atomically revokes active sessions; deletion and reactivation remain outside MVP.
- **Reasoning and trade-offs:** This preserves the specified RBAC while avoiding unrequested complexity. Canonical case-insensitive identity avoids duplicate accounts but can collapse addresses differing only by local-part case. Temporary credentials require direct user verification and handoff; this avoids an unapproved email recovery channel. It does not provide data partitioning for future tenants or teams.
- **Impacted specifications:** PRD §§3.1-3.2, 6, 12-13, 15 AC01/AC13; docs/SECURITY.md; docs/API_SPEC.yaml; docs/DATA_MODEL.md; docs/UI_SPEC.md; PP-003 and dependent PP-012/PP-029.
- **Status:** Approved
- **Confirmation date:** 22 November 2026
### SEC-03 — Approved recipient controls and manual-send boundary

- **Description:** Define the approved recipient directory, editable manual-message content, and how the application prevents unapproved or accidental sends.
- **Options:** (1) Sandbox-only approved internal recipients; (2) real internal recipients with explicit authorization; (3) arbitrary recipients entered by users.
- **Approved approach:** Use a fixed Admin-managed sandbox directory; no arbitrary addresses, no supplier recipients, and no real sending in MVP. Keep preview plus explicit confirmation, incident-scoped content, server-side recipient validation, idempotency key, and full audit as required by the PRD. Any real sending requires a separate explicit approval and updated security review.
- **Reasoning and trade-offs:** This is the lowest-risk end-to-end demo and aligns with the non-production boundary. It limits realistic delivery testing and requires the sandbox directory to be configured.
- **Impacted specifications:** PRD §§3.2, 6.8, 9.4, 10, 13.2, 15 AC13–AC14, 19 D06; future Notification and Security specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### SEC-04 — Feedback text in logs, telemetry, and exported files

- **Description:** Set handling rules for source text and model excerpts outside the source-record store, including logs, traces, and exports.
- **Options:** (1) Copy full feedback into operational logs; (2) redact or omit raw text from telemetry and keep it only in governed source records; (3) omit feedback text from all detail views.
- **Approved approach:** Keep original text only where required for source evidence and authorized drill-down; redact it from logs/traces and avoid including personal details in email content. Escape formula-leading values in exports as required. Prefer synthetic data for the capstone dataset.
- **Reasoning and trade-offs:** This follows the PRD’s redaction and no-PII constraints while preserving investigation evidence. Diagnostic logs will carry less text context.
- **Impacted specifications:** PRD §§6.4–6.8, 7.3, 10, 13.2; future Security, Privacy, and Export specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

## Operations

### OPS-01 — Non-production deployment target and topology

- **Description:** Choose where and how the application runs for the required non-production deployment, health checks, and rollback demonstration.
- **Options:** (1) One Linux VM running Docker Compose as a preferred proposed topology; (2) another single-instance non-production topology that satisfies the confirmed SQLite storage constraints; (3) local-only demonstration; (4) separate environments for web, worker, and data services across multiple providers.
- **Required deployment constraint (confirmed 20 November 2026):** Run one active application instance and provide persistent local storage containing the SQLite database file, accessible to both the API and the one worker and retained across restarts/redeployments. Do not assume a network filesystem or multiple application instances.
- **Preferred proposed topology (not approved):** One Linux VM running Docker Compose, with the API and one background worker sharing the same persistent local SQLite storage. The deployment must support protected secrets, health checks, logs, backups, and rollback. Do not create production or multi-region infrastructure for this capstone.
- **Reasoning and trade-offs:** A single VM and Compose are a compact proposed shape that can honor SQLite's single-writer/local-file operating model. No cloud hosting provider is selected or approved; provider suitability, persistent-volume behavior, account/access, and cost remain to be verified.
- **Impacted specifications:** PRD §§13.1–13.3, 15 AC18, 16–18; future Deployment and Runbook specifications.
- **Status:** Proposed
- **Confirmation date:** 20 November 2026

### OPS-02 — Retry budgets, failure recovery, and reconciliation schedule

- **Description:** Set bounded retry counts/backoff, dead-letter visibility, and the cadence for reconciliation of jobs and missed detection updates.
- **Options:** (1) Retry indefinitely; (2) use bounded automatic retries then surface a terminal failure for Admin recovery; (3) require manual retry after every failure.
- **Approved approach:** Use bounded automatic retries for transient OpenAI/mail errors, persist terminal failures for Admin visibility and retry, and schedule reconciliation at a documented cadence. Keep retries idempotent and avoid retrying permanent validation errors. Define an Admin-only notification retry operation for eligible known-failed events; it preserves the original notification/event identity and audit history, and each new provider call has a new numbered delivery attempt. OUTCOME_UNKNOWN is not retryable without provider verification or an approved policy.
- **Reasoning and trade-offs:** Bounded retries protect cost and avoid stuck work while maintaining recovery paths. The exact retry budget needs provider behavior and operational tests.
- **Impacted specifications:** PRD §§8.1, 9.1, 10.3, 13.3, 15 AC04/AC16; Job Processing and Operations specifications; `ALERT_SPEC.md` and the Admin retry operation in `API_SPEC.yaml`.
- **Status:** Approved
- **Confirmation date:** 20 November 2026
- **Clarification date:** 21 November 2026 (Admin-only notification retry and attempt identity)
- **Clarification date:** 22 November 2026 (Product Owner): For the durable `CLASSIFICATION` work item created by PP-014 when confirming an accepted feedback import, snapshot `max_attempts = 3`. This is at most three claimed attempts total, including the initial attempt and up to two additional claimed attempts. PP-014 may persist the queued work item only; it does not implement retry execution, backoff, leases, worker processing, or OpenAI calls.
- **PP-007 clarification (22 November 2026):** Use the worker retry-delay sequence 5 seconds, 15 seconds, then 45 seconds between eligible attempts. The sequence does not set a job-type retry budget. The PP-014 classification item remains capped at 3 total claims, so it uses only the first two delays. Other job-type attempt budgets are not assigned a default. Provider-specific notification retry limits, routing, sink selection, and external idempotency remain gated under PP-008; `OUTCOME_UNKNOWN` is not automatically resent.

### OPS-03 — Data retention, backup, and recovery expectations

- **Description:** Define retention for source records, audit history, notification content, and backups, plus what rollback restores.
- **Options:** (1) Keep all synthetic capstone data through the evaluation/demo and allow a documented reset; (2) define fixed retention and automated backups; (3) treat the environment as disposable and rely only on reseeding.
- **Approved approach:** Keep synthetic dataset and audit evidence for the capstone period. Retain uploaded CSVs, previews, row reasons, and generated rejection reports through the capstone period with no automatic per-artifact expiry; remove them only through the documented synthetic reset/reseed procedure after a consistent backup and reference/audit checks. Document a SQLite-consistent backup and restore procedure that captures/restores the SQLite database and all referenced file artifacts together as one coherent recovery set (OPS-06); stop API/worker writes and artifact mutations while taking the set and before file replacement or reset, verify database integrity and foreign-key relationships before restarting, and provide a documented reset/reseed procedure. Before every migration and reset/reseed, create a consistent development backup. Use Python's SQLite backup API with the artifact set quiesced. Do not claim production recovery guarantees. Confirm any retention/deletion requirement before using non-synthetic public data.
- **Reasoning and trade-offs:** This is practical for a non-production capstone and supports repeatable demos. It is not a production backup policy; loss of demo history may require reseeding. Deployment-specific periodic backup cadence and backup-set retention remain unspecified.
- **Impacted specifications:** PRD §§7.4, 11, 13.2–13.3, 15 AC18; future Data Lifecycle and Operations Runbook specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### OPS-04 — Performance and freshness targets

- **Description:** Confirm whether the proposed dashboard p95 and post-classification display targets are acceptance gates or measurement goals.
- **Options:** (1) Treat both as hard release gates; (2) use them as measured targets and report results; (3) replace them after a baseline measurement.
- **Approved approach:** Treat the PRD’s ≤3-second dashboard p95 on 10,000 records and ≤60-second display after successful classification as provisional measurement targets, not promises about provider queue time. Measure event-to-display, ingestion-to-display, and classification-to-display separately, including API/worker write contention. Confirm before turning either into a merge blocker.
- **Reasoning and trade-offs:** This preserves the PRD’s performance intent without confusing UI polling with end-to-end processing. SQLite write contention and a small test environment may affect measurements; the targets are unchanged and must be reported honestly.
- **Impacted specifications:** PRD §§6.2, 13.1, 14, 16; future Performance and Evaluation specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### OPS-05 — Operational visibility and solo-developer runbook

- **Description:** Choose the minimum operational views and documented procedures needed to support the capstone without a staffed operations team.
- **Options:** (1) Expose only service health; (2) expose health plus job/queue age, failure counts, model cost, notification failures, and freshness; (3) build a full operations dashboard.
- **Approved approach:** Implement the PRD’s listed health and processing indicators in the Admin Console and dashboard summary, with a concise runbook for failed jobs, stuck work, notification errors, cost review, reset, and rollback. Avoid a separate operations product surface.
- **Reasoning and trade-offs:** It covers required failure visibility with a small surface area. Troubleshooting remains partly manual and depends on clear logs and identifiers.
- **Impacted specifications:** PRD §§6.2, 6.7, 13.1–13.3, 16–18; future Operations and Runbook specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### OPS-06 — Local artifact storage and recovery-set consistency

- **Description:** Define storage and integrity requirements for uploaded CSV files and generated rejection reports.
- **Options:** (1) Store file contents as SQLite BLOBs; (2) store file contents in a protected local filesystem directory and keep opaque identifiers and metadata in SQLite; (3) use a separate object-storage service.
- **Approved approach:** Store uploaded CSV bytes and generated rejection-report bytes in a protected local filesystem directory on persistent local storage accessible to the API and background worker. Store only opaque artifact identifiers and metadata in SQLite, never the file contents as BLOBs. Keep files outside public/static delivery and out of Git. Resolve identifiers only on the backend using a server-controlled mapping beneath the configured storage root; do not accept client-supplied paths. Preserve file hashes, sizes, uploader/generator identity when available, timestamps, immutable preview/hash binding, and audit lineage. Publish files atomically before committing SQLite references; on database failure remove the newly published file, and reconcile unreferenced orphan files without deleting referenced artifacts. Backups and restores must treat the SQLite database and referenced artifact files as one consistent recovery set.
- **Retention boundary:** OPS-03 approves retaining artifacts through the capstone period without automatic per-artifact expiry. The approval of orphan cleanup does not authorize deletion of referenced artifacts before the preview/rejection workflow and approved synthetic reset procedure permit it.
- **Reasoning and trade-offs:** This keeps large file contents out of SQLite and its WAL while preserving durable preview and rejection-report access. Filesystem and database writes cannot share one transaction, so publication ordering and orphan reconciliation are required.
- **Impacted specifications:** `docs/DATA_MODEL.md`, `docs/TECH_STACK.md`, `docs/ARCHITECTURE.md`, future `API_SPEC.yaml`, and the Operations/Backup Runbook.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### PP-007 — Product Owner disposition (22 November 2026)

- **Status:** Done — operational policies and approved development parameters are recorded below and aligned in the affected specifications. Deployment-specific backup cadence and backup retention are explicitly deferred; those choices remain gated before deployment.
- **SQLite contention:** Set a 5-second per-connection busy timeout and allow 2 additional retries after rollback for a retryable `SQLITE_BUSY`, using only an idempotent database unit.
- **Worker operation:** Keep one standard-library polling worker and one shared SQLite database. Poll jobs/outbox every 5 seconds; use a 5-minute lease with renewal every 60 seconds during long provider calls; reject writes from stale lease owners; run reconciliation at startup and every 60 seconds while running. Reconciliation finalizes expired claims as abandoned and clears the old lease. Work without an approved attempt budget is not eligible for worker claim or automatic replay. Schedule another attempt only when the outcome is safe to retry and the work type has an approved attempt budget; use the next eligible 5/15/45-second delay. Reconcile uncertain provider submissions by their owning contract before resubmission. Exhausted approved budgets remain terminal failures for Admin visibility/recovery.
- **Retry policy:** Use backoff delays of 5, 15, and 45 seconds between eligible retries. Preserve `max_attempts=3` total for PP-014-created `CLASSIFICATION` work items; only the first two delays can be used under that cap. Do not infer max-attempt budgets for other job types. Retry only known transient failures; terminal failures remain visible. Provider-specific notification retry limits remain pending under PP-008, and `OUTCOME_UNKNOWN` must not be automatically resent.
- **Artifacts and development backups:** Retain synthetic upload, preview, rejection-report, and audit artifacts through the capstone period without automatic per-artifact expiry. Clean them only through a documented synthetic reset/reseed after backup and reference/audit checks. Before every migration and reset/reseed, take a coherent SQLite-plus-referenced-artifact backup using Python's SQLite backup API while database writes and artifact mutations are quiesced. Restore checks include database integrity, foreign keys, referenced artifact presence, and hash verification.
- **Deferred operations:** No deployment-specific periodic backup cadence or backup retention period is approved. Routing, sink selection, provider-specific notification retry limits, and external idempotency remain under PP-008. ARC-08 readiness/degradation thresholds and provider-health parameters remain open.
- **Operational visibility:** Use structured, redacted logs with safe request/job/incident identifiers and action-oriented error categories. Use the existing health endpoint, Admin operations view, dashboard freshness indicators, and concise runbook; do not add a separate operations product. Keep raw feedback, secrets, tokens, message content, provider payloads, filesystem paths, and raw exception text out of general-purpose logs.
- **Affected specifications and readiness notes:** Architecture v1.5, Tech Stack v1.2.0, Data Model v1.5.2, API_SPEC.yaml v1.5.2, Alert Specification v0.3 (still Draft), UI Specification v0.4.1, and Implementation Plan v1.0. PP-010, PP-014, PP-018, PP-034, PP-035, PP-015, PP-036, PP-053, and PP-054 readiness/closure notes are reconciled with the approved and deferred gates.
- **Implementation boundary:** This disposition does not authorize application code, migrations, deployment, detection activation, incident-producing current results, or notification activation. PP-018 may be rechecked for Implementation Ready status; it still requires a separately approved bounded implementation milestone.

## Evaluation

### EV-01 — Held-out dataset size and scenario sufficiency

- **Description:** Set final held-out record and planted-episode counts sufficient to report stable classification and detection metrics.
- **Options:** (1) Use a fixed count selected before evaluation; (2) base the count on a documented minimum per class and episode type; (3) report the available set with uncertainty and do not claim a stable target where counts are small.
- **Approved methodology:** Lock the held-out set before final tuning; report counts, uncertainty, false positives, misses, and class imbalance; assess minimum representation during development.
- **Pending parameters:** Final held-out record and planted-episode counts/minimums, including adequate per-class and per-scenario representation, remain to be set before the dataset is locked.
- **Reasoning and trade-offs:** This supports honest evaluation and prevents tuning against held-out cases. Creating enough labelled scenarios takes capstone time.
- **Impacted specifications:** PRD §§7.4, 14–15 AC17, 19 D02/D19; future Evaluation Dataset and Plan.
- **Status:** Pending Calibration
- **Confirmation date:** 20 November 2026
### EV-02 — Classification gates by class

- **Description:** Set class-specific precision/recall or regression thresholds for the taxonomy without inventing an unsupported aggregate accuracy target.
- **Options:** (1) Use one macro-accuracy threshold; (2) define per-class thresholds from development results and class prevalence; (3) report all metrics but block only schema/integrity/security failures.
- **Recommended option:** Follow the PRD: derive class-specific thresholds from development evaluation and class prevalence before examining held-out results; report per-class precision/recall and confusion matrix; do not promise a macro-accuracy value without evidence.
- **Reasoning and trade-offs:** This matches the PRD and accounts for class imbalance. It requires enough labelled examples and a documented regression policy.
- **Impacted specifications:** PRD §§8, 14–15 AC17, 19 D19; future AI Evaluation Plan and local verification evidence requirements.
- **Status:** Pending Calibration
- **Confirmation date:** 20 November 2026

### EV-03 — Planted-episode recall gate

- **Description:** Confirm the provisional ≥90% held-out planted-episode recall gate and its denominator.
- **Options:** (1) Keep ≥90%; (2) set another threshold after development scenarios; (3) report detection recall without a numeric release gate if the held-out set is too small.
- **Recommended option:** Keep ≥90% as a provisional target only if the locked scenario count can support it; calculate detected/total episodes, report false positives and missed episodes, and do not tune after locking. Otherwise seek product-owner confirmation for a revised gate before final evaluation.
- **Reasoning and trade-offs:** The gate is already in the PRD but explicitly provisional. Small scenario counts make percentage changes unstable.
- **Impacted specifications:** PRD §§14–15 AC09/AC17, 19 D19 and 19.1; future Detection Evaluation and local verification evidence requirements.
- **Status:** Pending Calibration
- **Confirmation date:** 20 November 2026

### EV-04 — Lead-time baseline method

- **Description:** Choose the documented sentiment/negative-review comparator used to measure detection lead time on the identical event-time stream.
- **Options:** (1) A fixed sentiment-score threshold; (2) a fixed negative-review threshold; (3) report detection performance without a lead-time comparison.
- **Approved approach:** Select one simple, reproducible comparator during development, document its threshold and data requirements, then freeze it before held-out evaluation and apply it to the identical event-time stream. Do not build a user-facing sentiment feature solely for this comparison.
- **Reasoning and trade-offs:** A fixed comparator makes lead-time claims auditable without expanding product scope. Its method can affect the claimed improvement and must be selected before seeing held-out results.
- **Impacted specifications:** PRD §§2.2, 14, 18; future Evaluation Plan.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

### EV-05 — Cost reporting and cost gate

- **Description:** Decide whether model cost per 1,000 records is a report-only metric or a release gate, and set a budget if gated.
- **Options:** (1) Report measured cost only; (2) set a budget after development runs and block above it; (3) defer cost tracking.
- **Approved approach:** Track and report cost per 1,000 records, including retries and Batch versus incremental work. Establish a cost gate only after representative development runs and explicit budget confirmation; no spend limit is approved here.
- **Reasoning and trade-offs:** Measurement informs model selection and operational choices. A gate requires a confirmed budget and stable evaluation conditions.
- **Impacted specifications:** PRD §§6.7, 8.1, 14, 16, 18; future AI Evaluation and Operations specifications.
- **Status:** Approved
- **Confirmation date:** 20 November 2026

## Architecture approval blockers and downstream specification decisions

The high-level approaches for ARC-01 through ARC-08 are approved at their recorded scopes, including ARC-06 local verification. Architecture v1.5 is Approved. API_SPEC.yaml v1.5.2, UI_SPEC.md v0.4.1, and DATA_MODEL.md v1.5.2 are Approved — Design Baselines subject to documented conditions; API v1.5.1 and Data Model v1.5.1 were previous baselines. SEC-01/02, DAI-01/02/08, and PB-06 are Approved; OPS-06 artifact storage and the OPS-03 capstone artifact-retention policy are Approved; DAI-06 methodology is confirmed but its parameters remain Pending Calibration; OPS-01 deployment suitability remains gated until the provider is verified.

### Remaining architecture-approval blockers

None identified for approval of the logical architecture. SEC-01/02 define the approved authentication/account contract; DAI-01/02/08 define the approved CSV parser/mapping/conflict contract; PB-06 defines unresolved-linkage behavior. DAI-06 methodology is approved while its exact coverage parameters remain open for DETECTION_SPEC.md. API_SPEC.yaml v1.5.2, UI_SPEC.md v0.4.1, and DATA_MODEL.md v1.5.2 are conditional design baselines with remaining implementation dependencies. ARC-08 readiness assessment parameters remain for the operations specification. OPS-01 provider suitability is required before deployment approval.

### Proposed deployment choice (not approved)

- **OPS-01:** A single Linux VM running Docker Compose is the preferred proposed topology. The API and one worker must share persistent local SQLite storage. The cloud hosting provider is not selected or approved.
- Before deployment, verify the selected provider supports one active instance, persistent local storage shared by API and worker, protected secrets, health checks, logs, backups, and rollback. Keep OPS-01 Proposed until that provider and suitability are confirmed.

### Pending calibration parameters

- **DAI-06:** Exact source and classification coverage scope, completeness criteria, and calibration parameters remain Pending Calibration. Do not interpret missing coverage as zero; do not send automatic warnings when required baseline coverage is insufficient. Specify the parameters in `DETECTION_SPEC.md`.
- **PB-01:** Detection thresholds and minimum counts remain Pending Calibration.
- **EV-01/EV-02/EV-03:** Held-out dataset size, class-specific gates, and planted-episode recall remain Pending Calibration.

### Downstream specification decisions

- **ARC-02 — REST request/response contracts:** API_SPEC.yaml v1.5.2 is Approved — Design Baseline subject to remaining implementation dependencies; v1.5.1 was the previous version. It incorporates the approved authentication, readiness, CSV parser/mapping/conflict, retry-eligibility, filter-alignment, PP-014 queue snapshot, and PP-007 operational parameters. Security, other route rate limits, and notification-routing choices remain assigned to their existing specifications.
- **ARC-03 — ORM and migration tooling:** SQLAlchemy 2.x and Alembic 1.x were approved under PP-001 on 21 November 2026. Exact compatible releases are recorded in `uv.lock` during project setup.
- **ARC-04 — SQLite concurrency and recovery details:** PP-007 approves the 5-second per-connection busy timeout, 2 additional rolled-back `SQLITE_BUSY` retries, one-item atomic claim, 5-minute leases, 60-second renewals, 5-second polling, and 60-second reconciliation. Stale-owner writes are rejected; provider calls remain outside transactions.
- **OPS-02/OPS-03 — Retry and backup parameters:** PP-007 approves 5/15/45-second worker retry delays and `max_attempts=3` total for PP-014-created classification items. Other work-type attempt budgets and provider-specific notification retry limits remain unresolved (notification limits under PP-008). Capstone artifact retention and pre-migration/pre-reset development backups are approved; deployment-specific periodic backup cadence and backup retention remain open.
- **DAI-05 — OpenAI model identifier:** evaluate support for both APIs and the strict output contract before selecting a model.
- **ARC-05 — Email sink:** select the capture sink. ARC-06 local verification and pre-merge evidence are approved; no hosted CI service is used.
- **SEC-01/02 — Authentication and account details:** Approved 22 November 2026 and recorded in SECURITY.md, API_SPEC.yaml, DATA_MODEL.md, UI_SPEC.md, and TECH_STACK.md. Implementation remains subject to ticket scope and verification gates.
- **OPS-01 — Deployment provider:** the Linux VM/Docker Compose topology remains Proposed; select and verify a provider in the Deployment and Runbook specification before deployment.
- **DAI-06 — Coverage parameters:** methodology is Approved; exact source/classification coverage scope, completeness criteria, and calibration parameters belong in `DETECTION_SPEC.md` and remain Pending Calibration.
- **PB-01/PB-04 — Detection calibration and notification edge cases:** threshold values and minimum counts are Pending Calibration; severity decreases, re-crossings, and recurrence details need a downstream notification specification.
- **PB-05 — Metric definitions:** creating a shared glossary is Approved; metric definitions are not approved and remain for the glossary/dashboard specifications.
- **ARC-07 — Provider-send uncertainty and external idempotency:** local incident/outbox atomicity and conservative recovery are Approved: expired SENDING without a started attempt returns to QUEUED; abandoned IN_PROGRESS becomes OUTCOME_UNKNOWN and is not automatically resent absent provider verification or an approved policy. Provider verification capability and external idempotency remain open.
- **ARC-08 — Role-visible readiness projection:** Approved; exact degradation thresholds and provider-health assessment parameters remain pending for the operations specification. The endpoint remains read-only, uses UNKNOWN when readiness cannot be established, and omits Admin configuration and secrets. Approval does not activate detection or notifications.
- **DAI-01/02/08 — CSV parsing, duplicate/conflict, and mapping contracts:** Approved with PP-004 on 22 November 2026. The byte/row limits, parser versions, UTF-8/BOM, timestamp and field rules, exact identifiers, duplicate/conflict semantics, preview idempotency/hash binding, and safe rejection-report contract are recorded in the API, Security, Data Model, and UI specifications. OPS-03 now retains associated synthetic artifacts through the capstone period; no automatic per-artifact expiry is defined.
- **EV-01/EV-02/EV-03 — Evaluation parameters:** held-out size, class-specific gates, and planted-episode recall remain Pending Calibration.
- **EV-04/EV-05 — Evaluation details:** choose and freeze the lead-time comparator during development; no cost gate is approved without explicit budget confirmation.
- **Test tooling:** Backend/API pytest with FastAPI TestClient, frontend Vitest with React Testing Library, and repeatable local PowerShell check scripts with a documented pre-merge checklist are Approved. GitHub Actions and Playwright are not used; no browser E2E framework is selected. DATA_MODEL.md v1.5.2 is the current Approved — Design Baseline, subject to documented conditions; v1.5.1 was the previous baseline. Remaining operational gates are other work-type attempt budgets, provider-specific notification policies, ARC-08 readiness thresholds, and deployment-specific backup cadence/retention.

The remaining calibration items **DAI-06 coverage parameters, EV-01 dataset-size parameters, EV-02 class-specific gates, and EV-03 planted-episode recall** do not prevent approval of the logical architecture; they must be resolved in their downstream detection/evaluation specifications before implementation or final evaluation depends on them. EV-01/EV-02/EV-03 still block final evaluation-plan approval. OPS-01 provider selection and suitability verification remain prerequisites for deployment approval, not logical-architecture approval. Remaining operational decisions are provider-specific notification behavior, other work-type retry budgets, ARC-08 readiness thresholds, and deployment-specific backup cadence/retention.

## Approval record

**Confirmation dates:** 20 and 21 November 2026.

On 20 November 2026, the product owner explicitly selected SQLite as the sole primary relational database for the MVP and confirmed SQLite-persisted job/outbox state with one separate worker. This updates ARC-03 and ARC-04 and adds the persistent single-instance storage constraint under OPS-01. Later confirmation approved SEC-01 and PB-06, approved the DAI-06 methodology while leaving its parameters Pending Calibration, recorded a Linux VM/Docker Compose preference under OPS-01 without selecting a provider, and approved OPS-06's protected local filesystem artifact storage and joint database/artifact recovery-set requirement. At that point SQLAlchemy 2.x, Alembic, deployment provider, artifact retention/expiry, and SQLite concurrency/recovery parameters remained unresolved; PP-001 now resolves only the ORM and migration-tool selections.

The following approaches were explicitly approved on that date: PB-02 through PB-08 (PB-05 covers glossary creation only), DAI-01 through DAI-05, ARC-01 through ARC-07, SEC-01 through SEC-04, OPS-02 through OPS-06, EV-04, and EV-05. PB-06's approved scope is product-level analytics for valid product identities, with no product-only incidents or automatic notifications from unresolved-link records. OPS-06 approves protected local filesystem storage for uploaded CSVs and generated rejection reports, SQLite metadata-only references, secure backend resolution, atomic publication/orphan handling, and joint database/file recovery sets; artifact retention/expiry remains open under OPS-03. ARC-01 specifies Recharts.

EV-01's evaluation methodology was approved on 20 November 2026; its dataset-size and minimum-representation parameters remain Pending Calibration. DAI-06's coverage methodology is approved, while its exact granularity, completeness criteria, and calibration parameters remain Pending Calibration alongside PB-01, EV-02, and EV-03. OPS-01 remains Proposed until a hosting provider is selected and its suitability is verified. No other decision status is changed by this confirmation.

The PRD remains the product-requirements source of truth. These approvals do not relax or replace its explicit requirements. At the prior register revision, Architecture v1.3 and API_SPEC.yaml v1.1.0 were Approved; Data Model v1.1 was the last Approved baseline while v1.2 was a Draft update. This register update does not authorize application code, migrations, or tickets. Other than PB-09 recorded below, no other decision status changed in that update.

On 21 November 2026, the user approved DAI-07's explicit import mode and automatic classification dispatch, fixed PB-04's same-severity cooldown at 86,400 seconds with no MVP override while preserving escalation bypass, and approved `API_SPEC.yaml` v1.0.0. The user then approved the DAI-03 outcome mapping, DAI-07 Batch correlation/recovery refinement, and `DATA_MODEL.md` v1.1 updates reflected in this register. Those confirmations did not resolve other Pending Calibration, Proposed, or Open items.

At the 21 November 2026 disposition, before the later RC-01 change, the Product Owner approved PP-001's Python 3.12/uv, SQLAlchemy/Alembic, React Router/MUI/TanStack Query, React local state/context, standard-library SQLite polling worker, pytest/FastAPI TestClient for backend/API tests, Vitest/React Testing Library for frontend tests, repeatable local PowerShell check scripts, Bandit/pip-audit/npm audit, and later-stage ZAP Baseline/Locust selections. The Product Owner explicitly rejected GitHub Actions and Playwright. Compatible stable package releases are to be resolved at project setup and recorded in lockfiles. PRD F16, §14.1, and AC17 still required CI merge gates and fail/restore evidence; local scripts alone did not meet those requirements. No other CI service or local-only requirement change had yet been approved, so ARC-06 and PP-001 remained Open and PP-010 remained gated at that point.

On 22 November 2026, the Product Owner approved PRD change RC-01: repeatable local automated verification, a documented pre-merge checklist, and retained evidence replace GitHub-hosted CI merge gates. The local checks preserve the approved automated functional, API, security, and evaluation requirements; passing checklist evidence identifies the exact revision proposed for merge. The deliberate failure/restoration demonstration remains required workshop evidence. GitHub Actions and Playwright remain excluded; no browser E2E framework is selected. ARC-06 and PP-001 are Done, and PP-010 is Implementation Ready subject to its bounded-milestone authorization and readiness recheck. EV-01/02/03 calibration decisions and other downstream gates remain unchanged.

Also on 21 November 2026, the Product Owner approved `AI_SPEC.md` v1.0 as **Approved — Design Baseline**, subject to its documented implementation and calibration conditions. This approval does not resolve the DAI-05 model identifier, initial taxonomy seed, numeric OPS-02 retry/rate limits, EV-01/EV-02/EV-03 evaluation gates, or EV-05 cost limits; each remains pending and must be resolved before its dependent implementation or evaluation. Cost reporting remains required, but no numeric cost limit or cost gate is approved. No other decision status changes in this update.

On 21 November 2026, the user approved PB-09's result fingerprint, primary-label evidence tie-break, severity increase audit, read-only detection-result contract, historical recomputation boundary, and recoverable atomic result application. This does not approve PB-01 or DAI-06 calibration values, classification-attempt authority, notification edge cases assigned to ALERT_SPEC, or unrelated pending decisions.

On 21 November 2026, the Product Owner approved `DETECTION_SPEC.md` v1.0 as **Approved — Design Baseline**. This conditional design approval preserves PB-09 and does not activate automatic detection or approve PB-01, DAI-06, or EV-01/02/03 calibration parameters. The authoritative-classification selection rule remains an unresolved pre-implementation dependency. No other decision status changes by this approval.

On 21 November 2026, the user approved corrections to the Alert Specification: same-severity cooldown is per incident and severity across all routes, with escalation bypass and `SYSTEM_DECISION` audit for suppression; provider unavailability does not suppress incident/outbox persistence; Admin-only retry applies to eligible known-failed events with stable event identity and new delivery attempts; expired SENDING leases and abandoned IN_PROGRESS attempts are reconciled conservatively, with uncertain outcomes marked OUTCOME_UNKNOWN and not automatically resent absent provider verification or an approved policy. Non-definitive classifications are excluded from confirmed counts, DAI-06 determines coverage sufficiency, and automatic detection remains disabled until required coverage policy/calibration approval. Cooldown timestamp anchor and re-crossing behavior remain pending. API_SPEC v1.2.0 and DATA_MODEL v1.2 were draft revisions at that point; API_SPEC v1.1.0 and DATA_MODEL v1.1 remain the last Approved baselines.

On 21 November 2026, UI/API consistency review recorded ARC-08 and DAI-08 as Proposed. API_SPEC.yaml v1.3.0, DATA_MODEL.md v1.3, and UI_SPEC.md v0.2 remained drafts pending review; that review did not approve documents or activate detection/notification behavior. Account-recovery and exact password/session policy remain assigned to SECURITY.md under SEC-01.

On 21 November 2026, the user approved ARC-08 and DAI-08 as recorded above. These decision approvals do not approve `UI_SPEC.md`, `API_SPEC.yaml`, or `DATA_MODEL.md` as documents and do not activate detection or notifications. Exact readiness degradation thresholds and provider-health assessment parameters remain pending for the operations specification. Existing calibration, routing, provider, cooldown-edge, security, and operational decisions remain unchanged.

On 21 November 2026, the Product Owner approved `API_SPEC.yaml` v1.4.0, `UI_SPEC.md` v0.3, and `DATA_MODEL.md` v1.4 as **Approved — Design Baseline**, subject to the unresolved implementation decisions, calibration parameters, and dependencies recorded in those documents. Subsequent approved conditional revisions are API_SPEC v1.5.2, UI_SPEC v0.4.1, and DATA_MODEL v1.5.2. This conditional design approval does not activate detection, notifications, or other functionality whose prerequisites remain unresolved, and does not approve migrations or implementation tickets.
On 22 November 2026, the Product Owner explicitly approved all PP-003 authentication recommendations and PP-004 ingestion recommendations. SEC-01/02 now specify Argon2id/argon2-cffi at 19 MiB, 2 iterations, parallelism 1 (rehash on successful login and benchmark upward); a 15-128 Unicode-code-point NFC password policy with a common/compromised-password blocklist and no composition/periodic-expiry rules; 30-minute idle and 8-hour absolute server-side sessions; concurrent sessions; token rotation; the __Host-productpulse_session Secure/HttpOnly/SameSite=Lax/Path=/ host-only cookie; a 10-minute pre-login CSRF bootstrap, session-bound CSRF, and same-origin production CORS; protected one-time Admin bootstrap; canonical email identity; deactivation/session revocation; Admin-assisted temporary-password recovery with mandatory change and verified in-person handoff; 10-failure/account/15-minute lockout with 15-minute cooldown and 60-attempt/IP/15-minute limit; and safe authentication audit/security-log scope.

DAI-01/02/08 now specify a 20,000,000-byte streamed CSV limit and 50,000 logical data-record cap; strict UTF-8 with a single optional leading BOM; five versioned upload-kind parser contracts; explicit-offset millisecond UTC timestamps; field and identifier limits; exact source identifier preservation/validation; first-valid-row duplicate semantics; never-overwrite source conflicts; guarded reference conflict application; immutable preview/idempotency/hash binding; and UTF-8 formula-safe rejection reports containing rejected/conflicting outcomes without raw feedback or duplicate no-ops. These decisions preserve the PRD's P0 requirements, Admin-only ingestion, DAI-01 mapping precedence, DAI-02 no-overwrite rule, and DAI-08 mapping model. They do not resolve or alter DAI-05 model selection, DAI-06/PB-01 calibration, EV-01/02/03, notification routing/provider choices, OPS-03 artifact retention, deployment provider, or other OPS-02 retry/reconciliation parameters. PP-003 and PP-004 are decision-resolution tickets only; this approval authorizes no application code, migration, or Milestone M2 implementation.

On 22 November 2026, the Product Owner approved an OPS-02 clarification for PP-014: each durable `CLASSIFICATION` work item created for a confirmed feedback import snapshots `max_attempts=3` total claimed attempts, including the initial attempt. PP-014 creates the `QUEUED` item atomically with the import but does not claim or execute it, implement retries/backoff/leases, or call OpenAI.

On 22 November 2026, the Product Owner approved PP-007's initial development parameters: a 5-second SQLite busy timeout with 2 additional `SQLITE_BUSY` retries; one worker polling every 5 seconds; 5-minute work leases renewed every 60 seconds, including during long provider calls; reconciliation every 60 seconds; the 5/15/45-second eligible retry-delay sequence; and the existing PP-014 classification limit of 3 total claims. Provider calls remain outside database transactions and stale-owner writes are rejected. The Product Owner also approved capstone-period synthetic artifact retention without automatic expiry and coherent development backups before every migration and reset/reseed using Python's SQLite backup API with database/artifact mutations quiesced. Deployment-specific backup cadence and retention, provider-specific notification retry limits, routing, sink selection, and external idempotency remain unresolved. `OUTCOME_UNKNOWN` is never automatically resent. PP-018 is eligible for a readiness recheck; this decision is not implementation-milestone authorization.
