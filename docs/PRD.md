# ProductPulse — Product Requirements Document (PRD)

**Project:** Capstone Project 16 — Review and Return Reason Analyser  
**Product:** ProductPulse — AI Product Quality Monitoring & Early Warning Platform  
**Version:** 1.1 (consolidated recommended MVP specification)  
**Status:** Recommended implementation baseline — pending product-owner sign-off on calibration-sensitive decisions  
**Date:** 20 November 2026  
**Audience:** Product owners, developers, QA, design, and capstone reviewers

> **Scope and decision status:** The capstone catalogue mandates AI classification, historical Batch API processing, near-real-time feedback processing, product/supplier/batch linkage, emerging-defect detection, dashboard drill-down, and measurable evaluation. Authentication, admin-only CSV ingestion, automated/manual emails, and incident management were established in project discussion. Version 1.1 integrates recommended product decisions from the MVP Decision Resolution review. These are **resolved for implementation planning**, not evidence of formal stakeholder approval. Detection thresholds, recurrence timing, notification routing, and quality gates remain provisional until product-owner sign-off and evaluation.

## 1. Executive summary

ProductPulse is a web-based product quality intelligence platform for retail businesses. Administrators upload synthetic customer review and product return feedback files in CSV format. The backend validates, stores, and classifies feedback using the OpenAI API, associates feedback with products, suppliers and manufacturing batches, detects emerging defect clusters, and updates an analytics dashboard. Business users log in to view insights and warnings, investigate supporting records, acknowledge and resolve incidents, and manually notify stakeholders. Automatic email notifications are sent when configured warning rules are met.

**Core proposition:** Detect specific product quality issues earlier than a sentiment-only reporting approach, with traceable evidence and accountable follow-up.

**Key architectural principle:** Data ingestion and analysis are background operations. Business users do not upload data or trigger ingestion. The dashboard presents the most recently processed data and its freshness status.

## 2. Problem statement and objectives

### 2.1 Problem

Retailers receive reviews and return explanations across multiple sources. Simple sentiment summaries can hide a growing problem limited to a particular product, supplier or batch. Manual review is slow, inconsistent and difficult to act upon.

### 2.2 Objectives

1. Consolidate synthetic reviews and return reasons in one governed data store.
2. Classify feedback into consistent defect categories and link it to original records.
3. Detect abnormal defect clusters by product, supplier and batch using deterministic application logic.
4. Surface actionable warnings and supporting evidence in an automatically refreshed dashboard.
5. Notify relevant stakeholders automatically and allow authorized users to send alerts manually.
6. Track each warning from detection through investigation and resolution.
7. Measure classification accuracy, detection rate and lead time, source-link accuracy, latency and cost.

### 2.3 Non-goals for MVP

- No business-user uploads, direct edits to source reviews, or self-service ingestion.
- No real customer or client data; synthetic or public non-sensitive data only.
- No automatic supplier emails or external remedial actions without explicit configuration and human approval.
- No model-generated numerical thresholds or unsupported defect conclusions.
- No direct inventory quarantine, product recall, refund or purchase-order changes.
- No guarantee of instantaneous streaming; CSV ingestion is admin initiated and dashboard updates are near-real-time after processing.

## 3. Personas, roles and permissions

### 3.1 Personas

**Administrator (Admin):** Operates the data pipeline, uploads files, reviews ingestion failures, configures classification taxonomy, notification rules and users, and monitors processing health.

**Business User (Quality / Product / Operations):** Monitors quality metrics, investigates product defects, reviews evidence, acknowledges warnings, records findings, resolves/reopens incidents, and sends manual alert emails to approved recipients.

**Read-only Viewer (future):** Deferred from MVP. Only Admin and Business User accounts are created for the capstone.

### 3.2 Role-based access control (RBAC)

| Capability | Admin | Business User |
|---|---|---|
| Sign in and view dashboard | Yes | Yes |
| Filter analytics and view original feedback | Yes | Yes |
| Upload review / return CSV | **Yes** | **No** |
| View ingestion jobs and failed rows | Yes | No |
| Reprocess ingestion jobs | Yes | No |
| Configure taxonomy, thresholds, recipient groups | Yes | No |
| Manage users / permissions | Yes | No |
| View warnings and investigation history | Yes | Yes |
| Acknowledge, investigate, add notes, resolve, reopen warning | Yes | Yes |
| Send manual warning email to approved recipients | Yes | Yes |
| View email delivery status | Yes | Yes (authorized scope) |
| Manage OpenAI credentials | Backend deployment admin only | No |

**Enforcement:** The server authorizes every endpoint; hiding UI controls is insufficient. A Business User calling an upload API directly receives `403 Forbidden`, with no file stored or ingestion job created. This is a single-retailer deployment, not a multi-tenant application.

## 4. Product scope and feature priorities

**P0 = MVP required; P1 = recommended if time allows; P2 = future enhancement.** Capstone-mandated engineering and evaluation requirements remain required even if not visible in the UI.

