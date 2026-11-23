# ProductPulse UI/UX Specification

**Version:** 0.4.1  
**Status:** Approved — Design Baseline  
**Approval date:** 22 November 2026  
**Requirements source:** PRD v1.7  
**Related specifications:** Architecture v1.5 (Approved); AI_SPEC v1.0 (Approved — Design Baseline); Tech Stack v1.2.0; Detection Specification v1.1 (Draft clarification; v1.0 remains the Approved Design Baseline); Alert Specification v0.3 (Draft); API_SPEC.yaml v1.5.2 (Approved — Design Baseline, conditional); Data Model v1.5.2 (Approved — Design Baseline, conditional); Security v1.1; Decision Register v2.0.

## 1. Purpose and approval boundary

This specification defines the React + TypeScript presentation layer for the ProductPulse MVP. It translates the PRD and current API design into a practical screen set for one retailer and a solo developer. Recharts is the approved charting library. The component library, frontend router, state-management package, and exact route URLs remain unselected; this specification does not select them.

The API is the authorization and validation boundary. UI visibility and client validation improve usability but do not grant access. The browser does not call OpenAI or an email provider, run detection formulas, decide alert eligibility, or hold provider credentials.

The original conditional design baseline was approved on 21 November 2026; this revision records the Product Owner-approved PP-003 authentication, PP-004 ingestion, and PP-007 operational decisions dated 22 November 2026. It does not approve the draft Detection or Alert specifications or authorize application code. The API and Data Model conditional design baselines are reflected here; exact readiness degradation/provider-health assessment parameters remain pending for the operations specification. This approval does not activate detection, notification routes, or other functionality whose prerequisites remain unresolved. Implementation remains subject to the pending decisions documented in this specification and its related contracts.

### 1.1 Governing display rules

- Display only values and states returned by the API. Do not compute KPI definitions, alert thresholds, detection severity, coverage sufficiency, recipient routing, or delivery success in the browser.
- Keep record counts, return-record counts, and returned-unit counts distinct. Never label feedback counts as a product failure or return rate.
- Do not show an undefined metric as zero. A null value with PENDING_DEFINITION is displayed as “Definition pending.”
- Exclude pending, failed, needs-review, uncertain, invalid, or otherwise non-definitive classifications from confirmed defect counts. Show processing or coverage incompleteness separately.
- Show LINKAGE_PENDING product analytics in a separately labelled context. Such records do not establish supplier/batch incidents or automatic notifications.
- Show UTC event times and the exact API-provided event window. Do not substitute the user's local timezone for event-window calculations.
- Keep automatic detection and automatic notification activation visibly pending until the required classification-attempt authority, DAI-06 coverage policy and calibration, and PB-01 threshold calibration are approved. The UI must not present the feature as active while these gates are unresolved.
- Use the role-visible GET /readiness projection for coarse detection, processing, notification-configuration, and email-provider states. Display UNKNOWN as unknown; never map it to ACTIVE or HEALTHY, style it as a healthy state, or present it as evidence of zero product defects. Never infer readiness from Admin-only operations data or browser calculations. INACTIVE detection is not zero defects. This projection reveals no provider identity, route, recipient configuration, credentials, or secrets and does not authorize an action.
- Enable manual notification confirmation only when readiness reports manual_confirmation_state ENABLED and the authorized recipient list is available. An email_provider_state of UNAVAILABLE is a separate warning; confirmation may still persist an outbox event, but the UI must show only the API's persisted outcome and must never imply delivery. No real external or supplier email is in scope.

## 2. Roles, navigation, and access

### 2.1 MVP roles

Only Administrator and Business User roles exist in the MVP. A future read-only Viewer is out of scope. The app uses the authenticated role returned by GET /auth/session to tailor navigation, but every protected operation is still checked by the backend.

### 2.2 Primary navigation

Authenticated users see:

1. Overview
2. Product Intelligence
3. Feedback Explorer
4. Alerts & Incidents

An incident detail opens from an incident row or a linked dashboard result. Manual Alert Preview opens in the context of one incident. Admin-only navigation contains:

5. Data Upload
6. Ingestion & Processing
7. Admin Settings, including User Management

Use these as navigation labels and screen identifiers. Exact browser route paths and URL state encoding are implementation decisions because frontend routing is not selected. Keep the current page, selected product/incident, and useful filter context when navigating to details where the API accepts those filters.

### 2.3 Capability matrix

| Capability | Administrator | Business User |
|---|---:|---:|
| Sign in, sign out, view dashboard, filter analytics | Yes | Yes |
| Search products and view source feedback | Yes | Yes |
| View incidents, evidence, notes, status history, and permitted notification history | Yes | Yes |
| Change incident state and append investigation notes | Yes | Yes |
| Compose and confirm a manual alert to an approved directory recipient | Yes, when notification prerequisites are approved and enabled | Yes, when notification prerequisites are approved and enabled |
| Upload, preview, confirm, or retry ingestion | Yes | No |
| View ingestion jobs, row errors, processing jobs, and detailed operational status | Yes | No |
| Reconcile source-link conflicts | Yes | No |
| Manage taxonomy, detection rules, notification routes, recipients, and groups | Yes | No |
| Create or deactivate users | Yes | No |
| Retry an eligible known-failed notification | Yes | No |
| Manage OpenAI or mail-provider credentials | No UI capability | No |

