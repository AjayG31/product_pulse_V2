# ProductPulse Incident and Alert Specification

**Version:** 0.3  
**Status:** Draft for cross-document review; not approved for implementation  
**Date:** 22 November 2026  
**Scope:** Incident lifecycle, automatic and manual notification behavior, durable delivery, audit, and API/database alignment.

## 1. Purpose and approval boundary

This specification turns approved ProductPulse requirements and user-authorized alert and PP-007 operational decisions into a downstream incident and email design. `docs/PRD.md` remains the product requirements source of truth. The current baseline includes PRD v1.7, Decision Register v2.0, Architecture v1.5, API_SPEC.yaml v1.5.2 and DATA_MODEL.md v1.5.2 (Approved — Design Baselines, subject to documented conditions), UI_SPEC.md v0.4.1 (Approved — Design Baseline, subject to documented conditions), AI_SPEC.md v1.0, and DETECTION_SPEC.md v1.1 (Draft clarification; v1.0 remains its Approved design baseline).

This document does not activate detection thresholds, approve recipient routing, select an email provider, authorize real email, or claim that the unresolved choices below have product-owner approval. Approved behavior is labeled **Approved**. An implementation choice that needs a decision is labeled **Open**. Automatic notification activation remains gated by the calibration and operational dependencies in §18.

The design is deliberately limited to the single-retailer, synthetic/non-production MVP and one SQLite-backed worker. It introduces no broker, second database, production mail path, supplier mail, or new user role.

## 2. Normative invariants

1. Detection counts, baselines, severity, incident eligibility, and notification eligibility are deterministic backend decisions. An AI classification or `severity_hint` cannot create an incident, select severity, or trigger email.
2. Only a qualifying `CURRENT_MONITORING` detection result may be applied to incident state or create automatic notification intent. A historical recomputation is evidence only.
3. An incident is batch-specific and requires resolved `(product_id, supplier_id, batch_id, logical_defect_id)` identity. `LINKAGE_PENDING` records cannot create product-only incidents or automatic notifications.
4. Non-definitive classifications are excluded from confirmed defect counts. DAI-06's approved coverage policy determines whether classification and source coverage are sufficient for a detection result to qualify. Until the required coverage policy and calibration are approved, automatic detection and notification remain disabled.
5. Automatic and manual sends use only the Admin-managed approved internal/sandbox directory and the approved sandbox/local capture adapter. No arbitrary addresses, supplier recipients, real external sends, or customer personal details are allowed in MVP.
6. A notification-triggering incident update and its required outbox intent and recipient snapshots commit atomically in SQLite. Provider I/O occurs after commit and outside all database transactions.
7. Persisted provider acceptance is `ACCEPTED`, not proof of delivery. Exactly-once external email delivery is never promised.

## 3. Incident identity, creation, and severity

### 3.1 Identity and creation

An incident represents one episode for one stable, resolved batch-specific defect cluster. The cluster identity is `(product_id, supplier_id, batch_id, logical_defect_id)` and its `cluster_id` is reused across repeated evaluations. Display names, model output, issue-name similarity, or unresolved identifiers cannot establish identity.

An incident is created only when an eligible, calibrated rule produces a qualifying severity in a current monitoring result and the result is applied successfully. Auto-created incidents start in `NEW`. Trend-only results and `NO_TRIGGER` results do not create incidents. A result that DAI-06 classifies as insufficient for the required detection decision cannot create an automatic incident or notification. Non-definitive classifications are excluded from confirmed defect counts; their presence does not itself override the approved DAI-06 coverage decision. `LINKAGE_PENDING` evidence cannot qualify an incident.

Automatic detection remains disabled until the required source/classification coverage policy and detection calibration are approved. The authoritative-classification-attempt selection dependency must also be resolved before counts can be considered dependable.

There is at most one open incident per cluster. New qualifying evidence updates its evidence and counts rather than creating a duplicate. A decrease in observed count does not automatically resolve an incident.

### 3.2 Severity

Persisted incident severities are `MEDIUM`, `HIGH`, and `CRITICAL`. Severity comes from the versioned deterministic detection rule. The PRD's numeric minimums and ratios are provisional hypotheses; PB-01 remains Pending Calibration and this specification does not make them defaults.

When an eligible current result raises the severity of an existing episode, update the incident and append a `DETECTION_UPDATED` or `SYSTEM_DECISION` event containing the detection result ID and before/after severity in the same transaction. Detection result history remains immutable.

DETECTION_SPEC.md does not define automatic severity decreases. Until a product decision defines that behavior, a lower result must not silently lower the incident severity or automatically resolve it. Record the result and preserve the incident history. The severity-decrease policy remains open.

### 3.3 Lifecycle and recurrence

The server permits only the approved transition sequence:

| Current state | Permitted next state | Notes |
|---|---|---|
| `NEW` | `ACKNOWLEDGED` | Stale or conflicting actions are rejected and audited. |
| `ACKNOWLEDGED` | `INVESTIGATING` | No shortcut transition is added. |
| `INVESTIGATING` | `RESOLVED` | Store the resolution timestamp. |
| `RESOLVED` | `REOPENED` | Authorized review or qualifying recurrence. |
| `REOPENED` | `INVESTIGATING` | No direct resolution shortcut. |