| ID | Feature | Priority | Primary actor |
|---|---|---|---|
| F01 | Login, session handling and RBAC | P0 | All |
| F02 | Admin-only CSV upload and field validation | P0 | Admin |
| F03 | Import job status, error report and retry | P0 | Admin |
| F04 | Historical classification using OpenAI Batch API | P0 | Backend/Admin |
| F05 | Near-real-time classification for newly ingested records | P0 | Backend |
| F06 | Strict-schema defect classification and taxonomy | P0 | Backend |
| F07 | Product, supplier, batch and source-record linkage | P0 | Backend |
| F08 | Rule-based emerging defect detection | P0 | Backend |
| F09 | Auto-refresh overview dashboard and filtering | P0 | All |
| F10 | Product/defect detail and original-feedback drill-down | P0 | All |
| F11 | Automatic warning creation and email notifications | P0 | Backend |
| F12 | Manual alert email with preview and confirmation | P0 | Admin/User |
| F13 | Warning lifecycle and audit trail | P0 | Admin/User |
| F14 | Alert deduplication and notification cooldown | P0 | Backend |
| F15 | Processing health, last-updated and failure indicators | P0 | Admin/All (summary) |
| F16 | Evaluations, baseline comparison and CI merge gates | P0 | Engineering |
| F17 | Basic incident investigation notes | P0 | Admin/User |
| F18 | Export incident / quality report | P1 | Admin/User |
| F19 | Scheduled CSV ingestion from watched storage | P1 | Admin/Backend |
| F20 | Financial impact estimates and advanced forecasting | P2 | All |
| F21 | Natural-language dashboard assistant | P2 | All |
| F22 | Incident owner assignment and escalation | P1 | Admin/User |

**MVP scope constraint:** Fashion/apparel for one synthetic retailer with 10,000 seeded review/return records; no Viewer, SSO, watched-folder integration, real customer data, supplier email delivery, or production-ready multi-tenancy.

## 5. End-to-end operating model

### 5.1 Background data flow

```text
Admin signs in
   -> Uploads reviews CSV and/or returns CSV
   -> Backend validates file format, required columns, identifiers and duplicates
   -> Valid rows are staged; invalid rows recorded with reasons
   -> Classification job is queued
       -> Historical backlog: OpenAI Batch API
       -> New arrivals: OpenAI Responses API
   -> Structured defect classifications validated and stored
   -> Product/supplier/batch/source links verified
   -> Deterministic detection engine recomputes affected clusters
   -> Dashboard aggregates and warning states updated
   -> Notification rules evaluated
       -> No threshold crossed: continue monitoring
       -> Threshold crossed: create/update warning, deduplicate, queue email
   -> Notification delivery status and audit events recorded
```

CSV uploads are **admin-initiated** in MVP; once uploaded, processing is automatic. A future connector can continuously feed the same ingestion API. No user needs to be logged in for analysis, detection or notifications to continue.

### 5.2 Business user journey

```text
Sign in -> Overview Dashboard -> Review KPI cards / warnings
        -> Filter by date, product, category, supplier, batch, defect
        -> Open product or warning detail
        -> Inspect trends, detection rationale and original feedback
        -> Acknowledge -> Investigating -> Resolved (or Reopened)
        -> Optional: Compose -> Preview -> Confirm manual alert email
        -> Review incident timeline / notification history
```

### 5.3 Administrator journey

```text
Sign in -> Admin Console -> Upload reviews / returns CSV
        -> Map / validate columns -> Confirm import
        -> Track job (queued / running / completed / partial / failed)
        -> Inspect rejected rows and retry corrected input
        -> Review ingestion health and OpenAI usage
        -> Configure taxonomy, alert rules, recipients and users
```

## 6. Screen-level requirements

### 6.1 Login

- Email/password or a development authentication provider; passwords must never be stored in plaintext.
- Redirect to dashboard after successful login; admin can navigate to Admin Console.
- Unauthorized and expired sessions are handled safely.
- Navigation and server routes reflect role permissions.

### 6.2 Overview Dashboard (default landing page)

**Top KPIs:** feedback records analysed, classification coverage (`successfully classified eligible records / validated eligible records`), unique defect-bearing feedback records, return-record count, active warnings, critical warnings, products at risk, and processing freshness. Display returned units separately if `return_quantity` is used. Do **not** display return or failure rates without valid matching sales/transaction denominators.

**Charts:** defect complaints by day/week, defect category breakdown, top affected products, supplier/batch comparisons, returns by reason, and severity distribution.

**Controls:** date range, product, category, supplier, batch, defect type, severity and warning status. Filters must apply consistently across cards, charts and drill-downs.

**Warning list:** severity, product, supplier, batch, defect, first detected, last observed, status, owner (if enabled) and action to open details.

**Freshness:** show last successful import, last successful classification, last detection recomputation, queue/pending counts, and stale-data warnings. A low complaint count must not imply low risk when classification coverage is incomplete.

**Refresh:** poll aggregates every **30 seconds**, with a manual Refresh control. This is a UI cadence, not a guarantee that all new input will be classified within 30 seconds. All event windows and timestamps use UTC; display timezone and window definitions.

### 6.3 Product Intelligence

- Search and select a product; display supplier and batch associations.
- Trend chart for complaints and return reasons over time.
- Defect taxonomy breakdown and affected batch comparison.
- Show distinct complaint counts and return counts with explicit counting units; feedback-based proportions may be displayed only when a clearly defined eligible-feedback denominator is shown, and must never be called product failure rates.
- Navigate from any data point to its contributing source records.

### 6.4 Warning / Incident Detail

- Header: incident ID, severity, status, product, supplier, batch, defect type, first detection, last update.
- Detection rationale: distinct observed complaint count, normalized historical baseline (or explicit zero/insufficient-history status), UTC window, applicable threshold, rule version and linked source records; do not show unsupported rates.
- Time-series chart showing when the cluster emerged.
- Original reviews/returns with source ID, timestamp, text, model classification and data lineage.
- Actions: Acknowledge, Start Investigation, Add Note, Resolve, Reopen, Send Alert.
- Timeline: status changes, notes, automatic/manual emails, delivery results, rule evaluations.
- If evidence is insufficient or contradictory, show uncertainty instead of an unqualified assertion. Show historical-coverage maturity and classification coverage; incident notes are P0.