Hiding Admin navigation is not an authorization control. A Business User who follows an Admin link or calls an Admin endpoint directly receives the backend's 403 response. In particular, a denied upload request must create no preview, artifact, or ingestion job.

## 3. Application shell and shared behavior

- Use a compact desktop-first shell with a page title, breadcrumb or parent link on detail screens, role-appropriate primary navigation, and a visible sign-out action.
- Use one shared filter state for Overview and compatible drill-downs. Keep applied filters visible, provide a clear-all action, and show the exact UTC range. Do not send a filter to an endpoint that does not define it or imply that an unsupported filter was applied. The incident list supports the common subset documented in §5.3; category_code and source_type apply to dashboard aggregates and feedback/product results, not GET /incidents. Show those filters as not applied to the incident panel and omit them from incident requests.
- Use server pagination for lists. The API design baseline defaults to page 1 and page_size 50, with a maximum page_size of 100; follow the specified API values.
- Display event timestamps with an explicit UTC label. Display API-generated or operational times according to their meaning rather than relabelling them as event time.
- Provide page-level loading, empty, stale, and error states. Preserve the last successful data when a refresh fails, but label it stale and show when it was last updated.
- Avoid automatic retries of state-changing requests. Use the API's idempotency contract for supported commands and show the resulting persisted state.
- For data labels and statuses, show plain-language text alongside raw enum values only where an Admin needs the technical state for operations.

## 4. Screen inventory and requirements

### 4.1 Login

**Purpose:** Establish an authenticated server-side session for an existing account.

**Content and behavior**
- Email and password fields, submit action, field-level validation, and a generic credential failure message that does not disclose whether the account exists.
- No public registration, SSO, or self-service recovery. On page bootstrap, call GET /auth/csrf, retain the returned CSRF value in memory only, and submit it with POST /auth/login. Admin-assisted password reset uses a temporary credential handed directly to the verified user in person outside ProductPulse; ProductPulse sends no recovery email.
- On success, retain only the public user and session-bound CSRF token returned by the API; do not store the session token. If must_change_password is true, route to the forced password-change screen and allow only session inspection, logout, or password change until complete. After change, use the fresh session and CSRF values returned by the API.
- On expired or revoked session, return to Login. Do not automatically replay a previously submitted mutation after re-authentication.

**API mapping:** GET /auth/csrf and POST /auth/login for bootstrap/sign-in; GET /auth/session during session bootstrap; POST /auth/password-change for forced change; POST /auth/logout for sign-out.

**Errors:** 401 shows a generic sign-in failure; 422 shows field/request validation; 429 shows generic retry guidance. Never display raw authentication details or account existence.

### 4.2 Overview Dashboard

**Purpose:** Provide the shared entry point for quality trends, warnings, and freshness.

**KPI cards**
- Feedback records analysed.
- Classification coverage, using the PRD definition: successfully classified eligible records divided by validated eligible records.
- Unique defect-bearing feedback records.
- Return-record count.
- Returned units, when returned-unit data is available; always labelled separately from return records.
- Active warnings, critical warnings, and products at risk only when the API returns a defined value. Until PB-05 definitions are approved, display the returned null/PENDING_DEFINITION state as “Definition pending.”
- Data freshness and coverage status.

Each card shows its unit, applicable filter/window context, and freshness. Do not infer a zero from missing data or incomplete coverage.

**Charts**
Use the trend metrics defined by the API: defect complaints, defect-category breakdown, top affected products, supplier/batch comparison, returns by reason, and severity distribution. Label every axis/legend with the API-provided unit and time bucket. Use UTC day/week buckets and display the returned bucket boundaries. Do not calculate an additional percentage, rate, or severity from chart points.

**Filters**
Expose date range, product, category, supplier, batch, logical defect, severity, incident status, and source type where supported. Dashboard summary and trend panels receive their defined filters. The warning list receives only its API-supported subset; category_code and source_type are visibly marked as not applied to incident rows. Date filters use inclusive from_utc and exclusive to_utc bounds. Carry only compatible applied filters into drill-downs.

**Warning list**
Show incident ID, severity as text and color, product/supplier/batch/defect identity, first-detected and last-seen times, status, and a link to incident detail. Do not show an owner field unless an approved owner-assignment feature is later added; ownership is P1 in the PRD.

**Freshness and coverage**
Show last successful import, classification, and detection recomputation; queued/running/failed job counts; coverage status; stale indicator; and windows awaiting coverage when returned. Also show the coarse GET /readiness states: detection activation, current monitoring coverage, processing status, automatic notification activation, manual confirmation availability, and email-provider availability. Explain INSUFFICIENT or UNKNOWN in ordinary language. A low complaint count with incomplete coverage/classification must not appear as low risk. Do not compute processing degradation or provider availability in the browser.

**Drill-downs**
- A chart point opens the corresponding Product Intelligence or Feedback Explorer result using the point's returned product/defect/source filters and UTC bucket.
- A warning row opens Incident Investigation Detail.
- A KPI with a defined count may open the supported list with matching filters. A pending-definition KPI is not clickable as if it had a numeric result.

**API mapping:** GET /readiness; GET /dashboard/summary; GET /dashboard/trends; GET /incidents using only its defined filter subset; GET /products for filter choices; GET /detection-results when displaying stored rationale/coverage results.