Every accepted transition records the actor/system, UTC timestamp, before/after state, and idempotency key where supplied. Rejected stale/conflicting actions have an auditable result. Notes are append-only events; corrections are new notes.

For a qualifying recurrence, compute elapsed time from the stored `resolved_at`: at or before 30 × 24 hours reopens that incident; later recurrence creates a new episode linked through `previous_episode_id`. Preserve prior events and episodes. The boundary is approved under PB-03 and AC22.

How notification cooldown history interacts with a reopened incident or a linked new episode is not fully resolved by PB-04. Do not infer a cooldown reset or carry-over policy without that decision; see §18.

## 4. Automatic notification eligibility and cooldown

### 4.1 Trigger eligibility

The following core trigger behavior is approved by PRD §9.4–10.1, PB-04, and Architecture §14:

| Detection/incident outcome | Automatic email behavior |
|---|---|
| Informational/trend-only or `NO_TRIGGER` | No incident email. |
| `MEDIUM` | May create/update an incident; no automatic email. |
| First eligible `HIGH` or `CRITICAL` threshold crossing | Create a durable automatic notification intent, subject to cooldown and approved route resolution. Sandbox/provider readiness affects delivery state, not incident or outbox creation. |
| Eligible increase to a higher severity, including `HIGH` to `CRITICAL` | Create an escalation intent; it bypasses the same-severity cooldown. |
| Same-severity update during the fixed cooldown | Suppress the repeated automatic send; retain detection and incident updates. |
| Historical recomputation, insufficient coverage, or evidence from `LINKAGE_PENDING` records | No automatic incident update and no automatic notification. |

Thresholds are evaluated only by calibrated deterministic rules. Non-definitive classifications never contribute to confirmed counts; DAI-06 determines whether classification/source coverage is sufficiently complete. A model hint, unsupported rate, or model-generated numeric claim cannot qualify a trigger. Automatic detection and notifications cannot be enabled until applicable PB-01 and DAI-06 decisions are approved and the active rule configuration is calibrated.

### 4.2 Fixed cooldown and escalation bypass

For MVP, the same-severity automatic notification cooldown is exactly **86,400 seconds (24 hours) per incident and severity, shared across all notification routes**. It is not a separate cooldown per route or recipient group, and an Admin cannot change the duration. A higher-severity escalation bypasses the cooldown. Manual notifications are separate events: they neither consume nor suppress the automatic cooldown and do not change incident severity.

The cooldown must be enforced against durable SQLite state, not a process-local timer. Stable outbox event identity prevents retries of one logical trigger from creating duplicate local events. A blocked/no-route intent is not a provider send. When a qualifying incident update is suppressed by cooldown, append an `incident_events` `SYSTEM_DECISION` event with a stable event key, detection result ID, severity, and result code `AUTO_NOTIFICATION_SUPPRESSED_COOLDOWN` in the same transaction as the incident update and detection application. Do not create a delivery event for the suppressed notification.

**Open trigger semantics:** The approved documents do not settle whether an unchanged `HIGH`/`CRITICAL` incident may generate another automatic notification after 24 hours without a newly defined threshold re-crossing, or how severity decreases and re-crossings reset the comparison. The precise cooldown timestamp anchor and treatment of failed/blocked sends are pending clarification in this specification. A repeated detection poll is not by itself a new send trigger.

## 5. Manual alert preview, confirmation, and authorization

Manual notifications are incident-scoped and available to authenticated `ADMIN` and `BUSINESS_USER` actors. The backend enforces role, CSRF/session protection, incident access, and recipient authorization on every command. Hiding controls in the frontend is not authorization.

The required sequence is:

1. The user selects one or more active recipient IDs from the approved directory and supplies editable authored subject/body text within the API limits.
2. `POST /incidents/{incident_id}/notifications/preview` resolves the IDs, prepares the complete incident-scoped message, and returns an opaque preview token and content hash. Previewing, refreshing, or abandoning does not create an outbox event and cannot send.
3. The user explicitly confirms the displayed preview using `POST /incidents/{incident_id}/notifications`, the preview token/hash, and an `Idempotency-Key`.
4. The backend revalidates the actor/session, incident, token binding, hash, active recipient authorization, and exact preview content before atomically snapshotting the exact message/recipients and queuing one `MANUAL` event.
5. The API returns `202` with the durable notification state. `QUEUED` means the confirmation is stored for processing; it does not mean accepted or delivered. A provider call is later performed by the worker.

If the sandbox is temporarily unavailable, confirmation still commits the outbox event and exact snapshots and returns `202 QUEUED`; provider failure and bounded retry are handled independently. If the sandbox is unconfigured or disabled, confirmation still records the confirmed event durably; the worker marks its queued attempt `FAILED` with a safe configuration error and no provider call, and an Admin may retry it after the sandbox is restored if it is eligible. Neither response nor stored state claims delivery.

The token is bound to the actor/session, incident, exact content, recipient snapshot, and preview identity. Reuse of the same confirmation key and same preview returns the original notification. Reuse of a key for a different command is a conflict. A new preview is required for changed content or recipients. Exact token storage/expiry and repeat-preview behavior remain a Security/API implementation dependency.