### 6.5 Customer Feedback Explorer

- Searchable, paginated list of reviews and return reasons.
- Filters for source type, product, supplier, batch, date, defect category and classification state.
- View original text and extracted structured labels, model/version and linked warning IDs.
- Business users cannot edit or re-ingest source records.

### 6.6 Alerts & Incidents

- Tabs or filters: New, Acknowledged, Investigating, Resolved, Reopened.
- Sort by severity, first detection, recent activity and affected product.
- Bulk actions are out of scope for MVP; individual actions must be audited.
- Repeated qualifying feedback updates an existing incident where appropriate instead of creating a duplicate.

### 6.7 Admin Console — Data Sources & Processing

- Admin-only upload controls for `reviews.csv`, `returns.csv`, and optional product/supplier/batch reference CSVs.
- Downloadable CSV templates and documented required fields.
- Validation preview: total rows, accepted rows, rejected rows, missing keys and duplicates.
- Import confirmation, asynchronous job status, error log and retry mechanism.
- Historical Batch API job tracking and near-real-time processing status.
- Usage/cost and operational health summaries.
- Admin-controlled versioned configuration for taxonomy, thresholds, approved internal/sandbox email recipient groups and notification cooldowns; show audit history for changes.

### 6.8 Manual Alert Composer

- Opened from a specific warning/incident; issue details prefilled from the database.
- Recipient selection only from an admin-managed approved internal/sandbox directory; no arbitrary external addresses or direct supplier emails in MVP.
- Subject and body editable, with fixed incident link and key evidence references.
- Preview and explicit **Confirm & Send** step.
- Server verifies sender authorization and recipient permissions; success only after the mail provider accepts the send request.
- Log actor, exact recipients and message content/version, timestamp, delivery state, incident ID and a unique request/event idempotency key. Provider acceptance does not prove delivery.

## 7. CSV input requirements

### 7.1 Reviews CSV — proposed schema

| Field | Required | Example / notes |
|---|---|---|
| review_id | Yes | Unique source record ID |
| product_id | Yes | `P1001` |
| supplier_id | Yes* | `SUP01` |
| batch_id | Yes* | `B101` |
| review_timestamp | Yes | ISO 8601 timestamp |
| review_text | Yes | Customer feedback text |
| rating | No | Integer 1–5 |
| source | No | `web`, `app`, `marketplace` |

### 7.2 Returns CSV — proposed schema

| Field | Required | Example / notes |
|---|---|---|
| return_id | Yes | Unique return record ID |
| product_id | Yes | `P1001` |
| supplier_id | Yes* | `SUP01` |
| batch_id | Yes* | `B101` |
| return_timestamp | Yes | ISO 8601 timestamp |
| return_reason | Yes | Free-text reason |
| return_quantity | No | Positive integer |
| return_category | No | Original source category |

`*` Supplier/batch may be supplied in the record or resolved from an imported product/batch mapping. Otherwise, structurally valid feedback is stored as `LINKAGE_PENDING` and excluded from batch-specific incidents until reconciled. Never invent identifiers.

### 7.3 Validation, partial acceptance and idempotency

- Accept **admin-only manual CSV uploads** after a preview and explicit confirmation. Maximum **20 MB and 50,000 rows per upload**; reject unsupported extensions, malformed CSV, invalid encoding, and structurally invalid files.
- Preview accepted rows, rejected rows, missing keys, duplicate rows and changed-record conflicts. Valid rows may be imported while invalid rows are rejected; produce downloadable row-level reasons.
- Required record identity, product ID, event timestamp, and nonempty feedback text/reason must be valid. Supplier/batch references may be resolved from the record or reference mappings.
- Retain otherwise valid records whose supplier or batch cannot be resolved, mark `LINKAGE_PENDING`, and exclude them from **supplier/batch-specific** incidents. Do not invent missing IDs. Admin reconciliation of mappings triggers recomputation of affected aggregates. Product-level monitoring may continue separately with a distinctly defined cluster key.
- Enforce globally unique `(source_type, source_record_id)` within the synthetic retailer. Identical re-uploads are no-ops; a changed payload with an existing identity is a **conflict requiring admin review**, never a silent overwrite.
- Preserve original source text and event time as immutable normal-workflow records. Store file hash, uploading actor, ingestion timestamp, job ID, accepted/rejected counts, linkage status and reconciliation audit trail.
- Treat review/return event timestamps as **UTC event time** for detection windows; retain ingestion/processing times separately for delayed or late data.
- Escape formula-leading strings in any exported CSV; prevent row duplication and alert duplication under retries.

### 7.4 Synthetic dataset and coverage contract

- Seed **10,000 synthetic review and return feedback records** representing one fashion/apparel retailer, across at least **35 days** of UTC event time, to support a 7-day observation window and the preceding 28-day baseline.
- Include normal patterns, labelled planted defect clusters (zippers, stitching, sizing/fit, material, finish, packaging), non-defects, ambiguous examples, late arrivals and data-quality failures.
- Define and persist which date intervals have complete synthetic source coverage. An absence of complaints is **not** proof of a zero baseline if historical coverage is incomplete.
- Hold out distinct planted scenarios for final evaluation, away from threshold/prompt tuning.