### 4.3 Product Intelligence

**Purpose:** Explore a selected product's quality counts and linked supplier/batch context.

**Content and behavior**
- Product search and selection, product identity, and supplier/batch associations returned by the API.
- Count-based trend and defect-category views, affected-batch comparisons, and return-reason views. Keep each unit explicit and separate from returned units.
- Clearly separate fully linked totals from LINKAGE_PENDING product analytics. Never imply that unresolved supplier/batch feedback belongs to a batch.
- Do not display product failure rates or feedback proportions without an API-defined eligible denominator. PB-05 definitions remain pending.
- Data points link to contributing feedback or incident records. Preserve the selected product and compatible date/defect filters.
- Display the API's coverage and linkage context; do not infer risk from an absent or incomplete series.

**API mapping:** GET /products; GET /products/{product_id}; GET /dashboard/trends with product_id and supported filters; GET /feedback for a contributing-record drill-down; GET /incidents for batch-specific incidents.

### 4.4 Feedback Explorer

**Purpose:** Search original review and return feedback and inspect validated classification lineage.

**Content and behavior**
- Paginated, searchable list with source type, source ID, event timestamp, product/supplier/batch linkage state, classification state, validated category/issue labels when present, and linked incident IDs when returned.
- Filters for source type, product, supplier, batch, event-time range, category/defect, and classification state as supported by the API.
- Detail view shows the original record and source lineage, model and contract metadata allowed by the API, structured labels, evidence excerpt, and associated incident(s).
- Distinguish COMPLETED defect, COMPLETED no-defect, NEEDS_REVIEW, queued/in-progress, and failed states. A non-definitive state is not a no-defect label.
- Display only taxonomy values returned by the API. Candidate category and issue-code examples in AI_SPEC are not an approved seed and must not be hard-coded as active filter values.
- Source records are read-only for both application roles. No edit or re-ingest action appears.

**API mapping:** GET /feedback; GET /feedback/{feedback_id}. Use dashboard or product trend endpoints only for aggregate context, not to reconstruct classifications in the browser.

### 4.5 Alerts & Incidents

**Purpose:** Find and prioritize existing incidents.

**Content and behavior**
- Filter by incident status and severity; search/sort by severity, first detection, recent activity, and product as supported by the API.
- Status labels use the API values: NEW, ACKNOWLEDGED, INVESTIGATING, RESOLVED, REOPENED.
- Display product, supplier, batch, defect, severity, first-detected/last-seen times, and recent activity.
- No bulk incident actions in MVP.
- If no incidents exist, use GET /readiness to distinguish inactive detection and insufficient/unknown coverage from an empty result. Show processing degradation separately. INACTIVE detection does not mean zero defects, and an empty list does not prove there is no quality issue.
- Category and source-type filters do not apply to this incident list. Keep the dashboard's broader filter state visible, label those filters as not applied to incident results, and pass only the supported incident filters.
- Repeated evidence updates and recurrence are represented only as persisted by the API; the UI does not decide whether records merge into an incident.

**API mapping:** GET /readiness; GET /incidents; GET /notifications for authorized notification history or status summaries when included in the view.

### 4.6 Incident Investigation Detail

**Purpose:** Show the deterministic rationale, cited feedback, lifecycle history, and available actions for one incident.

**Header and rationale**
- Show incident ID, severity, current status, product/supplier/batch/defect identity, first detection, last seen, and latest update.
- If previous_episode_id is present, show a keyboard-accessible link to the prior episode's investigation detail. Identify it as the linked previous episode; do not infer recurrence relationships beyond the returned ID.
- Show the stored detection rationale: observed distinct feedback count, baseline result, observation and baseline UTC windows, coverage/completeness state, applicable threshold and rule version, and linked evidence references when returned.
- Explicitly label zero baseline, insufficient baseline, and unknown coverage according to the API. Do not substitute a threshold, window, or baseline formula in the client.
- Show evidence uncertainty and linkage status. Do not present a model severity hint as final incident severity.

**Evidence and history**
- Paginate cited observed and baseline feedback. Each record links to Feedback Explorer and retains source ID and timestamp.
- Show an append-only chronological timeline of status transitions, notes, detection updates, and SYSTEM_DECISION events, including cooldown suppression when returned.
- Show notification history and delivery attempts with distinct states: QUEUED, SENDING, ACCEPTED, DELIVERED, BOUNCED, FAILED, OUTCOME_UNKNOWN, and BLOCKED_NO_ROUTE. ACCEPTED means provider acceptance only; it is not delivery confirmation.
- Preserve the actor and timestamp for status changes and notes. Notes are append-only; correction is a new note, not edit/delete.

**Actions**
- Offer only a server-permitted next transition: NEW to ACKNOWLEDGED; ACKNOWLEDGED to INVESTIGATING; INVESTIGATING to RESOLVED; and RESOLVED to REOPENED when permitted, followed by INVESTIGATING. The server remains authoritative for recurrence and transition validation.
- Add Note opens a short note form with the API's length/content validation. Submit with CSRF and Idempotency-Key. Once saved, render the returned immutable event.
- Offer Send Manual Alert only when approved recipient/provider prerequisites are enabled. Otherwise show that notification setup is pending.
- For Admins, show notification retry only when the API's retry_eligibility is true with reason_code ELIGIBLE and the current notification is a known FAILED outcome. The API rechecks eligibility when the command is submitted and returns 409 with the safe current reason if it changed. Never offer retry for OUTCOME_UNKNOWN. Business User responses omit retry eligibility and never show the control.

