# ProductPulse Deterministic Detection Specification

**Version:** 1.1  
**Status:** Draft clarification pending review; v1.0 remains the Approved — Design Baseline  
**Prior approval date:** 21 November 2026  
**Clarification date:** 21 November 2026  
**Requirements source:** [PRD](PRD.md) v1.6  
**Related decisions:** Decision Register v1.4; PB-01 Pending Calibration; PB-03 Approved; PB-04 Approved with notification edge cases open; PB-05 definitions pending; PB-06 Approved; PB-09 Approved; DAI-04 Approved; DAI-06 methodology confirmed, parameters Pending Calibration; EV-01/02/03 Pending Calibration  
**Related contracts:** [Architecture](ARCHITECTURE.md) v1.3 Approved; [Data Model](DATA_MODEL.md) v1.4 Approved — Design Baseline (conditional; v1.1 was previous approved baseline); [API](API_SPEC.yaml) v1.4.0 Approved — Design Baseline (conditional; v1.1.0 was previous approved version); [Alert Specification](ALERT_SPEC.md) v0.2 Draft; [AI Specification](AI_SPEC.md) v1.0 Approved — Design Baseline

## Approval boundary and terminology

The PRD remains the product-requirements source of truth. The Product Owner approved v1.0 as a conditional design baseline on 21 November 2026. This v1.1 draft records the user-authorized clarification that non-definitive classifications are excluded from confirmed defect counts, DAI-06 determines coverage sufficiency, and automatic detection remains disabled until required coverage policy and calibration are approved. This clarification does not activate automatic detection or approve pending calibration values. The unresolved authoritative classification-attempt selection rule is a pre-implementation dependency for classification counting.

Labels used below:

- **Approved requirement** means the behavior is already required by the PRD or an Approved decision.
- **Provisional hypothesis** means a PRD demonstration value that must be calibrated and versioned before held-out evaluation or production-like use.
- **Pending calibration** means the exact value or interpretation is unresolved under PB-01 or DAI-06. This specification may describe a candidate for review, but it is not an approval.
- **Proposed implementation detail** means a practical deterministic mechanism offered for review. It does not change business behavior or resolve a pending decision.

No detector may create incidents or automatic email notifications while required historical coverage is insufficient. An uncalibrated rule version may be stored as a draft, but it must not be activated to create incidents or automatic emails. API_SPEC.yaml specifies a calibration-pending conflict for rule activation. The six design decisions approved on 21 November 2026 are reflected below and in PB-09; they do not approve PB-01 or DAI-06 calibration values.

## 1. Detection objectives, scope, and architecture

The detector identifies emerging, batch-specific product-defect clusters using validated classifications and deterministic Python/SQL calculations. It supplies reproducible evidence for dashboards and incidents. It does not use an LLM to count complaints, calculate baselines, choose severity, create incidents, or decide email eligibility.

In scope:

- Defect counts for REVIEW and RETURN feedback, keeping feedback records distinct from returned units.
- Cluster identity across taxonomy versions through explicit stable logical-defect mappings.
- UTC event-time observation and baseline windows, explicit coverage assessment, and explainable outcomes.
- Durable result/evidence persistence, cluster recomputation, incident creation/update, and recomputation after linkage reconciliation or late arrivals.
- Dashboard summaries and incident rationale derived from persisted detection results.
- Evaluation on synthetic planted episodes and comparison with a frozen sentiment/negative-review baseline.

Out of scope:

- Product-only incidents from LINKAGE_PENDING feedback.
- Model-generated numerical decisions, sentiment-based production alerts, product failure rates without valid denominators, and automatic supplier contact or external remedial action.
- Historical bulk reclassification after taxonomy changes unless separately specified and approved.
- Notification-provider retry and uncertain-send semantics owned by ALERT_SPEC.md.

The worker flow is:

1. A validated classification or linkage/coverage change schedules durable recomputation work for affected cluster identities.
2. The worker reads the eligible feedback, applicable classifications and labels, and coverage declarations for a fixed evaluation instant T.
3. Deterministic code calculates counts, coverage state, normalized baseline, ratio where valid, and the highest qualifying severity using one immutable rule version.
4. Persist an immutable result, coverage snapshot, and evidence references. A current qualifying result starts with incident application pending; a separate short SQLite transaction applies it idempotently to incident state and, when required by ALERT_SPEC, writes the notification outbox intent and recipient snapshot atomically. Historical recomputations never apply incident or notification changes.
5. Dashboard/API reads aggregate persisted results and source facts. Browser code does not run detector formulas.

OpenAI classification runs earlier in the backend worker. Only validated completed classification outcomes enter confirmed defect counts. Provider calls are never part of detection calculations or held inside a database transaction.

## 2. Defect cluster identity and counting eligibility

An incident-capable defect cluster has the natural identity:

**(product_id, supplier_id, batch_id, logical_defect_id)**

The corresponding defect_clusters row has a stable opaque cluster_id and a unique constraint on this tuple. Repeated evaluation reuses that row; the service must not derive cluster identity from display names, category names, model output, or issue-code similarity.

logical_defect_id is the stable semantic identity assigned by the approved, versioned taxonomy mapping. DAI-04 permits reuse across taxonomy versions only when a human-reviewed mapping establishes semantic equivalence. A changed defect meaning receives a new logical_defect_id. The detector never merges IDs by name similarity and never accepts a logical_defect_id from model output.