## 8. AI classification requirements

### 8.1 OpenAI integration

- Backend calls the OpenAI **Responses API** for new feedback and the **Batch API** for historical backlogs.
- OpenAI API key is provided through server-side secret configuration (e.g. `OPENAI_API_KEY`), never exposed to the browser, committed to Git, included in logs or sent in user-visible responses.
- Use a selected supported model and **Structured Outputs** with strict JSON schema. Historical Batch and incremental Responses paths must obey the same versioned classification contract.
- Store model identifier, prompt/schema version, token usage, latency and estimated cost for each job, without exposing secrets.
- Use retries with exponential backoff for transient failures and dead-letter/failed-record tracking after retry exhaustion.
- Review text is untrusted input: model must classify it, not follow instructions embedded in it.

### 8.2 Proposed defect taxonomy

- Functional failure (e.g. broken zipper, non-working switch)
- Sizing / fit
- Material / durability
- Appearance / finish
- Packaging / leakage / shipping damage
- Performance / overheating / battery
- Other product defect
- No defect / non-actionable
- Uncertain / needs review

The taxonomy and normalized `specific_issue_code` dictionary must be versioned. One feedback record may have a primary and optional secondary issue labels. Deduplicate identical issue codes within the same record and cluster; do not count the same complaint twice in one cluster.

### 8.3 Classification output schema (illustrative)

```json
{
  "source_record_id": "R001",
  "has_defect": true,
  "primary_category": "functional_failure",
  "specific_issue_code": "zipper_failure",
  "severity_hint": "medium",
  "evidence_excerpt": "zip stopped working after two uses",
  "needs_review": false
}
```

The JSON is illustrative; implementation must add source type, schema version and optional secondary labels to its validated response contract. Schema validity does not prove factual correctness. Validate allowed taxonomy values, source-ID correspondence and evidence grounding; uncertain/invalid classifications must be retried or flagged, not silently treated as no defect. Model-provided severity is only an advisory input; final warning severity is computed solely by versioned backend rules. Failed, uncertain or needs-review records do not silently become `no_defect` and do not contribute to confirmed complaint counts. Dashboard classification coverage makes these exclusions visible.

## 9. Defect detection and warning logic

### 9.1 Counting, cluster identity and time windows

- **Counting unit:** One distinct `(source_type, source_record_id)` with a successfully validated `has_defect=true` classification per cluster. One record may contribute to distinct issue clusters via secondary labels but may not count twice in the same cluster.
- **Batch-specific cluster key:** `(product_id, supplier_id, batch_id, specific_issue_code)` with a normalized versioned issue code nested in its defect category. Batch-specific incidents require resolved product, supplier and batch keys. Product-level monitoring of unresolved linkage must use a separate, explicitly labelled key without fabricated identifiers.
- **Time basis:** UTC event time. At evaluation instant `T`, count observed complaints in `[T−7 days,T)` and baseline complaints in `[T−35 days,T−7 days)`. Store evaluated instant, source IDs, counts, coverage, rule version and linkage status.
- **Baseline:** `baseline_7d = baseline_28d_count / 4`; calculate `observed_7d / baseline_7d` only for a usable **nonzero** baseline. A usable baseline requires declared full 28-day historical event-time coverage, not simply a database with some older records.
- If historical coverage is complete but prior count is **zero**, display `No prior observed complaints` and apply the count-only thresholds in Section 9.2. Never display an infinite multiplier.
- If 28-day coverage is insufficient, display `Insufficient historical baseline`, retain trend evidence but suppress automatic warning emails. A provisional trend-only indicator may be shown; do not assign a validated alert severity from an unsupported ratio.
- Recompute affected aggregates on new classifications, corrected linkages and late arrivals; run scheduled reconciliation to detect missed changes.

### 9.2 Configurable initial rules (provisional; not validated)

These are **MVP demo hypotheses**. Calibrate on development planted scenarios, freeze the configuration before held-out evaluation, and log the rule version applied. Choose the **highest** qualifying severity.

| Level | With usable nonzero 28-day baseline | With complete, usable zero baseline | Dashboard behavior | Automatic email |
|---|---|---|---|---|
| Informational / trend-only | No qualifying medium threshold | Fewer than 5 complaints | Trend only, not incident | No |
| Medium | ≥5 distinct complaints in 7 days **and** ≥2× baseline | ≥5 complaints in 7 days | Create/update incident | No |
| High | ≥10 complaints in 7 days **and** ≥3× baseline | ≥10 complaints in 7 days | Create/update incident | Yes (sandbox) |
| Critical | ≥20 complaints in 7 days **and** ≥5× baseline | ≥20 complaints in 7 days | Create/update priority incident | Yes, priority (sandbox) |

- Counts are feedback-record complaints, **not** rates of product failure. Return-record count and `return_quantity` are distinct measures. Do not infer sales volume.
- A model's `severity_hint` alone **cannot** trigger Critical. Credible safety-related content may be flagged for human review; any special deterministic safety rule requires separate design, validation and approval.
- Detection rationale must expose source record IDs, actual counts, baseline math, coverage status and threshold used. For insufficient history, present uncertainty and no automatic alert email.

### 9.3 Incident lifecycle and episode boundaries