Manual confirmation never modifies severity, bypasses an authorization check, or blocks an automatic escalation. The final confirmed subject/body and exact recipients are retained in the notification record as required by PRD; abandoned preview content is not persisted as a send. The message always retains the system-supplied incident identity, evidence references, and fixed incident link.

## 6. Approved recipient directory and automatic routing

### 6.1 Directory boundary

The MVP directory is Admin-managed and contains approved internal/sandbox/capture addresses only. There is no free-form recipient entry, supplier directory, arbitrary external address, or real sending. Address changes create a new directory entry; deactivation preserves history. Group membership changes are timestamped and historical membership is retained.

Manual composition can select only active directory entries. At confirmation, current permission is rechecked and exact address/display-name snapshots are copied to the notification. Subsequent directory, group, or membership changes cannot rewrite a queued notification's recipients.

### 6.2 Automatic routing requirements

PRD §9.4 requires Admin-approved mapping by product/category/supplier and an approved internal quality-team sandbox fallback. If no approved route or fallback exists, the system must not send and must surface an operational error. No supplier is an eligible route.

The rule table is versioned and Admin-managed. A route-definition change creates a new inactive version; activation/deactivation is audited. Every rule uses the fixed cooldown. `routing_scope`, `routing_key`, `recipient_group_id`, `fallback_group_id`, and `threshold_severity` must be snapshotted/referenced by the API and data model. For each automatic notification, preserve the actual selected rule/version, scope/key, group(s), route role (matched or fallback), and membership provenance. Preserve provenance per recipient even if a route resolver de-duplicates an address. This records the resolution result without approving precedence, group combination, or de-duplication policy.

**Open routing decisions:** The approved documents do not choose product-versus-category-versus-supplier precedence, whether multiple matching groups combine, how duplicate recipients are de-duplicated across groups, whether a fallback is used only on no match or also on an empty/inactive primary group, the exact quality-team fallback group, or the scope-key encoding. Until these decisions and the sink are approved, route activation is blocked. If a future evaluation cannot resolve one approved route, fail closed, create a visible `BLOCKED_NO_ROUTE` record, and send nothing; do not guess at precedence.

## 7. Notification templates and evidence rules

### 7.1 Automatic template

Use a versioned server-side template. The automatic subject/body must include the incident ID, product, supplier, batch, defect identity/display name, severity, observed distinct feedback-record count, baseline count/status and normalized baseline when valid, first-detected UTC time, a concise evidence summary, and a secure incident link. The message must identify the relevant evaluation window or evaluated time so counts are interpretable.

Values must come from the applied detection result and incident snapshot. A complete zero baseline is represented as “No prior observed complaints”; never display an infinite ratio. Do not include unsupported product failure/return rates, inferred sales denominators, raw customer feedback, personal customer details, or the model's severity hint. Insufficient baseline results cannot produce an automatic incident/email.

### 7.2 Manual template

The manual preview includes the user's authored content and a fixed system-generated incident/evidence block with the incident link and key verified evidence. The preview is the exact message later confirmed. A user cannot use recipient text to introduce arbitrary addresses; the recipients are selected by directory ID. Preserve exact confirmed subject, body, template/content version, recipient snapshots, actor, incident, timestamps, and idempotency identity.

Manual text must be validated against API size limits and safely encoded for the provider's message format. Subject handling must reject or normalize header-control characters according to the selected provider adapter. Provider formatting and content sanitization details are implementation dependencies; never insert raw feedback into a message.

## 8. SQLite transactional outbox and idempotency

### 8.1 Atomic local transaction

For a qualifying current detection result, the application transaction must re-read the pending result and current incident/episode, confirm its fingerprint is still current, and atomically:

- create/update/reopen the incident and append the idempotent incident event;
- evaluate the automatic notification decision and append a `SYSTEM_DECISION` event if cooldown suppresses the send; otherwise create the required outbox intent;
- when an outbox intent is created, snapshot the resolved approved recipients, recipient-to-group/membership provenance, route/content version, and route-resolution result;
- create the first `QUEUED` delivery-attempt row when a route is resolved (a `BLOCKED_NO_ROUTE` row has no delivery attempt);
- set `detection_results.incident_application_state=APPLIED`.

For a manual notification, the confirmation transaction atomically creates the `MANUAL` outbox row, exact recipient snapshots, actor/content snapshot, confirmation identity, and initial `QUEUED` delivery attempt. A preview alone creates none. If any local database write fails, the transaction rolls back. A pending detection application remains recoverable and an existing `result_key` must not skip recovery.

If no approved route can be resolved, preserve the incident/detection application and record the notification decision as `BLOCKED_NO_ROUTE` with no provider call. This is consistent with the existing status contract and PRD's no-send/surface-error rule. The incident itself must not be rolled back just because notification configuration is missing. If a route is valid but the sandbox/provider is unavailable, persist the incident and required `QUEUED` outbox event atomically; delivery health does not suppress the incident.

The single worker polls durable jobs/outbox every 5 seconds and claims one item at a time in a short `BEGIN IMMEDIATE` transaction. The claim carries an owner token and a 5-minute lease, renewed every 60 seconds in a separate short transaction conditioned on that token, including while a long provider call is active. Stale-owner writes are rejected. The worker commits before email-adapter I/O and records the attempt outcome in a separate short transaction. No provider call, retry sleep, or network callback occurs within a transaction. SQLite uses a 5-second busy timeout and up to 2 additional `SQLITE_BUSY` retries after rollback. API and worker share the same SQLite file.