A feedback record is eligible for a given logical-defect cluster only when all of the following hold:

1. It is a persisted REVIEW or RETURN feedback row with immutable source identity and UTC event_time_utc.
2. It has a validated, completed classification outcome representing a definitive defect (has_defect=true, needs_review=false).
3. A validated PRIMARY or SECONDARY classification label maps to the cluster's logical_defect_id and includes the required specific issue code.
4. The feedback has resolved product, supplier, and batch identities, linkage_status=LINKED, and the batch's product/supplier keys agree with the feedback.
5. Its event_time_utc is inside the window being evaluated.

Count one distinct feedback record at most once in a given cluster and period, even if it repeats the same issue in its text or multiple labels map to that logical defect. If PRIMARY and SECONDARY labels map to the same logical_defect_id, count the feedback once and cite PRIMARY in detection_evidence. Use SECONDARY only when no valid PRIMARY label maps to that cluster. A record may contribute once to each of two distinct logical-defect clusters when it has validated distinct defect labels. The counting unit is a feedback record, not the return_quantity.

Only an applicable completed classification is counted. The AI specification preserves immutable attempts, but the cross-document contract does not state which completed attempt is authoritative if one feedback record has more than one completed attempt. The authoritative selection rule is unresolved and is a pre-implementation dependency: do not implement classification counting across multiple completed attempts until the rule is explicitly approved and aligned across AI_SPEC.md, DATA_MODEL.md, and this specification. Using the highest attempt_number is only a candidate for review, not an approved rule. Attempts must never be counted additively.

## 3. Product, supplier, and batch linkage; PB-06

Batch-specific cluster creation requires all four natural-key values. Linkage is taken from valid source identifiers and approved reference mappings/reconciliation. The detector does not infer or fabricate supplier or batch identifiers.

For LINKAGE_PENDING records:

- Preserve the feedback row when product_id is valid.
- Include completed defect classifications in clearly labeled product-level pending analytics, separately from fully linked defect totals. Pending-defect breakdowns may be grouped by product and logical_defect_id; these are not incident-capable clusters.
- Exclude these records from supplier/batch cluster counts, cluster evidence, incident creation, severity, and automatic notification eligibility.
- Do not create a product-only defect_clusters row or incident, even if the product and defect label are known.
- When Admin reconciliation changes linkage to LINKED, append the linkage event/audit evidence and schedule recomputation for the newly resolved batch cluster. Preserve source text, source identity, event time, and originally reported IDs.

These are Approved PB-06 rules. They supersede any looser interpretation of product-level analytics in the PRD: product-level visibility for unresolved links does not authorize product-only incidents or emails.

## 4. Event-time windows and historical baseline

All detector timestamps are UTC. For one evaluation instant T:

| Period | Half-open interval | Meaning |
|---|---|---|
| Observed | [T − 7 days, T) | Distinct eligible complaints in the recent 7-day window |
| Baseline | [T − 35 days, T − 7 days) | Distinct eligible complaints in the immediately preceding 28 days |

The observation and baseline windows are event-time windows, not import, ingestion, classification-completion, or dashboard-filter windows. Store T as evaluated_at and persist the four exact interval boundaries. Dashboard chart bucketing does not change these detector windows. Use the same boundaries for all comparisons and define intervals as inclusive at start, exclusive at end.

For eligible records:

- observed_count is the number of distinct feedback records in the observed interval for this cluster.
- baseline_28d_count is the number of distinct feedback records in the baseline interval for this cluster.
- normalized_baseline_7d = baseline_28d_count / 4.
- For a usable nonzero baseline, observed_to_baseline_ratio = observed_count / normalized_baseline_7d, equivalently 4 × observed_count / baseline_28d_count.

Use exact integer/rational comparison for threshold decisions where possible (for example, compare 4 × observed_count with ratio_threshold × baseline_28d_count) so floating-point rounding cannot change a severity boundary. Persist the normalized value and ratio in the contract's numeric fields for explanation. Do not calculate a ratio when the baseline is zero or insufficient.

The fixed 7-day observation and preceding 28-day baseline are PRD behavior. The API rule schema fixes these window lengths at 7 and 28 days; a change requires an approved contract/specification update. Detection evaluation cadence is not set by these windows and remains an operational scheduling choice.

## 5. Coverage assessment and insufficient history

### Approved behavior

DAI-06 approves the methodology, not its numeric or scope parameters:

- Coverage is declared explicitly for UTC event-time intervals and an applicable source scope.
- Absence of a coverage declaration is UNKNOWN, never complete coverage or zero complaints.
- Missing intervals and declared INCOMPLETE or UNKNOWN intervals cannot establish a usable baseline.
- Late arrivals and new coverage declarations trigger recomputation of affected windows.
- If the required baseline coverage is insufficient, show the state and trend evidence, but do not create an automatic incident or automatic warning email.

### Candidate coverage algorithm for review

The existing source_coverage table stores source_type, scope_type, scope_key, half-open interval, completeness status, provenance, and declaration time. Overlapping declarations remain separate. Until DAI-06 parameters are approved, the following is a candidate algorithm and must not be treated as an approved scope policy:

1. The applicable detector source set is REVIEW and RETURN, because both contribute to the PRD complaint population. A source type may be omitted only if an approved rule explicitly defines that source as outside its population.
2. For each applicable source type, select declarations matching the chosen detection scope exactly. Do not treat an empty scope key, wildcard, AGGREGATE, or different scope as a match unless an approved convention explicitly defines it.
3. A baseline is complete only if the union of COMPLETE intervals covers every instant of [T − 35 days, T − 7 days) for every applicable source type with no gaps. Any uncovered interval, or any applicable INCOMPLETE/UNKNOWN declaration that prevents proving complete coverage, makes the baseline INSUFFICIENT.
4. Preserve every coverage declaration used in the evaluation in detection_result_coverage, including the assessed status. Do not overwrite prior coverage snapshots when declarations later change.
5. A fully covered baseline with zero eligible complaints is SUFFICIENT_ZERO. A fully covered baseline with one or more eligible complaints is SUFFICIENT_NONZERO.

DAI-06 must approve the scope granularity (for example, retailer-wide coverage per source type versus a narrower scope), how conflicting/overlapping declarations combine, the evidence required to declare an interval COMPLETE, and whether AGGREGATE coverage is permitted. These are not resolved by the candidate algorithm above.

Source-input coverage and classification completeness are separate assessments. For each evaluated period, classification completeness is computed over the persisted feedback records in the applicable source/scope cohort: `COMPLETE` means every eligible feedback record has a definitive validated completed classification; `INCOMPLETE` means one or more records remain queued, in progress, retryable/terminal failure, or `NEEDS_REVIEW`; `UNKNOWN` means that the applicable cohort cannot be enumerated. Store assessed and complete record counts. These states are facts, not a numeric coverage score.

The immutable coverage-policy version determines whether incomplete classification completeness makes the required baseline insufficient. No policy may interpret unresolved classification as `NO_DEFECT` or as a zero complaint. A pending-to-definitive classification transition, including a definitive no-defect result, changes the assessment and fingerprint and therefore invalidates a prior insufficient result. The exact source scope, any minimum classifier-completion policy, and how classification completeness combines with source_coverage remain DAI-06 Pending Calibration; automatic incident/email processing stays disabled until that policy is approved. Do not infer a numeric threshold.

For INSUFFICIENT results, persist decision_state=INSUFFICIENT_COVERAGE, coverage_state=INSUFFICIENT, and null severity and ratio. Retain known counts/evidence as partial evidence only, with the coverage state visible. No automatic incident/outbox event may reference that result. A provisional trend-only display may be offered with an explicit insufficient-baseline label; it has no validated severity.

## 6. Detection formulas, minimum counts, and severity

The rule engine uses deterministic versioned configuration. It evaluates all configured levels and chooses the highest qualifying level. For a usable nonzero baseline, a level qualifies only if both its minimum observed count and its minimum observed-to-baseline ratio are met. For a complete zero baseline, it uses that level's count-only gate; the ratio criterion is null and no infinite multiplier is generated.

The PRD's initial values are **provisional hypotheses only**:

| Level | Usable nonzero baseline | Complete zero baseline | Result |
|---|---|---|---|
| Informational / trend-only | No Medium threshold qualifies | Fewer than 5 observed complaints | Trend only; no incident or email |
| Medium | At least 5 observed complaints and at least 2× normalized baseline | At least 5 observed complaints | Create/update incident; no automatic email |
| High | At least 10 observed complaints and at least 3× normalized baseline | At least 10 observed complaints | Create/update incident; automatic sandbox email under PRD/PB-04 |
| Critical | At least 20 observed complaints and at least 5× normalized baseline | At least 20 observed complaints | Create/update priority incident; priority sandbox email under PRD/PB-04 |

When the baseline is complete and nonzero, an example Medium predicate is observed_count >= configured minimum and 4 × observed_count >= configured ratio × baseline_28d_count. Equality qualifies. For a zero baseline, only the configured minimum observed count applies. For insufficient coverage, no severity predicate is evaluated as a validated decision.

The values above are not defaults and must not be silently activated. PB-01 remains Pending Calibration. Calibrate only on development planted scenarios, record the final immutable rule configuration/version, receive the required product-owner decision, and freeze it before held-out evaluation. Until then, rules remain drafts and rule activation stays blocked as specified in API_SPEC.yaml. Any approved config must preserve the PRD's deterministic count-based behavior, zero-baseline count-only treatment, and highest-qualifying-severity rule unless the PRD is formally changed.

The model's severity_hint is advisory only. It cannot raise or lower final severity, trigger an incident, or make an event Critical. Safety-related content may be surfaced for human review; a safety override would require separate design, validation, and approval.

## 7. Cluster recomputation and incident create/update rules

Recomputation is cluster-scoped. New definitive classification, linkage reconciliation, coverage changes, late-arriving feedback, and activation of a calibrated rule version enqueue affected work. Recompute counts from the eligible source rows and labels rather than incrementing a mutable counter; retries therefore cannot double-count. Persist each evaluation as an immutable detection_results snapshot with its evidence and coverage declarations. Rule activation must not rewrite earlier results.

An evaluation is tagged `CURRENT_MONITORING` or `HISTORICAL_RECOMPUTE`. `CURRENT_MONITORING` is created by the normal monitoring schedule with T fixed for that cycle before calculation. Recalculation of any previously stored T/window, or catch-up work for an elapsed monitoring cycle, is `HISTORICAL_RECOMPUTE`. Only a qualifying `CURRENT_MONITORING` result may be applied to incident state or create a required automatic notification outbox event. Rule changes recompute affected historical windows as `HISTORICAL_RECOMPUTE`; the next normal monitoring cycle evaluates its current window under the active rule. A historical result, even if it is `TRIGGERED`, is evidence only and cannot by itself create, reopen, update, or notify an incident.