- Auto-generated incidents begin `NEW`; allowed workflow: `NEW → ACKNOWLEDGED → INVESTIGATING → RESOLVED`, with `RESOLVED → REOPENED → INVESTIGATING` for recurrence and authorized review. Record actor, timestamps, notes and before/after states. Basic investigation notes are P0.
- Maintain at most **one open incident per cluster**. New evidence updates its counts and source links rather than creating another incident; decreasing counts do **not** automatically resolve it.
- For a qualifying recurrence **within 30 days after resolution**, reopen the same incident. If the recurrence occurs **more than 30 days after resolution**, create a new linked episode. Compute this window from the stored resolution timestamp and audit the decision.
- A resolved incident remains monitored. A confirmed new qualifying spike can reopen or create a linked episode without deleting old history.

### 9.4 Deduplication, cooldown and escalation

- High and Critical events queue automatic emails to approved recipients. Medium incidents do not auto-email.
- Enforce a **24-hour cooldown** for repeated same-severity automatic emails per incident; higher-severity escalation bypasses cooldown. Use durable outbox events and stable event IDs to prevent duplicate internal dispatch requests.
- Manual notification events are distinct from automated events and never change severity or block escalation.
- Route by admin-approved product/category/supplier mapping, falling back to the configured internal quality-team sandbox inbox. If no approved route/fallback exists, do not send; surface an operational error.
- Email provider acceptance is not proof of actual delivery, and exactly-once external delivery cannot be guaranteed unless the provider supports idempotency.

## 10. Email notifications

### 10.1 Automatic alert email

**Trigger:** A detection rule crosses the configured notification threshold or an existing warning escalates.  
**Recipients:** Approved **internal/sandbox** recipient group mapped to product/category/supplier; use an approved quality-team sandbox fallback where needed. Never automatically email suppliers in MVP.  
**Content:** Incident ID, product, supplier, batch, defect type, severity, observed distinct complaint count, baseline, first detected time, supporting evidence summary, and secure link to the incident.  
**Safety:** Synthetic data only; no personal customer details, unverified numeric claims or non-approved external recipients. Do not send if no valid routing destination is configured.  
**Audit:** Store event ID, recipient group, delivery provider message ID, timestamps and delivery status.

### 10.2 Manual alert email

**Trigger:** Authorized user clicks Send Alert from an incident.  
**Workflow:** Select approved recipients -> edit optional note -> preview -> confirm -> send -> record history.  
**Controls:** Require incident-scoped preview and explicit confirmation, server-side approved-recipient authorization and a stable request idempotency key; audit exact message and initiator. Manual alerts do not change severity or suppress escalations.

### 10.3 Delivery states

`QUEUED`, `SENDING`, `ACCEPTED`, `FAILED`, and optionally `DELIVERED`/`BOUNCED` where provider callbacks support them. Persist a durable notification outbox and retry transient failures with bounded backoff. **Accepted** means the email service accepted the request, not necessarily that the recipient read the message.

## 11. Data model (logical)

| Entity | Key fields / relationships |
|---|---|
| users | id, email, role, status |
| products | product_id, name, category |
| suppliers | supplier_id, name |
| batches | batch_id, product_id, supplier_id |
| ingestion_jobs | job_id, file_type, file_hash, uploaded_by, status, counts, timestamps |
| feedback | feedback_id, source_type, source_record_id (unique pair), product_id, nullable unresolved supplier_id/batch_id, linkage_status, event_time_utc, text, ingest_job_id |
| classifications | classification_id, feedback_id, taxonomy_version, schema_version, model, prompt_version, normalized issue codes, evidence, status, usage |
| defect_clusters | cluster_id, cluster_key, window_utc, observed_count, baseline_28d_count, normalized_baseline, coverage_status, rule_version |
| incidents | incident_id, cluster_id, previous_episode_id (optional), severity, status, first_detected, last_seen, resolved_at, owner (P1) |
| incident_events | event_id, incident_id, actor, action, note, timestamp |
| notification_rules | rule_id, routing_scope, severity_threshold, cooldown, recipient_group |
| notifications | notification_id, incident_id, event_id unique, type, actor, approved recipients, exact content/version, status, provider_id, timestamps |
| audit_logs | event_id, actor, resource, action, result, timestamp |
| source_coverage | scope, window_start_utc, window_end_utc, completeness_status, import_job_id |
| ingestion_conflicts | conflict_id, source_type, source_record_id, existing_hash, incoming_hash, job_id, status |

Maintain referential integrity and source-to-classification-to-cluster-to-incident traceability. Consider indexes on feedback event time, product/batch, defect category and incident status.

## 12. API requirements (proposed REST surface)

| Method / endpoint | Purpose | Authorization |
|---|---|---|
| `POST /auth/login` | Authenticate | Public |
| `GET /dashboard/summary` | KPI cards and freshness | Authenticated |
| `GET /dashboard/trends` | Filtered time-series | Authenticated |
| `GET /products` | Product search/list | Authenticated |
| `GET /products/{id}` | Product quality detail | Authenticated |
| `GET /feedback` | Filtered source records | Authenticated |
| `GET /incidents` | List warnings | Authenticated |
| `GET /incidents/{id}` | Evidence and timeline | Authenticated |
| `POST /incidents/{id}/status` | Acknowledge/investigate/resolve/reopen | Admin/User |
| `POST /incidents/{id}/notifications/preview` | Preview manual alert | Admin/User |
| `POST /incidents/{id}/notifications` | Confirm/send manual alert | Admin/User |
| `POST /admin/ingestion/uploads` | Upload CSV | **Admin only** |
| `GET /admin/ingestion/jobs` | View import jobs | **Admin only** |
| `POST /admin/ingestion/jobs/{id}/retry` | Retry failed job | **Admin only** |
| `GET/PUT /admin/settings/*` | Rules, taxonomy, recipient groups | **Admin only** |
| `GET /health` | Service health | Deployment monitoring |