**Concurrent changes:** Send expected current state/version fields required by the API. On 409, explain that the incident changed, reload its current state, and ask the user to review before taking another action.

**API mapping:** GET /incidents/{incident_id} (includes the latest rationale); GET /incidents/{incident_id}/evidence; GET /incidents/{incident_id}/events; POST /incidents/{incident_id}/status; POST /incidents/{incident_id}/notes; GET /notifications with incident_id; GET /notifications/{notification_id}; POST /admin/notifications/{notification_id}/retry for an eligible Admin retry. The read-only GET /detection-results endpoint is used for dashboard or coverage exploration, not as an incident-specific detail endpoint.

### 4.7 Manual Alert Preview and Confirmation

**Purpose:** Let an authorized user prepare an incident-scoped notification and make an explicit confirmation decision.

**Availability gate**
This flow is enabled only when GET /readiness reports manual_confirmation_state ENABLED and the authorized recipient list contains an eligible recipient. UNKNOWN or DISABLED keeps confirmation unavailable. The readiness response does not expose provider or route configuration. A separate UNAVAILABLE email-provider state is a warning, not evidence that an outbox event cannot be persisted; use persisted API status after confirmation. No real external recipient or supplier address is allowed.

**Flow**
1. Open from a specific incident. Incident facts and evidence references are populated from the server.
2. Load active approved recipients. Permit selection only from returned recipient IDs; no free-form email address input.
3. Let the user edit only the API-supported subject/body fields. Keep incident link and key evidence references fixed. Do not include personal customer details or raw review text in notification content.
4. Request server preview. Show exact resolved recipients, subject, complete body, incident identity, and an explicit “Preview only — nothing has been queued” status.
5. Require a distinct confirmation action. Leaving, refreshing, or closing preview must not confirm or queue a message.
6. On confirmed submission, display the persisted API state. A 202 response means QUEUED. Show later ACCEPTED, DELIVERED, BOUNCED, FAILED, OUTCOME_UNKNOWN, or BLOCKED_NO_ROUTE only when confirmed by the API.
7. If the provider is temporarily unavailable, preserve the returned queued/failed/unknown state. Never report successful delivery without delivery evidence.

**Token/content safety**
Use the opaque preview token and content hash returned by the server; do not invent a client token or treat local state as authorization. Preview-token persistence, expiry, replay, and session binding remain open. If content or recipients change, require a fresh server preview. Do not automatically retry a confirmation after a timeout; reload notification state first.

**API mapping:** GET /readiness; GET /recipients; POST /incidents/{incident_id}/notifications/preview; POST /incidents/{incident_id}/notifications; GET /notifications; GET /notifications/{notification_id}.

### 4.8 Admin CSV Upload and Preview

**Purpose:** Let Admins validate a CSV and explicitly confirm an immutable import.

**Upload and preview**
- Offer templates for reviews, returns, product reference, supplier reference, and batch reference where enabled.
- Before requesting a server preview, show an interactive source-column mapping step for every CSV type, as required by PRD §5.3. Read header names locally only to populate the mapping UI; render them as untrusted text. Admins can map source columns to required and optional canonical template fields; optional source columns may be marked IGNORE. Each required target must be mapped exactly once, and two source columns cannot map to the same target. The server validates the mapping, required targets, header/index binding, file bytes, and rows; a preview missing a required mapping cannot be confirmed.
- Send the selected mapping with the file in POST /admin/ingestion/previews. Keep the validated mapping with the immutable preview identity and verified file hash; do not offer a mapping edit after preview. A changed file or mapping requires a new validated preview. Only Admins can access upload, preview, mapping, and confirmation controls; the backend enforces this restriction.
- For REVIEW and RETURN imports, require an explicit processing mode: HISTORICAL_BATCH or INCREMENTAL_RESPONSES. Do not select a default silently. Reference imports do not use a processing mode.
- Display preview state, file identity/hash summary, parser contract version, total rows, accepted, rejected, duplicate no-op, and conflict counts. Provide paged row outcomes and the UTF-8 formula-safe report when rejected/conflicting rows exist; the report excludes duplicate no-ops and raw feedback.
- Explain that accepted feedback is automatically queued for classification using the selected immutable mode after the import is confirmed. No Business User action can initiate or retry ingestion.
- Confirmation must use the exact preview and verified file hash. If the selected file changes, create a new preview. Never silently confirm a changed file.
- Show linkage state, exact case-sensitive source identifier behavior, duplicate no-ops, and changed-payload conflicts from the server. Timestamps require Z/explicit offsets and at most three fractional digits; the server normalizes to UTC milliseconds. Never overwrite original feedback.
- Display the approved inclusive 20,000,000-byte (decimal 20 MB) file-part limit and 50,000 logical data-record limit after the header; blank records count. Enforce the same limits server-side while streaming/parsing. Accept strict UTF-8 with at most one initial BOM; show safe errors for unsupported/malformed input.

**API mapping:** GET /admin/ingestion/templates/{upload_kind}; POST /admin/ingestion/previews with column_mappings and Idempotency-Key; GET /admin/ingestion/previews/{preview_id}; GET /admin/ingestion/previews/{preview_id}/rows; GET /admin/ingestion/previews/{preview_id}/rejection-report; POST /admin/ingestion/previews/{preview_id}/confirm.