For a result with a validated MEDIUM, HIGH, or CRITICAL trigger:

1. If an open incident exists for the cluster (NEW, ACKNOWLEDGED, INVESTIGATING, or REOPENED), update that incident's detection evidence and relevant counts/source links; do not create a duplicate. If the new qualifying result has higher severity, update the incident severity and append an auditable incident event containing the result ID and before/after severity. Severity decreases are not specified here and remain a PB-04/ALERT_SPEC decision. Do not auto-resolve it when counts later decrease.
2. If no incident is open and no prior resolved episode exists, create a NEW incident for the cluster.
3. If the latest resolved episode was resolved at time R and the new qualifying detection is at or before R + 30 days, reopen that same incident, clear its current resolved_at, and record the decision and prior resolution time in incident_events.
4. If more than 30 days elapsed after the stored resolution timestamp, create a new linked episode whose previous_episode_id points to the most recent episode. Preserve old incidents and events.
5. Compute the recurrence boundary from the persisted resolution timestamp. Exactly 30 × 24 hours is within the approved window; later is a new episode.

When the selected episode is existing (already open or reopened within the approved recurrence window), the higher-severity update rule applies to its stored severity. Record the severity before/after in the idempotent incident event. This does not add lifecycle transitions or settle lower-severity handling.

The 30-day recurrence rule is Approved by PB-03 and must not be changed by calibration. At most one open incident per cluster is enforced by the existing partial unique index. When a qualifying current result reopens or creates an episode, preserve the existing lifecycle and apply the severity rule above. Incident changes, audit event, detection-result application-state update, required notification outbox event, and recipient snapshot are committed in one SQLite transaction as required by ARC-07.

A NO_TRIGGER result never creates an incident. An existing incident is not automatically resolved by a NO_TRIGGER result or decreasing count. How to handle severity decrease on a still-open incident, severity re-crossing, and recurrence interactions with notification cooldown remain open under PB-04/ALERT_SPEC.md. Until that downstream rule is settled, do not infer a new email behavior from a severity decrease. Store the detection result and preserve the incident's audit trail.

Non-definitive classifications are excluded from confirmed defect counts; pending, failed, needs-review, and otherwise non-definitive results are never converted to `NO_DEFECT`. The approved DAI-06 coverage policy determines whether source and classification coverage is sufficient. When DAI-06 assesses required coverage as insufficient, the result cannot create or update an automatic incident, reopen an episode, create a linked episode, or enqueue automatic email. Automatic detection remains disabled until the required coverage policy and calibration are approved.

## 8. UTC event-time processing and late arrivals

Keep feedback.event_time_utc, feedback.ingested_at, classification completion timestamps, and detection evaluated_at distinct. Only event_time_utc selects observed/baseline membership. A record uploaded or classified late is not moved to the ingestion date.

When a late-arriving eligible record, classification-state change, or coverage-policy/rule change affects a stored window:

- Enqueue recomputation for each affected resolved cluster and all stored evaluation windows it intersects. Mark stored-window refreshes `HISTORICAL_RECOMPUTE`; the routine monitoring schedule separately creates its current-window evaluation.
- A late record in an observed window may change observed_count. A late record in a baseline window may change baseline_28d_count, normalized baseline, ratio, and the current severity result.
- Preserve the previous result and evidence snapshot; persist a new result with a new input identity. Record that recomputation was caused by late arrival where the job/audit context permits.
- Do not silently rewrite or delete a previous result. Incident history records which result caused each update.

Recompute windows by their stored UTC boundaries; do not reinterpret them in local time or move a record across a boundary due to processing time. Preserve earlier results, evidence, and audit history; append the new result with its recomputation cause and policy/rule versions. Historical recomputation never changes incident state or produces automatic email solely because the historical result qualifies. Only a qualifying current monitoring result is eligible for incident application/notification. PB-09 approves this policy; retention horizon and scheduled reconciliation cadence remain operational decisions.

## 9. Detection evidence, explainability, and traceability

Every persisted result must be reproducible from its immutable rule version, exact windows, counts, coverage snapshot, and source/classification evidence. The source lineage is:

source_type + source_record_id → feedback_id → applicable classification_id and taxonomy version → classification label and logical_defect_id → defect cluster → detection_result_id → incident/incident_event, if any.

For each result, persist or reference:

- Stable result identity, cluster_id, rule_version, coverage_policy_version, evaluation_mode, evaluated_at, and exact observed/baseline UTC boundaries.
- Distinct observed_count and baseline_28d_count; normalized_baseline_7d and ratio where mathematically valid.
- Source coverage_state, classification completeness states and assessed/complete counts, decision_state, and applicable coverage declaration IDs/statuses.
- Every counted feedback_id, classification_id, label_role, logical_defect_id, and evidence_period (OBSERVED or BASELINE).
- For incident changes, detection_result_id in incident_events plus before/after status and severity where applicable.
- Linkage status and source drill-down context. Do not expose raw feedback text in operational logs or safe error summaries.

Evidence constraints must confirm that a cited classification is the applicable completed result, its feedback_id matches the cited source, its label maps to the evaluated logical_defect_id, and the source record satisfies linkage/window eligibility. A feedback_id appears at most once per result and evidence period. When both label roles map to the same logical defect, persist one evidence row with `label_role=PRIMARY`. Preserve both baseline and observed source references for explanation; API evidence pagination may filter by period.