All endpoints require validation, pagination where applicable, appropriate rate limits and consistent error responses. The server must enforce scope and authorization independently of the frontend.

## 13. Non-functional requirements

### 13.1 Performance and availability

- Proposed dashboard p95 initial load target: **<= 3 seconds** on a seeded 10,000-record dataset in the test environment (target to validate).
- Proposed near-real-time target: new feedback reflected in dashboard **within 60 seconds after successful classification**, excluding provider queue delays. Report event-to-display and ingestion-to-display latency separately; 30-second polling is not a processing SLA.
- Background processing must not block interactive dashboard requests.
- Health endpoints and observable worker/job status are required.

### 13.2 Security and privacy

- Only synthetic or public non-sensitive data for the capstone; no real customer, C5i or client records, PII or PHI.
- Store OpenAI credentials and mail provider credentials in a secret manager or protected server environment; never in browser code, prompts, logs or repository.
- Enforce role permissions on all server routes and data access.
- Validate uploaded files and limit file size, type and row count; protect against CSV injection on exports.
- Test prompt injection in malicious review text and unauthorized requests to admin endpoints.
- Use TLS for deployed services, parameterized queries, audit logging and least-privilege database credentials.
- Redact sensitive text in telemetry and traces; do not send API secrets to the model.

### 13.3 Reliability and operations

- Ingestion and notification handlers must be idempotent.
- Use durable queues or equivalent persisted job states; support retries and failure visibility.
- Monitor classification failures, queue depth, ingestion age, notification failures and model costs.
- Provide deployment runbook, health checks, non-production environment, demonstrated rollback and cost/usage telemetry.

### 13.4 Accessibility and usability

- Desktop-first responsive web UI, keyboard-accessible controls, meaningful chart labels, color plus text for severity, and readable empty/loading/error states. Explain insufficient baseline, unresolved linkage and incomplete classification coverage in ordinary language.
- Every KPI and alert should expose its definition, time window and data freshness.

## 14. Evaluation and capstone evidence

| Metric | Evaluation approach |
|---|---|
| Defect taxonomy precision/recall | Held-out human-labelled synthetic review/return dataset; report per-class precision/recall and confusion matrix, plus uncertain-case counts. |
| Planted-cluster detection recall | On locked held-out planted episodes, report detected/total and false-positive warnings; compare results with baseline detection. |
| Detection lead time | Compare first qualifying ProductPulse warning with a documented sentiment-score or negative-review threshold baseline on **identical event-time streams**. |
| Source-link integrity | Verify classification → original source → product/supplier/batch → incident links for all evaluated records; correctly handle unresolved links. |
| Classification schema validity | Confirm strict-schema compliance for **stored completed** classification outputs; count rejects and needs-review items separately. |
| Cost per 1,000 feedback records | Track model, token usage, retry costs and Batch versus incremental processing. |
| Dashboard performance and pipeline latency | Measure dashboard p95 on 10,000 records; separately report ingestion-to-classification, classification-to-display and end-to-end latency. |
| Notification and incident safety | Measure duplicate incidents/notifications under retries, recurrence behavior, recipient authorization and provider acceptance states. |
| RBAC and prompt-injection tests | Attempt business-user uploads and injection via feedback text; verify forbidden actions fail. |

### 14.1 Provisional release gates and reporting

**Required automated MVP gates** (planning defaults; verify before approval):

- **100%** valid strict schemas for persisted, *completed* classifications; invalid/uncertain classifications are excluded and reported rather than silently treated as normal feedback.
- **100%** correct source-reference integrity in the test fixtures, including no fabricated supplier/batch links.
- **≥90%** recall of planted episodes in the locked held-out evaluation set. Report precision, false positives and missed episodes; this recall target is provisional and should be revisited if scenario count is too small.
- **Zero** duplicate incidents in retry/idempotency tests, unauthorized Business User uploads, and unconfirmed manual emails.
- CI blocks merges for reference-integrity failures, critical security/permission failures, planted-episode recall below the configured threshold or a known classification regression. Classification class-specific thresholds must be set from development evaluation and class prevalence before held-out testing; do not invent an unsupported macro-accuracy promise.

Lock the held-out dataset **before** final tuning. Report results, not assumed attainment. Demonstrate a deliberate failing CI change and restoration of a passing build.

**Other required capstone artifacts:** BRD with acceptance criteria, solution design, task plan, `AGENTS.md`, Codex review log, evaluation dataset and report, security triage, injection tests, non-production deployment, health checks, rollback demonstration, operating runbook, and 5–6-slide presentation with live demo.

## 15. Acceptance criteria (testable MVP scenarios)