### 4.9 Ingestion Jobs and Error Reports

**Purpose:** Help Admins monitor imports and recover eligible failed work.

**Content and behavior**
- Ingestion job list: upload kind, processing mode where relevant, status, row counts, created/started/completed times, and safe error code.
- Job detail: counts, linked preview, report link, processing state, and relevant retry availability.
- Paged preview outcomes/error report identify row and safe rejection/conflict reason. Do not place raw feedback text, secrets, file paths, or provider payloads in operational messages.
- Show classification/background processing as a separate job family so users can distinguish ingestion from classification, Batch polling, detection, and reconciliation.
- Show the API's explicit retry_eligibility and safe reason code on Admin job detail. Offer Retry only when eligible is true; the server rechecks eligibility at submission and may return 409 with the current reason. Retry preserves source identity and the original processing mode. PP-014-created classification work has `max_attempts=3` total and uses the first two PP-007 delays (5 and 15 seconds); do not imply attempt budgets for other job types or notification providers.
- Allow Admins to inspect and resolve source/mapping conflicts through the explicit reconciliation flow. Explain that a correction can trigger affected recomputation; the UI does not resolve linkage by guessing.
- Show operation summary data for queues, failures, freshness, coverage, outbox, model/version, usage, and estimated cost where returned. Cost is report-only until an approved budget gate exists.

**API mapping:** GET /admin/ingestion/jobs; GET /admin/ingestion/jobs/{job_id}; POST /admin/ingestion/jobs/{job_id}/retry; GET /admin/processing/jobs; GET /admin/processing/jobs/{background_job_id}; POST /admin/processing/jobs/{background_job_id}/retry; GET /admin/reconciliation/conflicts; GET /admin/reconciliation/conflicts/{conflict_id}; POST /admin/reconciliation/conflicts/{conflict_id}/resolve; PUT /admin/feedback/{feedback_id}/linkage; GET /admin/operations/summary; GET /admin/source-coverage; GET /admin/audit-events. Admin job responses carry retry_eligibility; this is a server-derived hint, never a replacement for the server-side retry check.

### 4.10 Admin Settings and User Management

**Purpose:** Present the Admin-only, versioned configuration and user operations exposed by the API.

**Sections**
- **Taxonomy:** list versions, inspect categories/issues, create immutable drafts, activate only a reviewed and approved taxonomy version. Do not hard-code candidate AI_SPEC codes as active values.
- **Detection rules:** list versions, create drafts, show calibration/activation state, and permit activation only after PB-01 and DAI-06 parameters and classification-attempt authority are resolved and the backend accepts activation. Until then display “Pending calibration” and keep active detection unavailable.
- **Recipient directory and groups:** list/manage approved sandbox/capture recipients, groups, and membership history. No arbitrary address entry, supplier group, or real-send setup. The final directory and routing rules remain pending.
- **Notification routing:** list/create immutable inactive route definitions and show the fixed 86,400-second same-severity cooldown. Do not provide a cooldown override. Keep route activation disabled until routing precedence, fallback, provider, and related pending decisions are approved.
- **Users:** list Admin and Business User accounts, provision accounts with a compliant temporary password, deactivate, and Admin-reset a password. Clear write-only password values from UI state after submission; never display or return stored passwords/hashes. The user must change an initial/reset temporary password before normal use. Deactivation/reset revoke active sessions. Admin hands temporary credentials directly to the verified user in person outside ProductPulse; do not email them. Do not add public registration, Viewer role, deletion, or reactivation.
- **Audit and operations:** expose safe configuration/admin audit history and summarized processing status. Do not expose provider secrets, raw feedback in telemetry, or filesystem paths.

**API mapping:** GET/POST /admin/taxonomies; GET /admin/taxonomies/{taxonomy_version_id}; POST /admin/taxonomies/{taxonomy_version_id}/activate; GET/POST /admin/detection-rules; POST /admin/detection-rules/{rule_version}/activate; GET/POST /admin/recipients; PATCH /admin/recipients/{recipient_id}; GET/POST /admin/recipient-groups; PATCH /admin/recipient-groups/{recipient_group_id}; GET/POST /admin/recipient-groups/{recipient_group_id}/members; DELETE /admin/recipient-groups/{recipient_group_id}/members/{recipient_id}; GET/POST /admin/notification-rules; PATCH /admin/notification-rules/{notification_rule_id}; GET/POST /admin/users; GET/PATCH /admin/users/{user_id}; POST /admin/users/{user_id}/password-reset; GET /admin/audit-events; GET /admin/operations/summary; GET /admin/source-coverage; GET /health. GET /readiness is read-only for both roles.

## 5. KPI, chart, filter, and drill-down contract

### 5.1 KPI handling

The PRD and API contract define the following named values for Overview: analysed feedback records, classification coverage, unique defect-bearing feedback records, return records, and returned units when available. PB-05 leaves active warnings, critical warnings, and products at risk undefined. The dashboard must display these as pending when the API returns null/PENDING_DEFINITION; the UI must not supply its own calculation.

For every visible metric, show the API-provided unit, definition status, and any applicable numerator/denominator, window, and freshness. Do not rename returned units to return records or vice versa. Do not infer sales denominators.