For a zero baseline, display “No prior observed complaints,” baseline_28d_count=0, normalized_baseline_7d=0, and ratio=null. For insufficient history, display “Insufficient historical baseline,” the coverage declarations/status, and partial counts only with an explicit incomplete label. Never display an infinite ratio or represent failed/uncertain classification as no defect.

## 10. Dashboard metrics and detection-result contracts

### Metric semantics

| Metric | Detection specification |
|---|---|
| Cluster complaints | Distinct fully linked, validated defect feedback records for one logical_defect_id and period. This is a record count, not a failure rate. |
| Product unique defect feedback | Distinct fully linked feedback with a completed validated defect classification, counted once per product even if multiple issue labels apply. |
| Product pending defects | LINKAGE_PENDING defect records with valid product identity, separately labeled and excluded from fully linked totals and incidents. |
| Returns / returned units | Keep return-record count and known return_quantity separate; neither is a sales denominator. |
| Active warnings, critical warnings, products at risk | PB-05 has approved glossary creation only; definitions are not approved. Until defined, API_SPEC.yaml returns null and PENDING_DEFINITION rather than invented values. |
| Freshness and coverage | Expose last successful detection recomputation, source-coverage status, windows awaiting coverage, pending classification/job state, and stale-data context. A low count with incomplete classification or coverage is not a low-risk conclusion. |

Filters on dashboard charts do not change detection-rule windows or the persisted severity decision. Complaint counts, return records, and returned units remain separate. No product failure/return rate is derived without approved matching sales/transaction denominators.

### Persisted result contract

The DATA_MODEL.md v1.4 detection_results row is the storage contract. Required semantic fields are:

| Field | Meaning |
|---|---|
| detection_result_id / result_key | Immutable result identity and idempotency identity for one exact input/version snapshot. |
| cluster_id / rule_version / coverage_policy_version | Stable natural-key cluster reference and immutable detection and coverage policies used. |
| evaluation_mode / incident_application_state | Distinguishes current monitoring from historical recomputation and makes current-result application recoverable. |
| evaluated_at and four window boundaries | UTC evaluation instant and half-open event-time windows. |
| observed_count / baseline_28d_count | Distinct feedback record counts, never returned units. |
| normalized_baseline_7d / observed_to_baseline_ratio | Baseline normalized to seven days and finite ratio; ratio is null for zero or insufficient coverage. |
| coverage_state | SUFFICIENT_NONZERO, SUFFICIENT_ZERO, or INSUFFICIENT. |
| classification coverage | `COMPLETE`, `INCOMPLETE`, or `UNKNOWN` with assessed and definitive-complete record counts for the relevant windows. |
| decision_state / severity | NO_TRIGGER, TRIGGERED, or INSUFFICIENT_COVERAGE; severity MEDIUM/HIGH/CRITICAL only for a validated trigger. |

API_SPEC.yaml v1.4.0 (Approved — Design Baseline, conditional) retains paginated `GET /detection-results` for ADMIN and BUSINESS_USER roles. It returns rationale for `NO_TRIGGER`, `INSUFFICIENT_COVERAGE`, and `TRIGGERED` evaluations, including evidence counts by period, baseline source-coverage status, classification-completeness assessment, rule and coverage-policy versions, evaluation time, thresholds, and coverage declarations. This read-only list applies the existing page/page_size limits and backend authorization. IncidentDetail continues to expose the latest rationale for an incident.

The existing detection rule API fixes observed_window_days=7 and baseline_window_days=28 and carries per-severity minimum_observed_count and nullable minimum_observed_to_baseline_ratio. Null ratio means count-only behavior for a complete zero baseline. It does not make the PRD hypothesis values active defaults.

The API keeps `normalized_baseline_7d=0` for a sufficient zero baseline and returns null for an insufficient baseline; the ratio is null for both. An insufficient result includes explicit source/classification coverage rationale and may expose partial counts only as evidence, never as validated risk.

## 11. Idempotency, retries, and concurrency

### Canonical result fingerprint

DATA_MODEL.md requires stable work_key and result_key values. `result_key` is the SHA-256 fingerprint of one canonical UTF-8 JSON input snapshot. Construction:

1. Include cluster_id, evaluation_mode, exact four UTC window boundaries, rule_version, coverage_policy_version and canonical coverage-policy configuration, source coverage assessment, classification-completeness assessment/counts, and sorted source-coverage tuples with assessed status.
2. Include sorted state tuples for every feedback record in the applicable observed and baseline source cohorts, not only counted defect evidence. Each tuple includes feedback_id, event_time_utc, linkage_status and resolved linkage IDs, relevant classification attempt/state/revision, and (when definitive) selected classification_id, defect outcome, needs_review, and validated logical-defect label mappings. Include counted evidence tuples with evidence_period and preferred label role. Do not include source text or other free text.
3. Serialize with deterministic key ordering and separators and hash with SHA-256. A change in pending/failed/needs-review/completed/no-defect state, source coverage, either policy version, windows, rule, or evaluation mode changes the fingerprint. In particular, a transition from pending to definitive no-defect creates a new result key and cannot leave a stale insufficient result current. A retry with identical inputs resolves to the same immutable result.