### 8.2 Stable identity

- `notification_outbox.event_key` is unique and stable for one logical automatic or manual event. Reprocessing one detection result/application action must reuse the same automatic key; repeated API confirmation must reuse the manual event key.
- `request_idempotency_key` is unique for manual confirmation. A key reused with different actor/incident/preview/content conflicts.
- Retries of a provider call remain attempts for the same notification event; they do not create new notification events.
- A distinct eligible threshold event may have its own stable event key. Cooldown eligibility decides whether it is queued; the exact re-crossing rule remains open under §4.2.
- Every durably scheduled dispatch has a numbered `notification_delivery_attempts` row. Initial routed events create a `QUEUED` attempt in the incident/outbox transaction; every bounded retry and accepted Admin retry appends a new `QUEUED` attempt. The worker marks that row `IN_PROGRESS` before adapter I/O and finalizes it once as `ACCEPTED`, `FAILED`, or `OUTCOME_UNKNOWN`. An idempotent Admin retry replay does not append a second attempt.

Database uniqueness and local transactions provide idempotent persistence. They do not make an external email side effect exactly-once.

## 9. Email sandbox adapter and delivery states

All sending is backend-only through an adapter boundary. ARC-05 approves a sandbox or local capture sink for MVP and prohibits real external delivery. The concrete local-versus-hosted sink, provider, credentials/configuration, callback support, and provider-specific idempotency capability are still open. No production credentials or real mailbox should be configured by this design.

The API/database delivery state vocabulary is:

| State | Meaning |
|---|---|
| `QUEUED` | Durable local intent exists; no current provider call is in progress. |
| `SENDING` | Worker owns the send claim and a provider attempt is in progress. |
| `ACCEPTED` | Adapter/provider accepted the request and returned an acceptance result; not proof of delivery or reading. |
| `DELIVERED` | A trusted provider callback or sink result explicitly reports delivery, if supported. |
| `BOUNCED` | A trusted provider callback explicitly reports a bounce, if supported. |
| `FAILED` | A permanent validation/configuration/dispatch error or exhausted approved retry budget prevents further automatic attempts until eligible Admin recovery. |
| `OUTCOME_UNKNOWN` | The request may have left the process, but the result cannot establish acceptance or failure. |
| `BLOCKED_NO_ROUTE` | No approved route/fallback was available; no provider call was made. |

Provider attempt outcomes and the current outbox state are separate: an attempt may be `FAILED` and the outbox may return to `QUEUED` for an approved retry. `ACCEPTED`, `DELIVERED`, and `BOUNCED` retain their timestamp distinctions. A callback may update the outbox state only after provider-specific authenticity and event-correlation checks are defined.

### 9.1 Retry and failure handling

OPS-02 approves bounded automatic retry for transient mail-provider errors, terminal failure visibility, Admin recovery/retry, idempotency, and scheduled reconciliation. PP-007 approves 5-, 15-, then 45-second retry delays for eligible retries and a 60-second worker reconciliation interval. Each bounded automatic retry appends a new `QUEUED` delivery-attempt row; prior attempt rows remain immutable. Permanent validation errors are not retried. Provider-specific notification attempt limits, retryable error taxonomy, and retry-eligibility mapping remain pending under PP-008 and must be reconciled with the selected sink/provider before notification integration. Do not retry indefinitely.

Each failure records a safe error code and redacted summary. When the approved retry budget is exhausted, persist `FAILED` and expose it to authorized users/Admin operations. An authenticated Admin-only `POST /admin/notifications/{notification_id}/retry` operation retries eligible known-failed events. It requires session/CSRF protection and an `Idempotency-Key`; it keeps the original notification ID, event key, content, recipients, and history, appends a new `QUEUED` delivery-attempt row, writes an audit event, and returns the same notification on an idempotent replay. The worker changes that row to `IN_PROGRESS` before adapter I/O. It does not retry `OUTCOME_UNKNOWN` or a permanent validation failure. A retry is eligible only when the prior outcome is known not to have been accepted and its blocking cause is corrected. Error taxonomy and exact retry budget remain pending. A replay with the same idempotency key returns the same attempt and does not append another row.

### 9.2 Uncertain send recovery

On process interruption or adapter timeout after a request may have left the process, persist the attempt as `OUTCOME_UNKNOWN` and the outbox as `OUTCOME_UNKNOWN`; do not relabel uncertainty as a known failure or acceptance. If the active provider call is long-running, renew its 5-minute lease every 60 seconds using a separate short transaction; no renewal or result update may succeed for a stale owner token. On an expired `SENDING` lease with a still-`QUEUED` attempt, clear the stale lease and return the outbox to `QUEUED` because no provider call started. An abandoned `IN_PROGRESS` attempt becomes `OUTCOME_UNKNOWN` and is never automatically resent without provider verification or a separately approved policy. Expose the state in history and operations views.


## 10. Audit logging and notification history