### 5.2 Chart behavior

- Render chart values and breakdowns from GET /dashboard/trends only.
- Show metric title, unit, UTC bucket range, legend labels, and filter context.
- Provide a text summary or accessible tabular equivalent for chart values.
- When coverage is INSUFFICIENT or UNKNOWN, mark values as incomplete/unknown per the API and do not style them as validated low-risk results.
- Distinguish LINKED, LINKAGE_PENDING, MIXED, and NOT_APPLICABLE context where returned.
- A chart click can only drill into a list endpoint with a matching supported filter. It must not imply that the chart's aggregate is itself a list of incidents.

### 5.3 Shared filter semantics

Use API filter names and values: from_utc, to_utc, product_id, category_code, supplier_id, batch_id, logical_defect_id, severity, incident_status, and source_type, subject to each endpoint's schema. Dashboard summary, trends, and GET /incidents use the common incident filter names where supported. GET /incidents supports from_utc, to_utc, product_id, supplier_id, batch_id, logical_defect_id, severity, and incident_status; it does not support category_code or source_type. Those two filters remain applied to dashboard aggregates and feedback/product results but must be visibly marked as not applied to incident results. This panel-specific subset follows PRD §6.2: the warning list receives its API-supported filters and carries only compatible applied filters into drill-downs. Date ranges are half-open: inclusive start and exclusive end. The active filter summary should be visible on each result page and carried into compatible drill-downs.

## 6. Automatic refresh and responsive behavior

- Overview summary and trend aggregates refresh every 30 seconds while the Overview is open. Provide a manual Refresh action and show last successful refresh time.
- Do not treat the polling interval as an ingestion, classification, detection, or notification SLA.
- Avoid overlapping refresh requests. A failed poll retains the last result as visibly stale and offers a manual retry.
- No automatic polling cadence is defined for detail, list, or Admin job screens. Those screens load on entry and provide an explicit refresh control; any additional cadence requires a product/operational decision.
- Desktop is the primary layout. At narrower widths, collapse navigation, stack KPI cards and filters, and preserve access to all actions without horizontal page overflow.
- Keep tables usable on narrow screens through a responsive row/card presentation or a contained horizontal scroller with keyboard support. Do not hide status, identity, or action information.
- Preserve a legible manual alert preview and confirmation summary on small screens.

## 7. Loading, empty, stale, and error states

Implement shared state patterns with page-specific wording:

| State | UI treatment |
|---|---|
| Initial loading | Page-level skeletons or progress indicators; maintain heading/context; announce completion to assistive technology. |
| Refreshing | Keep current values visible with a refresh indicator; prevent duplicate refresh actions. |
| Empty result | State the scope and filters that returned no rows. Distinguish no records from no results in the selected range. |
| Pending processing | Show queued/in-progress state and last successful processing time; do not call it complete. |
| Insufficient or unknown coverage | Explain that the baseline/result cannot be interpreted as zero or low risk. |
| Stale data | Keep last successful values visible, mark them stale, show the timestamp, and provide Refresh. |
| Page/API error | Show safe API detail and request ID where provided; offer a retry only for reads or an explicitly idempotent operation. |
| Forbidden | Show an access-denied page/state and hide the operation after session refresh; never treat a client route guard as sufficient. |
| Not found | Explain that the selected resource is unavailable and provide a safe return path. |
| Partial ingestion | Show accepted/rejected/conflict/duplicate counts and direct the Admin to row outcomes and the rejection report. |

## 8. Validation, authorization, and error handling

- Send authenticated requests with the session cookie. Include the session-bound CSRF token on state-changing requests as required by the API.
- Use backend authorization for every protected request. On 401, clear stale client session state and return to Login. On 403, do not render protected data or continue the action.
- Use client validation for immediate feedback and backend validation as final authority. Do not duplicate detection, import, recipient, or lifecycle business logic in React.
- Render the API problem title, safe detail, stable code, and request_id where available. Never display raw exception, provider payload, secret, session token, filesystem path, or API key.
- For 409 incident conflicts, reload and ask the user to review the new state before retrying. For preview hash conflicts, require a new preview. For idempotency conflicts, do not repeat with the conflicting key.
- For 422 errors, associate field errors with form fields; CSV row validation belongs in the preview table/report, not a generic form error.
- For 413/415 upload errors, show the server's size/type message and preserve the selected file for correction where safe.
- For 429, respect Retry-After when present. Do not start a retry loop.
- For generic 5xx or 503, show a redacted message and request ID. For notification operations, reload persisted notification state before reporting an outcome after a timeout.
- For destructive or externally visible configuration changes, show a review step with the exact object/version and consequences returned by the API. All final authorization and validation remain server-side.

## 9. Accessibility and reusable UI components

### 9.1 Accessibility requirements

- All navigation, filters, forms, dialogs, tables, pagination, and actions are keyboard operable with visible focus.
- Use semantic headings, landmarks, form labels, button names, and table headers. Associate validation text with its input.
- Never encode severity, coverage, linkage, or job state by color alone. Pair color with readable text and a status icon/shape where useful.
- Charts require a title, units, axis/legend labels, a concise text interpretation, and an accessible data table or equivalent. Tooltips cannot be the only way to discover values.
- Announce loading completion, form errors, confirmation results, and asynchronous state changes through appropriate live regions without repeatedly announcing unchanged polling results.
- Maintain readable contrast, scalable text, logical focus order, and dialog focus management. Confirm/cancel dialogs return focus to their trigger.
- Feedback text is untrusted content; render as text, never as executable markup.