| ID | Given / When / Then |
|---|---|
| AC01 | Given a Business User session, when they request an admin upload endpoint, then the server returns 403 and no ingestion job is created. |
| AC02 | Given an Admin session and valid reviews CSV, when uploaded, then a job ID is returned and accepted records are persisted once. |
| AC03 | Given a CSV with valid and invalid rows, when Admin previews and confirms an import, then valid rows are accepted once and rejected rows produce downloadable reasons. |
| AC04 | Given a duplicate upload or retry, when processed, then source records and incidents are not duplicated. |
| AC05 | Given valid feedback, when classification completes, then the result conforms to the strict schema and references the original feedback record. |
| AC06 | Given feedback containing instructions to ignore rules, when classified, then the system treats it as data and does not execute the instructions. |
| AC07 | Given historical feedback, when the Batch API job completes, then results are ingested, validated and included in analytics. |
| AC08 | Given a newly imported record, when the near-real-time classification finishes, then affected dashboard aggregates refresh without a business user initiating analysis. |
| AC09 | Given a planted defect spike above the configured threshold, when the detection job runs, then a warning is created with reproducible counts and baseline evidence. |
| AC10 | Given an active warning, when further matching feedback arrives, then the existing warning updates without duplicate same-severity emails inside cooldown. |
| AC11 | Given a warning severity escalation, when the rule evaluates, then an escalation email is queued even during the standard cooldown. |
| AC12 | Given a warning, when a user opens its detail page, then they can inspect correct original reviews and return records, supplier and batch links, and calculation rationale. |
| AC13 | Given an authorized user, when they select recipients and confirm a manual email, then the provider send is attempted and the exact action is audited. |
| AC14 | Given a user who has not confirmed a manual alert, when they exit the composer, then no email is sent. |
| AC15 | Given a warning in NEW state, when authorized users acknowledge, investigate and resolve it, then transitions and notes are recorded chronologically. |
| AC16 | Given a failed or delayed ingestion pipeline, when a user opens the dashboard, then the system shows data freshness and a visible processing warning. |
| AC17 | Given the held-out evaluation set, when CI runs, then quality metrics are calculated and configured regressions block merge. |
| AC18 | Given the deployed non-production application, when rollback is executed, then the previous healthy version is restored and verified by health checks. |
| AC19 | Given structurally valid feedback with unresolved supplier/batch mapping, when ingested, then it is `LINKAGE_PENDING` with no batch-specific incident; when Admin corrects mapping, affected aggregates recompute. |
| AC20 | Given complete 28-day baseline coverage with zero observed prior complaints, when 7-day counts cross a count-only threshold, then the corresponding incident is created without an infinity multiplier. |
| AC21 | Given insufficient 28-day historical coverage, when a recent cluster is detected, then the UI shows unavailable baseline and no automatic warning email is sent. |
| AC22 | Given a resolved incident and renewed qualifying evidence, when recurrence is within 30 days, then the same incident reopens; when later, a linked new episode is created. |
| AC23 | Given an existing source identity and different newly uploaded text, when an admin uploads it, then the system reports a conflict and does not overwrite the original. |
| AC24 | Given pending or needs-review classifications, when complaint totals are shown, then those records are excluded from confirmed complaints and classification coverage exposes the incomplete processing. |

## 16. Recommended implementation architecture

**Frontend:** React + TypeScript, dashboard charting library; 30-second aggregate polling and explicit data-freshness states.  
**Backend:** Python FastAPI with server-side RBAC and validation.  
**Database:** PostgreSQL (source records, classifications, incidents, audit).  
**Background jobs:** Durable queue/worker or database-backed job scheduler, periodic reconciliation and notification outbox.  
**AI:** OpenAI Responses API for new records; Batch API for historical backlogs; strict structured outputs.  
**Analytics:** SQL/Python deterministic aggregations and cluster rules.  
**Notifications:** Approved internal/sandbox mailbox via a backend adapter and idempotent outbox; no supplier or production external delivery.  
**CI/CD:** GitHub Actions or equivalent; unit, integration, security and evaluation gates.  
**Deployment:** Non-production cloud environment with health checks, secrets, logs, usage metrics and rollback.

**Important separation:** OpenAI classifies unstructured feedback; it does not calculate KPI totals, determine alert thresholds, authorize users or send emails directly. These responsibilities stay in tested backend services.

## 17. Suggested delivery phases

1. **Foundation:** Repository standards, BRD, versioned taxonomy/issue codes, 10,000-record synthetic data generator with declared historical coverage, DB schema, RBAC and secure login.
2. **Ingestion:** Admin upload UI/API, validation, idempotency, job tracking, historical and near-real-time paths.
3. **AI:** Strict-schema classification, prompt-injection handling, evaluation dataset, cost tracking.
4. **Detection:** Linkage reconciliation, 7-day/28-day baseline algorithm, zero/missing-history rules, planted clusters, incidents, 30-day recurrence.
5. **Experience:** Dashboard, product detail, feedback explorer, warning drill-down and freshness.
6. **Actioning:** Sandbox auto/manual emails, approved-recipient routing, cooldown, incident notes/status, recurrence and audit.
7. **Hardening:** CI evaluation gate, load/security tests, deployment, rollback, runbook and live demo.

**Suggested 4-person ownership:** (1) ingestion/database; (2) OpenAI classification/evaluation; (3) detection/incidents/notifications; (4) frontend/auth/deployment. Everyone participates in review, security and the final defence.

## 18. Demo scenario

1. Admin uploads historical reviews and returns CSV; show job completion and dashboard population.
2. A prepared CSV simulator or repeated admin uploads introduce new feedback in small intervals (the simulator is a test harness, not a business-user upload feature).
3. OpenAI classifies feedback; the dashboard updates automatically.
4. A planted zipper defect in `Product P1001 / Supplier SUP01 / Batch B101` crosses the high-severity threshold.
5. A warning appears and an automatic email is recorded in the sandbox mailbox.
6. Business user logs in, opens the warning, reviews the original comments and calculation, acknowledges it and adds a note.
7. Business user previews and confirms a manual email to an approved recipient; notification history updates.
8. Team presents classification accuracy, lead-time improvement over sentiment baseline, cost per 1,000 reviews, CI gate, security checks and rollback.