`incident_events` is the append-only incident timeline for lifecycle changes, notes, detection updates, cooldown suppression decisions, and other system decisions. `notification_outbox` is the durable message/event record; its routing provenance snapshot and `notification_recipients` preserve selected route/group/membership lineage and exact approved recipients; `notification_delivery_attempts` preserves every send attempt and safe outcome. `audit_events` records Admin retry requests and system lease reconciliation in addition to Admin recipient/group/routing configuration changes. It does not duplicate the incident timeline or raw provider payloads.

For every message preserve event ID/key, notification type, trigger kind, incident, severity snapshot, rule/content version, exact recipient and content snapshots, actor for manual messages, created/confirmed/attempt timestamps, provider message ID when returned, status, and safe error category. Routing configuration activation/deactivation and recipient/group/membership administration must be auditable. Keep notification history through the capstone period under OPS-03.

The read API returns notification status and safe attempt summaries to authenticated users. Audit snapshots must not contain email addresses, arbitrary subject/body text, provider payloads, raw feedback, secrets, session/CSRF values, filesystem paths, or raw exception details. Exact confirmed email content is stored only in the protected notification record because PRD requires it; it is not copied into generic audit snapshots or logs.

## 11. Historical recomputation and late arrivals

Late-arriving feedback, classification-state changes, linkage reconciliation, coverage changes, and rule/policy changes enqueue recomputation for the affected event-time windows and resolved clusters. Only validated definitive completed classifications contribute to confirmed defect counts; pending, failed, needs-review, or otherwise non-definitive classifications do not count as complaints. DAI-06's approved coverage policy, not the presence of any individual non-definitive record by itself, determines whether the detection result has sufficient source/classification coverage. Recompute by immutable UTC boundaries and preserve earlier detection results, evidence, incidents, events, and notification history.

Historical recomputation is evidence-only. Even if it produces `TRIGGERED`, it cannot create/update/reopen an incident or enqueue an automatic notification. Only a separate qualifying current monitoring result under the active calibrated rule may affect incident or automatic notification state. A late arrival that changes the current rolling window can affect the next normal current monitoring result; it cannot cause a historical result to send retroactively.

Rule activation causes historical recomputation as `HISTORICAL_RECOMPUTE`; the next normal current monitoring cycle evaluates under the activated rule. Existing cooldown and trigger-edge semantics still apply and require the decisions in §4.2/§18.

## 12. Suppression and eligibility gates

Automatic incident application is suppressed when:

- DAI-06 evaluates required source/classification coverage as insufficient for the detection decision.
- Evidence is `LINKAGE_PENDING`, lacks product/supplier/batch agreement, or otherwise cannot establish the resolved cluster identity.
- The result is `HISTORICAL_RECOMPUTE`, `NO_TRIGGER`, or trend-only.

Automatic notification intent is suppressed or blocked when:

- An eligible High/Critical notification falls within the incident/severity cooldown. Retain the incident update and append a `SYSTEM_DECISION` suppression event in the same transaction; do not create a delivery event.
- No approved routing destination/fallback is available. Preserve incident application and record the notification outcome as `BLOCKED_NO_ROUTE` with no provider call.

Non-definitive classifications are excluded from confirmed defect counts. DAI-06's approved coverage policy determines whether the remaining data is sufficiently complete. DAI-06's required scope/completeness policy and calibration are still pending; automatic detection and notification must remain disabled until approved. Classification-attempt authority also remains unresolved and must be settled before counts are dependable. Sandbox/provider unavailability is a delivery failure, not an incident-eligibility suppression condition: preserve the incident and outbox intent, then record/retry delivery separately. There is no real-email fallback.

## 13. API contract alignment

API_SPEC.yaml v1.5.2 is an Approved — Design Baseline, subject to its documented implementation conditions; v1.5.1 was the previous approved API version. ARC-08 approves a role-visible readiness projection and DAI-08 approves the CSV mapping contract; neither decision nor conditional design approval activates detection or notification behavior.

| Contract surface | Alert behavior |
|---|---|
| `GET /incidents`, `GET /incidents/{incident_id}`, `/evidence`, `/events` | Read batch-specific incidents, verified evidence, and append-only timeline/history. |
| `POST /incidents/{incident_id}/status`, `/notes` | Server-side transition validation, optimistic concurrency, CSRF, and idempotent audit. |
| `GET /recipients` | Active approved entries for manual composition only. |
| `POST /incidents/{incident_id}/notifications/preview` | Complete preview; no outbox row and no send. Preview token design/expiry remains open. |
| `POST /incidents/{incident_id}/notifications` | Confirm exact preview, validate authorization, queue one manual event; `202` means `QUEUED`. |
| `GET /notifications`, `GET /notifications/{notification_id}` | Paginated notification status/history with content/recipient snapshots and safe attempts. |
| `POST /admin/notifications/{notification_id}/retry` | Admin-only, idempotent retry of an eligible known-failed notification; same event identity and history, new worker attempt. |
| `/admin/recipients`, `/admin/recipient-groups`, memberships, `/admin/notification-rules` | Admin-managed directory, immutable route definitions, membership history, fixed cooldown; route activation waits for unresolved decisions. |