### 9.2 Reusable UI components

Keep the initial component set small and shared across pages:

- ApplicationShell and RoleNavigation
- PageHeader and Breadcrumbs
- FilterBar and AppliedFilterSummary
- KpiCard with unit/definition/freshness slots
- ChartPanel with text/table alternative
- StatusBadge and CoverageNotice
- DataTable with pagination, empty/loading/error states
- FreshnessSummary and LastUpdated
- FeedbackRow and FeedbackDetail
- IncidentSummary, IncidentTimeline, and NotificationStatusPanel
- FormField, InlineValidation, ConfirmDialog, and Toast/Announcement region
- UploadDropzone, PreviewSummary, RowOutcomeTable, and ErrorReportLink
- AdminConfigurationSection and AuditEventList

These are conceptual UI responsibilities, not a component-library selection.

## 10. User flows and UI acceptance criteria

### Flow A: Sign in and review quality

1. User submits existing credentials.
2. UI establishes the session from the API and opens Overview.
3. User reviews KPI definitions, freshness, filters, and charts.
4. User drills to a product, feedback list, or incident with compatible filter context.

**Acceptance criteria**
- UI-AC01: Login succeeds only through the session API; the browser stores no session token, and no registration path is shown.
- UI-AC02: Admin and Business User see shared business navigation; only Admin sees Admin navigation.
- UI-AC03: Every KPI and chart displays its unit and relevant time/filter context. Pending-definition values are not rendered as zero.
- UI-AC04: Dashboard summary and trends refresh on the 30-second cadence and manual refresh. A failed refresh marks prior values stale.
- UI-AC05: Incomplete classification, insufficient/unknown coverage, and LINKAGE_PENDING are visible and cannot be misrepresented as low risk or fully linked incidents.
- UI-AC24: Overview and incident empty states use GET /readiness to distinguish detection activation, coverage, processing degradation, automatic-notification activation, manual-confirmation availability, and email-provider availability. UNKNOWN remains explicit and is never presented as ACTIVE, HEALTHY, or evidence of zero product defects; INACTIVE detection is never presented as zero defects; the UI never infers readiness or exposes configuration details.

### Flow B: Investigate and update an incident

1. User opens an incident from Alerts & Incidents or a dashboard warning.
2. User reviews deterministic rationale, evidence, coverage, source links, and timeline.
3. User performs one permitted status transition or appends a note.
4. UI reloads the returned incident/event state and displays it chronologically.

**Acceptance criteria**
- UI-AC06: Incident pages show server-provided severity, status, evidence, windows, thresholds, and rule version without client recomputation.
- UI-AC07: Invalid status transitions are not offered; the API remains authoritative and a stale 409 requires reload/review.
- UI-AC08: Notes are append-only, attributed, timestamped, and cannot be edited or deleted in the UI.
- UI-AC09: Notification history distinguishes queued, accepted, delivered, bounced, failed, unknown, and blocked states. ACCEPTED is never labelled delivered.
- UI-AC10: Admin retry is shown only when the API exposes eligibility for a known-failed event with its blocking cause corrected. The server rechecks eligibility and returns a safe reason on 409. OUTCOME_UNKNOWN is not automatically resent.
- UI-AC25: A later linked episode shows a link to the returned previous_episode_id and opens that episode through the incident detail API.

### Flow C: Preview a manual incident alert

1. User opens the incident-scoped composer when the approved recipient directory and sandbox provider are enabled.
2. User selects returned recipients, edits supported content, reviews the complete server preview, then explicitly confirms.
3. UI reports the persisted notification state and refreshes status from the API.

**Acceptance criteria**
- UI-AC11: Arbitrary addresses and supplier recipients cannot be entered.
- UI-AC12: Previewing or leaving the composer creates no notification and sends nothing.
- UI-AC13: Confirmation is unavailable before recipient/provider approval and configuration. Once enabled, a 202 is shown as QUEUED, never as delivered.
- UI-AC14: If confirmation times out, the UI reloads notification status and does not blindly submit a second send.

### Flow D: Admin imports data and handles errors

1. Admin downloads a template, uploads a file, and maps source columns to canonical fields or explicitly marks them IGNORE.
2. Admin reviews the immutable server preview and explicitly chooses a feedback processing mode when required.
3. Admin confirms the exact preview/hash and tracks the created job.
4. Admin reviews row errors, rejection report, and eligible retry options.

**Acceptance criteria**
- UI-AC15: Only Admin has upload, preview, confirm, and ingestion retry controls; Business User access is denied server-side with no artifact/job created.
- UI-AC16: Feedback import mode is explicit; reference imports have no mode; retries preserve original mode.
- UI-AC17: Confirmation uses the exact preview and verified hash. Changed bytes require a new preview.
- UI-AC18: Duplicate no-op, conflict, accepted, and rejected rows are distinct. Changed payload never overwrites original feedback.
- UI-AC19: Job and error screens distinguish ingestion, classification, detection, and reconciliation work and show safe errors.
- UI-AC26: Admin mapping supports required and optional targets; every required target appears exactly once, no target is mapped from two source columns, and optional source columns may be marked IGNORE. A missing required mapping blocks confirmation. The validated mapping is bound to the immutable preview identity and verified file hash; changes require a new validated preview. Business Users cannot access ingestion or mapping.
- UI-AC27: Admin job/notification retry controls use server-provided eligibility and safe reason codes. A retry request is rechecked server-side; a 409 refreshes the reason and never triggers an automatic repeat.