## 19. Consolidated MVP decision register and sign-off boundary

All entries below are **recommended defaults for the implementation baseline**, not previously authorized organizational policies.

| ID | Topic | Resolution for MVP | Deferred / validation |
|---|---|---|---|
| D01 | Product domain | Fashion/apparel | Expand to other categories later |
| D02 | Dataset | 10,000 labelled synthetic review/return records, ≥35 days of event-time coverage, planted/held-out clusters | No real personal, C5i, or client data |
| D03 | Uploads | Admin-only manual CSV; preview, confirmation, partial acceptance, rejected-row report; 20 MB/50k-row limit | Watched-folder ingestion P1 |
| D04 | Freshness | 30-second poll + manual refresh + import/classification/detection timestamps | Actual latency separately measured |
| D05 | Roles | Admin and Business User | Viewer deferred |
| D06 | Email | Sandbox, approved internal recipients, automatic High/Critical, confirmed manual send | No supplier/production external sends |
| D07 | Detection | Distinct complaint counts in recent 7 days vs preceding normalized 28-day baseline; provisional severity table in §9.2 | Calibrate and version after planted-scenario evaluation |
| D08 | Denominators | Complaint-record counts, raw return-record counts, separate returned units where known | No product return/failure rate without units sold or matching transactions |
| D09 | Severity | Backend-only rule-derived severity; model hint advisory | Safety overrides require separate validation |
| D10 | Tenancy | Single synthetic retailer | Multi-tenancy deferred |
| D11 | Authentication | Secure email/password and server-side session/RBAC | SSO deferred |
| D12 | Unresolved links | Accept valid record as `LINKAGE_PENDING`, exclude from batch-specific incidents; reconcile later | No invented supplier/batch IDs |
| D13 | Idempotency | Same source identity + same payload is no-op; changed payload is admin-visible conflict | Corrections workflow deferred |
| D14 | AI paths | Historical Batch API and incremental Responses API, common versioned output contract | No classification-triggered dashboard work by Business Users |
| D15 | Multi-label counting | Primary plus optional secondary; distinct feedback counted once per issue cluster | Avoid repeated mention double-counting |
| D16 | Zero/incomplete baselines | Count-only gates for complete zero history; insufficient history prevents automatic email | No infinite multiplier |
| D17 | Recurrence | Reopen within 30 days of resolution; later qualifying spike creates linked episode | Product-owner review of episode length |
| D18 | Notification reliability | Durable outbox, stable event identity, retries, accurate ACCEPTED vs DELIVERED status | Exactly-once provider delivery not promised |
| D19 | Evaluation | Locked held-out data; provisional ≥90% planted-episode recall and integrity/security gates | Validate feasibility and class-specific gates |

### 19.1 Items requiring formal sign-off

1. Detection thresholds, minimum complaint counts, and the 28-day historical-coverage definition after calibration.
2. The 30-day incident-reopen boundary, including whether demonstrations show reopen or linked episodes.
3. Sandbox recipient directory, quality-inbox fallback, and permitted notification events.
4. Final held-out evaluation size, class-specific classification gates and ≥90% planted-episode recall target.

**Change control:** Any alteration to the thresholds, taxonomy, issue-code dictionary, episode window or email routing must be versioned and reflected in configuration audit logs, evaluation fixtures, acceptance tests and the demo narrative. Until explicitly approved, v1.1 is the working design baseline rather than a signed-off production policy.

## 20. References and provenance

**Primary requirements source:** *Capstone Projects — Applied GPT Capability Program for Engineering Practitioners (GPT Coders Track), C5i × Ambilio*, Project 16, “Review and Return Reason Analyser,” catalogue pages 13–14. The brief requires classification of synthetic reviews/return reasons, historical Batch API and near-real-time processing, product/supplier/batch linkage, code-based emerging-cluster detection, source drill-down and planted-cluster evaluation.

**Product decisions:** Admin-only CSV ingestion, business-user investigate/alert rights, backend OpenAI credentials, automatic/manual email and incident lifecycle came from the project discussion. The revised definitions of dataset, roles, detection thresholds, zero-baseline behavior, recurrence, email routing and CI gates are *recommended* MVP resolutions from the ProductPulse MVP Decision Resolution review, pending product-owner ratification.

**Relevant competitor references for context (not normative requirements):**
- Revuze — https://www.revuze.it/
- unitQ Monitor — https://www.unitq.com/products/unitq-monitor/
- Loop Returns documentation — https://help.loopreturns.com/en/articles/13680897
- Yotpo Insights documentation — https://support.yotpo.com/docs/yotpo-insights-overview

---

## Appendix A. Changes from v1.0

- Resolved all 11 original open MVP assumptions and incorporated eight additional operational decisions (D12–D19).
- Made the initial 7-day-versus-28-day rule, minimum counts, zero/incomplete-history outcomes, UTC event-time windows and 30-day incident recurrence executable and auditable.
- Clarified unresolved supplier/batch records, idempotent re-uploads, conflicting payloads, classification coverage and normalized multi-label counting.
- Defined sandbox-only approved email recipients, status semantics, cooldown, outbox/retry behavior and escalation.
- Promoted basic investigation notes to P0; moved owner assignment/escalation to F22 P1; deferred Viewer role.
- Added AC19–AC24 and provisional held-out evaluation gates; maintained explicit product-owner sign-off boundaries.

---

**Document end — ProductPulse PRD v1.1**