Fix evaluated_at/T for a durable work item before first calculation and preserve it across retries. The authoritative classification-attempt selection policy remains an open AI/data-model dependency; once approved, the fingerprint includes the attempt identity/state selected under that policy and any relevant state transition.

### Persistence and retry behavior

- Recompute counts from source rows on every attempt; do not use non-idempotent increments.
- In a short transaction, insert the immutable result/evidence/coverage snapshot. Set `incident_application_state=NOT_APPLICABLE` for historical, non-trigger, and insufficient results; set it to `PENDING` for a qualifying current result.
- Application checks `incident_application_state` even when `result_key` already exists. `PENDING` is a durable recovery condition and must never be treated as a completed idempotent duplicate. Recompute the current canonical input snapshot for the same T/rule/policy before applying: if it matches, apply; if not, mark the old result `SUPERSEDED` and durably queue/reuse recomputation for the latest input. An existing result only suppresses duplicate computation, not unapplied incident work.
- In one short SQLite transaction, re-read the pending result and current incident/episode, apply lifecycle/recurrence and any severity increase, write the idempotent incident event, write the required outbox event and recipient snapshot when ALERT_SPEC requires one, then set the result to `APPLIED`. The incident state, audit event, application-state update, and required outbox data commit or roll back together under ARC-07.
- Use a stable incident event key derived from detection_result_id and application action. On retry, if the event already exists, verify its incident/outbox effects and mark application complete in the same transaction; never duplicate them. Event/outbox uniqueness protects against concurrent retries.
- External email I/O happens only after commit. External provider delivery is not exactly-once.
- Persist failed/retryable work visibly. Numeric attempt limits, backoff, lease duration/recovery, scheduled reconciliation cadence, and SQLITE_BUSY behavior remain OPS-02/ARC-04 decisions; this document does not assign numeric values.

### Concurrency

The approved architecture uses one worker and SQLite on one active instance. The partial unique index remains the final guard against two open incidents for one cluster; unique result_key, incident event, and outbox keys guard retries. In the incident-application transaction, re-read the pending result, current open incident, and latest resolved episode before applying it. If a uniqueness conflict occurs, load and update the winning open incident idempotently rather than creating a second incident. Only the worker transaction changes application_state to APPLIED.

Keep write transactions short and never hold one during provider or long-running work. A concurrent API write or recovery operation may make SQLite busy; preserve durable work and use the separately approved bounded retry policy once ARC-04/OPS-02 values are selected. Do not add workers, locks, brokers, databases, or multi-instance deployment as a workaround.

If a newer source/coverage/classification snapshot becomes current while a result is being computed, the fingerprint comparison prevents stale application. Preserve the old immutable result as `SUPERSEDED` when it had already been persisted with application pending, and ensure the newest recomputation is durably queued. A stale result must never update incident state or create an outbox event.

## 12. Planted-defect scenarios and sentiment-baseline comparison

The synthetic seed must include 10,000 review/return records across at least 35 UTC event-time days, explicit complete-coverage intervals, normal patterns, non-defects, ambiguous cases, late arrivals, data-quality/linkage failures, and planted defect clusters. PRD examples include zippers, stitching, sizing/fit, material, finish, and packaging. The initial taxonomy seed and code spellings remain subject to AI_SPEC/DAI-04 governance; examples do not approve taxonomy values.

For each planted episode, retain evaluation-only truth metadata sufficient to identify the target product/supplier/batch/logical defect, onset and event interval, planted feedback identities, scenario split, and whether its source/linkage/coverage conditions make it eligible for automatic detection. Keep development episodes separate from the locked held-out episodes. Do not tune on held-out scenarios.

Detection evaluation reports detected/total planted episodes, false positives, misses, scenario counts, and uncertainty. EV-03's provisional ≥90% held-out recall target and denominator remain Pending Calibration. The dataset must define how a detection maps to one planted episode, the acceptable detection window, and the denominator before the held-out set is locked. Do not claim the target is met merely because individual planted rows were classified.

For lead-time comparison, run ProductPulse and one simple sentiment-score or negative-review threshold comparator on the identical event-time stream. EV-04 approves selecting a reproducible comparator during development and freezing its method and threshold before held-out evaluation; no particular method or value is selected here. Report first qualifying ProductPulse warning versus comparator time on the same episode. Do not add a user-facing sentiment feature solely for this evaluation.

## 13. Unit, integration, and evaluation test cases

Implement tests for the cases below once the required calibration and test-tool decisions are approved. Tests must use synthetic or permitted public non-sensitive feedback and deterministic fixtures.

### Unit tests

- Half-open interval membership at exactly T−35d, T−7d, and T; UTC normalization and no local-time drift.
- Distinct feedback counting when text repeats an issue, duplicate labels are attempted, or two classification attempts exist; when PRIMARY and SECONDARY map to one logical defect, count once and cite PRIMARY.
- Result fingerprint changes when relevant classification state changes from pending to definitive no-defect, when completeness assessments change, or when the coverage-policy version changes; identical snapshots remain idempotent.
- One record contributes once to each distinct logical defect, but never twice to the same logical_defect_id cluster/period.
- Cross-taxonomy versions with explicitly shared logical_defect_id join one cluster; a changed meaning/new ID remains separate.
- Formula correctness for nonzero baseline, fractional normalized baseline, exact equality at each configured boundary, highest qualifying severity, complete zero baseline, and ratio null/no infinity.
- Incomplete/unknown/gapped source or classification coverage yields INSUFFICIENT, null severity and ratio when the approved coverage policy requires it, even when partial baseline counts are nonzero; no automatic incident/outbox is allowed for a required insufficient baseline.
- Failed, retryable-failed, terminal-failed, queued, in-progress, and NEEDS_REVIEW classifications do not count as confirmed defects.
- LINKAGE_PENDING records appear only in pending product aggregates, never in incident-capable cluster counts.
- Recurrence at exactly 30 days reopens the same incident; recurrence after 30 days creates a linked episode.