### Flow E: Admin manages settings and users

1. Admin reviews existing versioned configuration and audit history.
2. Admin creates a draft or provisions/deactivates a user where the API allows it.
3. Admin activation is attempted only after dependent approval gates are resolved.

**Acceptance criteria**
- UI-AC20: Taxonomy candidates are not shown as active unless returned by an active approved version.
- UI-AC21: Detection and route activation remain blocked/pending until their explicit calibration and provider/routing dependencies are approved.
- UI-AC22: User management supports Admin/Business User create, deactivate, and Admin-assisted temporary-password reset; no self-registration or Viewer option appears. Temporary passwords are handed directly to the verified user outside ProductPulse.
- UI-AC23: Configuration and operational pages omit secrets, raw provider payloads, and filesystem paths.
- UI-AC28: User provisioning/reset sends only a write-only policy-compliant temporary password; the UI clears it after submission, never exposes stored passwords/hashes, and indicates required first-login change.

## 11. Consistency review and pending decisions

The reviewed requirements align on Admin-only ingestion, server-side RBAC, backend-only AI/email integrations, UTC event-time handling, count-based analytics, source drill-down, append-only incident history, and a 30-second Overview refresh cadence.

The following items remain unresolved and constrain this UI:

1. **Detection activation:** PB-01 thresholds/minimum counts and DAI-06 coverage scope/completeness/calibration remain pending. The selected authoritative completed classification attempt is also unresolved. DETECTION_SPEC v1.1 explicitly keeps automatic detection and automatic notifications disabled until the required policy and calibration are approved.
2. **Metric definitions:** PB-05 leaves active warnings, critical warnings, and products at risk undefined. Render API null/PENDING_DEFINITION as pending, not as a number.
3. **Alert behavior:** ALERT_SPEC v0.3 is Draft. Cooldown is fixed at 86,400 seconds per incident/severity across routes with escalation bypass, but timestamp anchor, same-severity re-crossing, treatment of failed/blocked sends, severity decreases, and recurrence/cooldown interaction remain pending. UI must not infer these edge rules.
4. **Routing and provider:** Final recipient directory, routing precedence/group combination, fallback, route-key semantics, concrete sandbox/local capture provider, callbacks, and provider verification are open. Automatic and manual send controls must remain gated until the required approvals/configuration.
5. **Manual preview lifecycle:** Preview-token persistence, expiry, replay, and session binding remain open. The UI consumes only the server token/hash and requires a fresh preview after content or recipient changes.
6. **Retry and recovery:** PP-007 approves worker reconciliation every 60 seconds and eligible retry delays of 5/15/45 seconds. `max_attempts=3` applies only to PP-014-created classification work; other job-type budgets and provider-specific notification limits/error mapping remain under their owning decisions. The API design baseline exposes safe retry eligibility and ineligibility reason codes. `OUTCOME_UNKNOWN` is not automatically resent.
7. **Readiness contract:** ARC-08 approves the role-visible coarse readiness endpoint and its informational-only semantics. Exact degradation thresholds and provider-health assessment parameters remain pending for the operations specification; the API must return UNKNOWN until readiness can be established. INACTIVE detection is not zero defects. The endpoint does not expose Admin configuration or authorize actions, and this approval does not activate detection or notifications.
8. **CSV mapping contract:** PRD §5.3 explicitly requires mapping. DAI-08 approves Admin mapping to required and optional targets, uniqueness, optional-source IGNORE, confirmation blocking for missing required targets, and immutable preview/hash binding. These semantics are captured in the approved conditional API and Data Model design baselines; dependent behavior remains subject to documented implementation prerequisites.
9. **Filter consistency:** The warning list uses the API-supported subset allowed by PRD §6.2. The UI visibly marks category_code and source_type as unapplied to incident rows and carries only compatible filters into drill-downs.
10. **Contract approval:** API_SPEC v1.5.2 and Data Model v1.5.2 are approved as conditional design baselines; API v1.5.1 and Data Model v1.5.1 were their previous approved versions. Remaining implementation and unrelated decision gates still apply.
11. **Frontend choices:** Exact chart conventions and design tokens remain open; approved authentication/recovery behavior is defined in SECURITY.md and API_SPEC.yaml.
12. **Upload contract:** The 20,000,000-byte file-part limit, 50,000 logical-row cap, encoding, timestamp, field-length, parser-version, and report behavior are approved and shown consistently with API_SPEC.yaml. Synthetic uploads, previews, row reasons, and rejection reports remain available through the capstone period without automatic per-artifact expiry; removal occurs through documented reset/reseed after backup and reference/audit checks under OPS-03.
13. **Performance:** Dashboard p95 and post-classification display targets are targets to validate, not guarantees. The 30-second poll is not a processing SLA.

No incompatible requirement was identified for the UI workflows described here. The PRD describes automatic warning/email scope, while the current Detection clarification explicitly holds activation pending calibration; this approved design baseline preserves the gate and does not treat the broader PRD scope as evidence that the feature is active.