The API status enum matches DATA_MODEL: `QUEUED`, `SENDING`, `ACCEPTED`, `FAILED`, `DELIVERED`, `BOUNCED`, `OUTCOME_UNKNOWN`, `BLOCKED_NO_ROUTE`. Manual confirmation uses `Idempotency-Key`; notification history distinguishes acceptance from delivery. Backend authorization is required even where an endpoint only lists recipient records.

### 13.1 Contract gaps for downstream review

- The approved conditional API baseline exposes an Admin-only retry_eligibility projection with safe reason codes; UI_SPEC v0.4.1 defines the client control. PP-007 approves the shared 5/15/45-second retry-delay sequence and 60-second reconciliation interval. Provider-specific notification limits and retry eligibility still depend on PP-008 and sink selection.
- API_SPEC.yaml has no provider callback operation. If the selected sink reports delivery/bounce callbacks, specify authentication, correlation, replay handling, and outbox update semantics in a provider-specific contract. `DELIVERED`/`BOUNCED` must remain unused when callbacks are unsupported.
- Preview token persistence/expiry and repeated-preview behavior are explicitly unresolved between API_SPEC and SECURITY.md. No preview persistence table is defined in DATA_MODEL.md.
- The route schema permits `routing_scope` and `routing_key` but its vocabulary, encoding, precedence, and fallback behavior are unresolved. The `BLOCKED_NO_ROUTE` data status exists, but route activation is gated pending the decision.
- DATA_MODEL/API now preserve selected route/group/membership provenance with each notification; precedence, group combination, and address de-duplication remain open.
- API_SPEC v1.5.2 identifies Decision Register v2.0 and is Approved — Design Baseline, subject to its documented conditions; v1.5.1 was the previous approved contract.

## 14. Data model contract alignment

DATA_MODEL.md §4.7–4.8 provides the logical records used here:

- `defect_clusters`, `detection_results`, `detection_evidence`, and `incidents` define eligibility, evidence, current/historical application, and episode identity.
- `incident_events` stores lifecycle, note, detection-update, and system-decision history.
- `recipient_groups`, `recipients`, `recipient_group_members`, and `notification_rules` define the managed directory and versioned route references.
- `notification_outbox` stores the event, state, route/content version, event/request identities, and canonical resolved-routing provenance snapshot.
- `notification_recipients` snapshots exact recipients and their source group/membership IDs; `notification_delivery_attempts` stores immutable per-call outcomes.
- `audit_events` covers configuration/admin actions under the approved safe-field allow-list.

Constraints to preserve include unique `event_key`, unique manual confirmation key, per-incident/per-severity cooldown shared across all routes at exactly 86,400 seconds, MANUAL actor/confirmation fields, AUTOMATIC null actor/confirmation fields, SENDING lease tuple, ACCEPTED/DELIVERED/BOUNCED timestamps, and OUTCOME_UNKNOWN without acceptance/delivery timestamps. One open incident per cluster and the immutable 30-day episode relation remain enforced. Retry reuses the notification row/event key and is audited; each accepted retry appends a new delivery-attempt row.

The current model can represent the approved boundary. PP-007 sets the 5-minute notification lease, 60-second renewal/reconciliation cadence, and shared retry-delay sequence. Route scope semantics, provider-specific notification attempt limits, callback behavior, provider verification for uncertain outcomes, retry reason-to-policy mapping, and external idempotency remain open under PP-008. DATA_MODEL v1.5.2 is an Approved — Design Baseline subject to documented conditions; this document does not authorize a migration.

## 15. Security and error handling

- Keep provider credentials only in protected backend environment/secrets management. Never expose them to a browser, log them, or include them in API responses.
- Never send real external email or supplier email in MVP. Use only approved internal/sandbox directory entries and the configured capture sink.
- Enforce authentication, role, CSRF, incident scope, recipient status, token binding, and idempotency on the backend at preview and confirmation.
- Treat incident fields and user-authored message text as untrusted input. Never execute instructions in feedback; do not put raw feedback into notifications, logs, traces, audit snapshots, or safe error summaries.
- Use parameterized SQL and short write transactions. Do not expose provider payloads, raw exception text, addresses in generic audit snapshots, or file paths in errors.
- Return the API's consistent problem responses: `401` for invalid session, `403` for authorization, `404` for unavailable resource, `409` for stale incident/preview/idempotency conflict, `422` for invalid content, and redacted generic `5xx` for internal/provider configuration failures. Do not reveal whether an unapproved external address exists.
- A missing route/fallback produces no send and a visible operational failure (`BLOCKED_NO_ROUTE`); invalid/inactive recipient selection is rejected before confirmation. Sandbox/provider outage does not roll back an incident or confirmed event; the API reports only persisted state, never successful delivery without evidence.
- A database failure before commit leaves no incident/outbox partial write. A worker/provider failure after commit leaves a durable state and safe attempt record for retry/recovery.
- Retain synthetic notification/audit evidence through the capstone period. Production retention, deletion, and real-send policies are outside this specification.

## 16. Verification scenarios

These are specification-level scenarios for future implementation tests; no application code or tests are created here.