### Integration and recovery tests

- A completed classification queues recomputation and produces reproducible result, evidence, and coverage rows.
- Retry of identical inputs/rule/policy versions produces one result and no duplicate incident event/outbox request.
- A qualifying current result persisted as PENDING is applied after recovery even though its result_key already exists; retries produce one incident event and at most one required outbox event, and forced transaction failure leaves the result PENDING.
- If the current input fingerprint changes before application, the old pending result becomes SUPERSEDED, creates no incident/outbox effect, and leaves latest-input recomputation durably queued.
- A historical recomputation can persist a TRIGGERED result and new evidence but does not create, reopen, update, or notify an incident; the current monitoring evaluation remains separately eligible.
- A higher qualifying severity updates an existing incident severity with before/after audit evidence; lower-severity handling is left to PB-04/ALERT_SPEC.
- New eligible source, late-arriving event, coverage declaration/change, and Admin linkage reconciliation recompute the affected cluster/windows.
- An insufficient-coverage result creates no incident, reopening, linked episode, or automatic outbox event.
- A complete zero baseline uses count-only configured thresholds and displays no prior complaints without infinity.
- A planted qualifying spike creates/updates one batch-specific incident with evidence that drills back to the correct feedback, classification, label, product, supplier, and batch.
- Two concurrent/recovered attempts for one cluster cannot create two open incidents; unique constraints and idempotent reload/update behavior are exercised.
- A NO_TRIGGER or decreasing count does not auto-resolve an incident.
- Incident update and required outbox event are atomic: forcing either local write to fail leaves neither committed.
- `GET /detection-results` returns paginated NO_TRIGGER and INSUFFICIENT_COVERAGE rationales to ADMIN/BUSINESS_USER, including evidence counts, baseline coverage status, rule/policy version, and evaluation timestamp; unauthorized access and invalid pagination are rejected consistently with other reads.
- Dashboard filters do not mutate detector windows; unsettled PB-05 KPIs return null/PENDING_DEFINITION.
- LINKAGE_PENDING inputs never fabricate supplier/batch IDs and never create product-only incidents/emails; reconciliation can then qualify the resolved batch cluster.

### Evaluation tests

- Held-out planted-episode recall, false positives, missed episodes, and scenario denominator are reported; no held-out tuning occurs.
- Compare lead time against the frozen sentiment/negative-review comparator using identical event-time input.
- Verify source-link integrity, cross-version logical-defect behavior, zero/incomplete coverage handling, late arrivals, incident recurrence, retry/idempotency, and no duplicate incidents under worker recovery.
- Keep classification gates (EV-02) and planted-episode gate (EV-03) clearly separate. Do not invent a macro-accuracy threshold, final held-out size, or approved 90% recall gate.

## 14. PRD requirement and acceptance-criteria traceability

| Source requirement | Detection behavior in this specification |
|---|---|
| PRD §2.2 objectives; F08 | Deterministic emerging-cluster counts, rule decisions, evidence, and batch-specific warning inputs (§§1–2, 6, 9). |
| PRD §5.1; AC05–AC09 | Validated classification recomputation in the worker, with durable evidence and reproducible thresholds (§§1, 2, 11). |
| PRD §§6.2–6.4; F09–F10 | UTC windows, coverage/freshness, evidence rationale, and source drill-down; 30-second polling remains UI cadence (§§4, 5, 9–10). |
| PRD §§7.3–7.4; AC19, AC23 | No fabricated links; explicit coverage; late arrivals; PB-06 handling and reconciliation recomputation (§§3, 5, 8). |
| PRD §9.1; AC20–AC21 | Distinct-record counts, normalized 28-day baseline, zero-baseline count-only treatment, and insufficient-coverage suppression (§§4–6). |
| PRD §9.2; AC09 | Provisional highest-severity rule table, deterministic backend severity, evidence of counts/math/thresholds (§§6, 9). PB-01 remains pending. |
| PRD §§9.3, 15 AC22; PB-03 | One open incident per cluster, no auto-resolution on decreasing counts, exact approved 30-day recurrence boundary (§7). |
| PRD §9.4; AC10–AC11; PB-04 | High/Critical email eligibility and fixed cooldown/escalation behavior remain owned by PRD/PB-04 and ALERT_SPEC; edge cases are open (§7, 11). |
| PRD §14; AC17; EV-01/EV-03/EV-04 | Planted-episode recall, false positives, locked held-out data, and identical-stream baseline comparison (§12–13). |
| PRD AC24; AI_SPEC §§3, 7, 11 | Only definitive completed classifications count; failures/uncertainty reduce visible coverage and are not NO_DEFECT (§2, 5, 13). |
| DATA_MODEL §§4.7, 5–6 | Cluster, immutable result, evidence, coverage snapshot, incident and idempotency fields (§§2, 9, 11). |
| API_SPEC dashboard, incident, detection-result, detection-rule, and source-coverage contracts | The API v1.4.0 draft retains the paginated detection-result rationale introduced in last-approved v1.1.0 and preserves calibration-pending rule activation (§10). |

## 15. Open decisions and calibration dependencies

| Item | Status | Needed before |
|---|---|---|
| PB-01 minimum counts and nonzero-baseline ratio thresholds | Pending Calibration. PRD table is provisional only. | Activating a rule for incident/email creation and final detection evaluation. |
| Minimum support count for a nonzero baseline | Not specified; no default may be inferred from the PRD ratio formula. | Deciding when the normalized ratio is sufficiently supported for automatic severity. |
| DAI-06 source/classification coverage scope and gate | Assessment states/counts and fingerprint inputs are approved; exact source scope, interval combination, classifier-completion policy, and any threshold remain Pending Calibration. No numeric gate is approved. | Finalizing when incomplete source/classification coverage may support automatic decisions; do not activate automatic detection before this is resolved. |
| Authoritative classification attempt when multiple attempts are COMPLETED | Unresolved; pre-implementation dependency. The highest-attempt proposal in §2 is not approved. | Implementing classification counting across retries or multiple completed attempts; align AI_SPEC.md, DATA_MODEL.md, and this specification first. |
| Evaluation instant and scheduled detection/reconciliation cadence | Windows are defined; operational cadence is open under OPS-02/ARC-04. | Worker scheduling and freshness promises. |
| Historical recomputation retention and cadence | PB-09 approves immutable historical recomputation without incident/outbox application; retained horizon and operational cadence remain open. | Selecting retention and scheduled reconciliation parameters. |
| Severity decreases/re-crossings and notification interaction | PB-04 core cooldown/escalation approved; edge cases belong to ALERT_SPEC. | Complete automatic notification behavior. |
| Detection result read API | Introduced in API_SPEC.yaml v1.1.0 and retained in the v1.4.0 Approved — Design Baseline as paginated read-only `GET /detection-results`. | Contract is specified; backend implementation remains downstream. |
| PB-05 definitions for active warnings, critical warnings, products at risk | Metric-glossary creation approved; definitions pending. | Returning numeric values for those KPIs. |
| EV-01 held-out data size and minimum representation | Pending Calibration. | Locking held-out evaluation or claiming stable evaluation metrics. |
| EV-02 class-specific classification gates | Pending Calibration under AI_SPEC.md; no final class gates are set here. | Finalizing classification evaluation or dependent held-out gates. |
| EV-03 planted-episode denominator and recall gate | Pending Calibration; the PRD's ≥90% value remains provisional. | Locking held-out evaluation or claiming a numeric detection gate. |
| Stable detection work_key/freshness predicate | Result-key proposal in §11; exact generation guard needs implementation review. | Reliable stale-result protection and recovery. |

## 16. Consistency review and approval boundary

The v1.0 approval review used AGENTS.md and PRD v1.6, Decision Register v1.2, Architecture v1.3, Data Model v1.2 (Draft update), API_SPEC.yaml v1.1.0 (Approved at that review), AI_SPEC.md v1.0, and TECH_STACK.md v0.7. Current linked baselines API_SPEC.yaml v1.4.0, DATA_MODEL.md v1.4, and UI_SPEC.md v0.3 are Approved — Design Baselines subject to documented conditions; ALERT_SPEC.md v0.2 remains Draft.

Consistency findings:

- The deterministic backend boundary, event-time windows, distinct feedback counting, zero-baseline treatment, PB-06 behavior, source lineage, immutable rule/results, and approved 30-day recurrence rule align with the reviewed specifications.
- Where PRD §9.1 says no automatic warning under insufficient history, this specification adopts the stricter and explicit Architecture/Data Model/API behavior: no automatic incident and no automatic email. That also follows the user's instruction for this deliverable.
- The PRD's 5/10/20 counts and 2×/3×/5× ratios are consistently labeled provisional. PB-01 stays Pending Calibration; DAI-06 method is preserved without approving its coverage values.
- The updated API and Data Model define the read-only no-incident rationale, classification/coverage fingerprint inputs, and recoverable application state. PB-09's historical recomputation boundary and primary-label evidence tie-break are reflected consistently.
- No contradiction was found with the PRD requirements, approved Architecture, SQLite single-writer constraint, PB-06 linkage boundary, or PB-03 recurrence rule. `DATA_MODEL.md` v1.4 is an Approved — Design Baseline subject to documented conditions. The v1.0 detection baseline remains approved; this v1.1 clarification is still a draft pending review.
- The authoritative-classification selection rule remains an unresolved pre-implementation dependency. DAI-06 exact coverage scope/completeness/gating parameters, PB-01 thresholds, EV-01/02/03 calibration parameters, and PB-04/ALERT_SPEC notification edge cases also remain open. None is approved by this document.

**Approval:** The Product Owner approved `DETECTION_SPEC.md` v1.0 as **Approved — Design Baseline** on 21 November 2026, with the conditions recorded above. This is a conditional design baseline only; it does not activate automatic detection or approve any calibration threshold. PB-01, DAI-06, EV-01/02/03, the authoritative-classification selection dependency, and the downstream ALERT_SPEC notification contract must be resolved before their dependent behavior is implemented or activated. No application code, migration, or ticket is included.

**Current revision:** v1.1 is a draft clarification only. It does not replace the approved v1.0 baseline or approve any DAI-06 scope/completeness parameter, PB-01 threshold, or detection activation decision.