1. An eligible first current `HIGH` result creates one incident and one stable automatic outbox event in the same SQLite transaction; a replay does not duplicate either.
2. A current result escalating `HIGH` to `CRITICAL` creates an escalation event despite an active same-severity cooldown; the incident event records before/after severity.
3. A `MEDIUM` result creates/updates an incident but never queues an automatic email.
4. A repeated same-severity event inside 86,400 seconds across any route does not create a second send; append `SYSTEM_DECISION` cooldown suppression event. Admin changes cannot alter the cooldown. Verify the cooldown anchor and after-expiry behavior once clarified.
5. A historical result that crosses a threshold updates stored detection evidence only; it cannot create/change an incident or notification.
6. A DAI-06-insufficient result or `LINKAGE_PENDING` row cannot create an automatic incident or notification. Non-definitive classifications are excluded from confirmed counts; the approved DAI-06 policy determines completeness. Reconciliation queues recomputation without retroactive mail from a historical result.
7. A missing/ambiguous route or fallback results in a visible `BLOCKED_NO_ROUTE` record and no provider call; route precedence test fixtures wait for approval of routing semantics.
8. Manual preview returns the exact final content and recipient snapshot but creates no outbox row. Abandoning it sends nothing. Confirmation during sandbox outage persists a notification and reports `QUEUED` or a recorded failure without claiming acceptance/delivery.
9. Manual confirmation requires a valid authorized actor, exact token/hash, active approved recipient IDs, CSRF, and idempotency key; replay returns the same notification, while a changed payload/key reuse conflicts.
10. A Business User cannot create/change recipient directory, groups, memberships, or routes; an unauthorized recipient ID cannot be used for manual confirmation.
11. One accepted adapter result maps to `ACCEPTED`, not `DELIVERED`; delivery/bounce states appear only after supported, validated sink signals.
12. Known transient provider errors follow a bounded configured retry budget; permanent validation errors are not retried; exhausted work is visible as `FAILED`. An eligible failed event can be retried by Admin with the same event identity and a new delivery attempt.
13. An expired lease with a still-`QUEUED` attempt is safely returned to `QUEUED`; an expired lease with an abandoned `IN_PROGRESS` attempt becomes `OUTCOME_UNKNOWN`. Unknown outcomes are not automatically resent and are not eligible for Admin retry without provider verification or an approved policy.
14. Concurrent/stale incident transitions return a conflict and preserve an auditable attempt; the one-open-incident-per-cluster constraint remains intact.
15. A late arrival recomputes affected stored windows and preserves prior results; only a subsequent qualifying current result can trigger an incident/email.
16. Audit/log review confirms exact message content is retained only in the protected notification record, while generic audit/log data excludes raw feedback, addresses, message bodies, secrets, provider payloads, and raw exception text.

## 17. PRD requirement and acceptance-criteria traceability

| Requirement | Coverage in this specification |
|---|---|
| PRD F08/F11; §§9, 10; AC09, AC20–AC21, AC24 | Deterministic current-result eligibility, incident creation, count exclusions, DAI-06 coverage gate, and activation block (§§3–4, 12). |
| PRD F13/F17; §§9.3, 11–12; AC15, AC22 | Approved incident states, audit, notes, concurrency, and 30-day recurrence (§3). |
| PRD F14; §§9.4, 10; AC10–AC11 | Stable identity, exact fixed cooldown shared across routes, escalation bypass, suppression audit, and pending edge cases (§4, §8). |
| PRD F12; §§6.8, 10.2; AC13–AC14 | Incident-scoped preview, explicit confirmation, role/recipient checks, sandbox-unavailable behavior, and idempotency (§5, §13). |
| PRD §10.1; AC10–AC11 | Internal/sandbox routing, no supplier contact, routing provenance, evidence-based template, and route failure handling (§§6–7). |
| PRD §10.3; AC10–AC13; OPS-02 | Durable outbox, delivery states, uncertain-send recovery, and no exactly-once guarantee (§§8–10). Admin retry is specified under OPS-02; the PRD has no standalone retry acceptance criterion. |
| PRD §§11–12; AC12, AC15 | Incident, event, recipient, notification and evidence API/data alignment (§§10, 13–14). |
| PRD §13.2–13.3; AC01, AC13–AC16 | Backend RBAC, protected secrets, redacted errors, durable worker/outbox, recovery, and failure visibility (§§8–10, 15). |
| PRD §15; AC19–AC22, AC24 | `LINKAGE_PENDING`, baseline/coverage handling, recurrence, and exclusion of non-definitive classifications from confirmed counts (§§3, 7, 11–12). |
| PRD F15; AC16 (ingestion-pipeline warning only) | Notification delivery status/history is exposed through notification and operations views. AC16 does not define notification retry; the Admin retry operation comes from approved OPS-02, and no standalone PRD retry acceptance criterion exists (§§9–10, 13). |

## 18. Unresolved decisions and implementation dependencies

The following are not approved by this specification and must remain visible in implementation planning:

| Item | Status / effect |
|---|---|
| PB-01 thresholds and minimum counts | Pending Calibration. Blocks incident/automatic-email activation. PRD 5/10/20 and 2×/3×/5× values remain hypotheses. |
| DAI-06 coverage scope, interval combination, classification-completeness gate/parameters | Method approved; parameters Pending Calibration. Non-definitive classifications are excluded from confirmed counts; this policy determines completeness. Automatic detection and email stay disabled until required coverage policy/calibration is approved. |
| Completed-classification attempt authority | Unresolved pre-implementation dependency across AI_SPEC, DATA_MODEL, DETECTION_SPEC. Do not count multiple completed attempts until aligned and approved. |
| Notification event semantics after a same-severity update and cooldown | PB-04 core is approved. Repeat/re-cross trigger, exact cooldown timestamp anchor, treatment of failed/blocked sends, and severity-decrease behavior remain pending clarification. |
| Cooldown across recurrence | PB-03 episode boundary is approved; PB-04 recurrence/cooldown interaction remains unresolved. |
| Recipient directory and fallback target | SEC-03 approves sandbox-only Admin-managed directory; PRD §19.1 still requires formal approval of the final directory/fallback. No concrete inbox is selected. |
| Concrete mail sink/provider, credentials, callback support | ARC-05 approves a sandbox/local capture boundary; provider and local-versus-hosted sink are not selected. No real external delivery. |
| Uncertain-send recovery and provider idempotency | Approved recovery rule: expired SENDING with no attempt returns to QUEUED; abandoned IN_PROGRESS becomes OUTCOME_UNKNOWN; no automatic resend unless provider verification or a separately approved policy permits it. Provider lookup support and verified-outcome handling remain open; exactly-once cannot be claimed. |
| Retry limits and reason mapping | API_SPEC v1.5.2 specifies safe eligibility reason codes and UI_SPEC v0.4.1 consumes them. PP-007 approves 5/15/45-second retry delays and 60-second reconciliation. Provider-specific notification attempt limits, retryable-error taxonomy, and reason-to-policy mapping remain under PP-008. |
| Preview-token persistence, expiry, replay, and session binding details | Open between API_SPEC and SECURITY.md; no preview table exists in DATA_MODEL. |
| Provider callback authentication/correlation | Open and provider-dependent; no callback route is defined in API_SPEC. |
| Route resolution and provenance | The actual selected rules, groups, and memberships are snapshotted. Precedence, group combination, duplicate-address handling, empty-group fallback, and scope-key encoding remain open; route activation must wait. |
| DATA_MODEL.md v1.5.2 review | Detection and alert-recovery model is an Approved — Design Baseline, subject to documented conditions; v1.5.1 was the previous approved version. DAI-08 mapping semantics, ARC-08 readiness projection, and PP-007 operational policies remain recorded. |
| API_SPEC v1.5.2 review | This Approved — Design Baseline includes Admin notification retry eligibility, the ARC-08 readiness projection, routing provenance, DAI-08 interactive column mapping, and PP-007 worker/SQLite policy; documented implementation conditions remain. API_SPEC v1.5.1 was the previous approved contract. |
| Evaluation gates EV-01/EV-02/EV-03 | Pending Calibration; required before final held-out evaluation, not resolved here. |
| SQLite worker lease/`SQLITE_BUSY` and email-provider operation details | PP-007 approves the 5-second busy timeout, 2 additional `SQLITE_BUSY` retries, 5-minute lease, 60-second renewal, and out-of-transaction provider calls. Provider-specific notification retry limits, sink/routing, verification, and idempotency remain open under PP-008. |

### Implementation gate

Before implementing an alert feature, approve this specification and the dependent route, provider, retry, preview-token, and uncertainty decisions; approve/review the needed DATA_MODEL/API contract changes; and resolve detection calibration and classification-attempt authority. Detection/email activation also requires the applicable calibrated rule and coverage policy. This document creates no application code, migrations, tickets, configuration activation, or send authorization.

## 19. Cross-document consistency review

This draft was checked against AGENTS.md, PRD v1.7, DECISION_REGISTER.md v2.0, ARCHITECTURE.md v1.5, DATA_MODEL.md v1.5.2, API_SPEC.yaml v1.5.2, UI_SPEC.md v0.4.1 (Approved — Design Baselines subject to documented conditions), DETECTION_SPEC.md v1.1 (Draft clarification; v1.0 remains the Approved design baseline), AI_SPEC.md v1.0 (Approved design baseline), and TECH_STACK.md v1.2.0.

The corrections align classification exclusions and DAI-06 coverage gating, the 30-day recurrence, per-incident/per-severity cross-route cooldown and escalation bypass, manual confirmation, sandbox-only routing, atomic SQLite persistence, history, and uncertain-delivery recovery. A cooldown suppression is an audited `SYSTEM_DECISION`. Sandbox/provider unavailability does not suppress an incident or durable outbox event. Non-definitive classifications do not count as confirmed defects; DAI-06 decides coverage sufficiency, and automatic detection remains disabled pending approval/calibration.

The remaining gaps are intentional: severity decrease/re-crossing and cooldown timestamp anchor, route precedence and fallback details, provider/sink selection, provider-specific notification retry limits/error mapping, preview-token lifecycle, and provider verification for uncertain outcomes. PP-007 has fixed the shared 5/15/45-second retry-delay sequence and 60-second reconciliation interval; this does not set notification-provider attempt limits. ARC-08 and DAI-08 are Approved decisions; exact readiness degradation thresholds and provider-health assessment parameters remain pending for the operations specification. API_SPEC v1.5.2 and DATA_MODEL v1.5.2 are Approved — Design Baselines subject to documented conditions. This Alert Specification remains Draft and is not approved for implementation.
