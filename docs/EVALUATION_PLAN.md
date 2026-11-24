# ProductPulse Evaluation Plan

**Version:** 0.6  
**Status:** Draft — evaluation methods documented; final plan approval is blocked by pending calibration decisions  
**Date:** 24 November 2026  
**Requirements source:** [PRD](PRD.md) v1.7  
**Decision basis:** [Decision Register](DECISION_REGISTER.md) v2.3

## 1. Purpose and approval boundary

This document defines a practical, reproducible evaluation for ProductPulse classification, detection, source linkage, processing, dashboard, security, and reliability behavior. It records how to measure results and what evidence to retain; it does not approve model or rule values, create evaluation data, authorize application work, or claim that ProductPulse meets a target.

The PRD is authoritative for product behavior. The Decision Register controls approval status. Evaluation procedures below are identified as one of:

- **Specified method:** directly follows an approved requirement or evaluation method.
- **Provisional target:** a PRD value approved only as a measurement target or hypothesis; it is not an acceptance gate unless separately approved.
- **Pending calibration/decision:** must be resolved before the dependent held-out evaluation, implementation, activation, or final gate.

EV-01, EV-02, and EV-03 remain Pending Calibration and block final evaluation-plan approval. This version is therefore a reviewable draft, not a final approved evaluation baseline. No evaluation results are asserted here.

## 2. Governing specifications and objectives

The evaluation covers the PRD objectives: classify review and return feedback into a governed taxonomy; preserve source links; detect planted defect clusters deterministically; show evidence and processing freshness; track incident and notification behavior; and report quality, lead time, latency, and cost.

| PRD success metric | Evaluation evidence | Current status |
|---|---|---|
| Classification quality | Held-out human-labelled per-class precision, recall, F1, confusion matrix, uncertainty, and strict-schema results. | Method specified; EV-01 sample support and EV-02 class gates pending. |
| Planted-defect detection | Eligible held-out episodes detected, false positives, misses, and scenario coverage. | Method specified; PRD `>=90%` recall is provisional; EV-03 denominator/gate pending. |
| Earlier warning than sentiment-only reporting | Paired lead time against one frozen sentiment/negative-review comparator on the identical event-time stream. | EV-04 selection/freeze method approved; specific comparator and threshold selected during development. |
| Source-link integrity | Exact source identity, product/supplier/batch linkage, evidence drill-down, and unresolved-link handling. | PRD's 100% fixture-integrity gate is a planning default to verify; report field and chain counts. |
| Classification and historical coverage | Classification coverage by record/state plus explicit source-interval and classifier-completeness assessment. | PRD coverage formula and DAI-06 method specified; exact DAI-06 parameters pending. |
| Dashboard quality and risk KPIs | Verify correct units, filter/freshness context, and pending/unknown states; assess numeric warning KPIs only after definitions are approved. | PB-05 leaves active warnings, critical warnings, and products at risk undefined; do not substitute UI calculations. |
| API-path consistency | Paired semantic agreement and completion/validity rates for Responses and Batch. | Method specified; no numeric agreement gate approved. |
| Usage, latency, and cost | Tokens, per-attempt/provider and pipeline latency, and cost per 1,000 eligible records with retry and path splits. | Cost reporting approved; no spend limit/gate approved. |
| Dashboard performance and freshness | Initial-load p95 on the seeded 10,000-record dataset; event-, ingestion-, and classification-to-display latency. | PRD `<=3 seconds` and `<=60 seconds` are OPS-04 provisional measurement targets, not pre-merge checklist gates. |
| Incident/notification reliability and security | Idempotency, incident lifecycle, notification authorization/state, RBAC, CSRF, injection, and safe output tests. | Test methods trace to PRD/SECURITY; Alert implementation details and security dependencies remain conditional/open. |

| Specification | Evaluation use and status |
|---|---|
| [PRD](PRD.md) v1.7 | Requirements source. Its 10,000-record synthetic seed and 35-day event-time span are product dataset requirements. Its release-gate values are explicitly provisional pending confirmation. |
| [AI_SPEC](AI_SPEC.md) v1.0 | Approved conditional design baseline for taxonomy classification, data splits, class metrics, path consistency, schema validity, injection evaluation, latency, and cost. Model ID, taxonomy seed, and evaluation gates remain open. |
| [DETECTION_SPEC](DETECTION_SPEC.md) v1.1 | Draft clarification; v1.0 remains the Approved conditional design baseline. Use v1.1's stated evaluation clarifications for review, but do not treat the draft as implementation approval. Detection activation remains gated. |
| [SECURITY](SECURITY.md) v1.0 | Approved conditional security design baseline. SEC-AC01–16 define security verification expectations; their unresolved dependencies remain in force. |
| [DECISION_REGISTER](DECISION_REGISTER.md) v1.7 | Authoritative status for EV-01–05, PB-01, PB-03–06, DAI-05/06, OPS-04, and other dependencies. |
| [ARCHITECTURE](ARCHITECTURE.md) v1.4 | Approved architecture constraints, including one API, one worker, one shared SQLite file, and no provider calls inside database transactions. |
| [API_SPEC](API_SPEC.yaml) v1.4.0, [DATA_MODEL](DATA_MODEL.md) v1.4, [UI_SPEC](UI_SPEC.md) v0.3 | Approved conditional design baselines. Use their role, state, traceability, freshness, and idempotency contracts while respecting their listed dependencies. |
| [ALERT_SPEC](ALERT_SPEC.md) v0.2 | Draft, not approved for implementation. Its verification cases help identify alert scenarios; unresolved routing, provider, retry, preview-token, and cooldown edge behavior must not be assumed settled. |
| [TECH_STACK](TECH_STACK.md) v1.0 | Backend/API and frontend test runners, repeatable local PowerShell scripts, and the pre-merge evidence process are selected. No hosted CI service or browser E2E framework is used. |

## 3. Evaluation stages

Keep development calibration separate from the final held-out evaluation.

### 3.1 Development calibration

Use only development records and development planted episodes to:

1. Review human labels and taxonomy definitions; resolve ambiguous examples or label them uncertain.
2. Select a supported common OpenAI model for Responses and Batch, then version and tune the prompt/schema/taxonomy contract as allowed by AI_SPEC and DAI-05.
3. Calibrate deterministic detection rules and the DAI-06 coverage policy on development scenarios only.
4. Select one simple sentiment-based comparator, define its inputs and threshold using development data, and freeze it before held-out evaluation under EV-04.
5. Assess class and scenario representation and propose thresholds/gates for owner review under EV-01, EV-02, and EV-03.

The PRD's 5/10/20 count and 2x/3x/5x ratio examples are detection hypotheses, not defaults. The provisional planted-episode recall value is not an approved gate. Do not tune using held-out outputs.

For EV-02, create a calibration row for each approved primary category and specific issue code. Using development records only, record definitive-label support and prevalence, per-class precision/recall and confusion counts, uncertainty/failure rates, and descriptive intervals. Compare candidate configurations against the observed class prevalence and the product impact of false positives and false negatives; document the evidence and trade-offs. The Product Owner must select and record each class's precision/recall floor or approved regression rule, any support/sufficiency condition, and how its failure is represented in the pre-merge checklist before held-out labels or results are examined. If development support cannot justify a class gate, record that class as pending and obtain more development evidence or an explicit decision; do not substitute an aggregate accuracy target. No numeric class gate or minimum support is selected by this plan.

### 3.2 Freeze and held-out evaluation

Before revealing or scoring held-out labels, record and freeze the dataset manifest and hash, label/taxonomy version, model identifier, prompt and schema versions, API path settings, code revision, detection rule and coverage-policy versions, sentiment comparator and threshold, episode-matching rule and detection horizon, authoritative classification-attempt policy, and the approved metric gates. Record all pending values as pending; do not substitute convenient defaults. Final held-out scoring remains blocked while EV-01, EV-02, or EV-03 is pending.

Run the frozen configuration on the held-out records and scenarios. Report the complete planned metric set, including failures and uncertainty. Any held-out result used to guide a change consumes that held-out set, including aggregate metrics, class/scenario diagnostics, misses, false positives, or observed uncertainty used to change the model, prompt, schema, taxonomy, comparator, thresholds, coverage policy, matcher, evaluator, or data design. Mark the set consumed and lock a fresh held-out set before making a new final claim. Do not feed held-out examples or results back into development calibration while continuing to call that set final.

### 3.3 Regression evaluation

For each model, prompt, input-format, schema, taxonomy-meaning, or detection-rule change, increment the applicable version and run regression evaluation on development data. Once the relevant decisions and gates are approved, local evaluation checks calculate the locked held-out metrics; the documented pre-merge checklist records any configured regression as a failure under PRD AC17. Keep held-out per-record diagnostics from becoming a tuning loop; use development data to diagnose and correct behavior.

## 4. Synthetic labelled data design

No dataset is created by this plan. When data work is separately authorized, use only synthetic or permitted public, non-sensitive review and return records. Preserve the PRD seed requirement of 10,000 feedback records across at least 35 UTC event-time days; this is not approval of the held-out evaluation sample size.

### 4.1 Proposed held-out structure and representation (EV-01)

The proposed held-out set is a locked, manifest-backed partition of unique feedback records and planted episodes, with separate development and held-out membership. A record is one stable source identity, not one provider attempt. Keep all exact/near duplicates, paraphrase or template families, and records belonging to the same planted episode in a single partition. The manifest should link record IDs to source type, gold-label/adjudication state, taxonomy version, evidence spans, and any linkage/coverage scenario; the episode manifest should link scenario and episode IDs to their planted records and truth conditions. Keep evaluation truth metadata separate from the input available to the evaluated system.

The proposed record strata include both REVIEW and RETURN; each approved primary category and specific issue code; definitive NO_DEFECT examples; and gold-uncertain examples. Show representation by source type and label, including support and prevalence. Do not activate candidate taxonomy spellings from AI_SPEC. The proposed episode strata cover the PRD's planted families (zippers, stitching, sizing/fit, material, finish, and packaging) and include ordinary non-episode controls, late-arrival cases, complete nonzero and complete zero baselines, and deliberately insufficient-coverage or unresolved-linkage suppression cases. Mark each episode or control as intended eligible or ineligible from its locked input truth and the approved coverage/linkage rules. Keep ineligible suppression cases visible in their own stratum; do not use them to enlarge the eligible recall denominator.

Before lock, the development report should show the available counts by source type, definitive label, uncertain-label status, episode/scenario type, and eligibility/suppression reason, then propose the count and minimum-representation plan for owner review. Final held-out record counts, per-class minimums, planted-episode counts, per-scenario minimums, split proportions, and any statistical sufficiency rule remain pending EV-01. Do not infer these values from the PRD's 10,000-record product seed or claim stable metrics when representation is insufficient.

Across the corpus, include normal feedback, malformed/rejected-input fixtures, and resolved and unresolved linkage cases in addition to the strata above. For every labelled example, preserve:

- Stable source type and source-record ID, event time in UTC, permitted source-text provenance, and split/group identifiers.
- Human-expected primary label, optional secondary label, evidence span(s), label/adjudication status, and taxonomy version.
- Expected product, supplier, and batch linkage, including whether any field is intentionally unresolved.
- For planted records: scenario ID, target product/supplier/batch/logical defect, episode onset and interval, planted source IDs, and the predeclared eligibility/coverage conditions for automatic detection.
- For source and classification coverage tests: declared UTC coverage interval and scope metadata, plus the intended classification-state transitions.

Use the approved taxonomy and label guide as the gold-label authority. Record uncertain or disputed examples explicitly; do not force a definitive gold label. A practical solo workflow is a human labeling pass followed by a separate review pass before lock, with unresolved disagreements retained as uncertain and counted in the report.

## 5. Classification quality metrics (AI-P01)

For each unique eligible source record, use only its authoritative validated `COMPLETED` classification for the taxonomy version pinned to the evaluated run; provider attempts are never the metric unit. Per the approved 23 November PP-005 rule, select the latest fully validated definitive completion by persisted UTC `completed_at DESC`, then unique `classification_id COLLATE BINARY DESC`. A completed classification is definitive defect or definitive no-defect and has `needs_review=false`. A record with no qualifying result for the run-pinned version has no predicted class label; retain its `NEEDS_REVIEW`, failed, invalid, pending, or missing disposition in separate outcome reporting and do not treat it as `NO_DEFECT`. For a definitive gold label absent from the selected output, count the label as not predicted (and therefore a false negative for that class). Report REVIEW and RETURN separately as well as together. Do not add attempts together; preserve the source attempt history and version context. The Product Owner approved the general aggregate applicability rule on 24 November: each aggregate context has one explicit taxonomy version, with no fallback or cross-version count merge. Evaluation continues to pin one version per run and does not substitute a result from another version.

For each approved primary category and specific issue code, report support and the following one-versus-rest measures:

- `precision = TP / (TP + FP)`
- `recall = TP / (TP + FN)`
- `F1 = 2 * precision * recall / (precision + recall)`

An undefined denominator is reported as `N/A`, with the underlying counts; it is not silently converted to zero. For each class, a true positive is an exact gold/predicted label match. A false positive is a prediction of that label where it is absent from the gold labels. A false negative is a gold label not predicted; an uncertain, failed, invalid, or missing output does not count as a positive prediction. Report support so small or absent classes are visible. Do not substitute an aggregate accuracy or macro-accuracy for per-class results.

For definitive gold labels, provide a primary-label confusion matrix with gold primary labels as rows and predicted labels as columns. Include the label predictions from authoritative COMPLETED outputs and explicit NEEDS_REVIEW and NO_VALID_OUTPUT/FAILED disposition columns so uncertainty and failures are visible and never merged into NO_DEFECT. Only an authoritative COMPLETED output contributes a class-label prediction or a predicted positive for precision; non-completed states are disposition columns and are not valid labels. Evaluate the optional secondary label separately with one-versus-rest issue-code metrics and exact primary/secondary tuple agreement. Report the count/rate of NEEDS_REVIEW, failed/rejected outputs, and invalid outputs separately from defect/no-defect predictions. Where supported, accompany proportions with a 95% Wilson interval as descriptive uncertainty, never as a gate.

Gold-uncertain examples are excluded from definitive-class precision, recall, F1, and the definitive-label confusion-matrix denominator; do not force them into a defect or NO_DEFECT class. Report their count and rate separately by source type, adjudication reason/status, and taxonomy version. For this subset, use one selected per-record outcome under the same approved attempt-selection policy and report its distribution (NEEDS_REVIEW, authoritative COMPLETED defect/no-defect, failed/invalid, or missing). Define NEEDS_REVIEW capture as gold-uncertain records with selected NEEDS_REVIEW divided by all gold-uncertain records; define the definitive-assertion rate as gold-uncertain records with an authoritative COMPLETED defect/no-defect result divided by all gold-uncertain records. Missing/failed/ambiguous-attempt cases remain separately visible in the denominator accounting. These are descriptive uncertainty-handling measures, not new gates. Disputed labels that cannot be adjudicated remain gold-uncertain.

Report strict-schema validity among persisted `COMPLETED` classifications, plus the number of invalid/rejected attempts. A stored `COMPLETED` result must represent a definitive defect or no-defect outcome; a failure or uncertainty is not a no-defect result. The PRD's 100% valid strict schema for persisted completed outputs is a stated invariant/gate candidate, not a new threshold introduced by this plan.

## 6. Planted-defect detection evaluation (DET-P01)

Replay held-out scenarios in UTC event-time order through the deterministic detection path, preserving DETECTION_SPEC's fixed windows at evaluation instant T: observation `[T - 7 days, T)` and baseline `[T - 35 days, T - 7 days)`. Use identical predeclared checkpoints for ProductPulse and the comparator. The operational evaluation cadence remains open under OPS-02; record the cadence and do not describe dashboard polling as detector cadence. Only a qualifying CURRENT_MONITORING incident episode is a warning prediction. Historical recomputations are evidence only and do not count as warning detections. Count initial incident creation, recurrence reopen, or a linked new episode once; subsequent updates/recomputations of the same incident episode do not create additional warning predictions.

### 6.1 Proposed EV-03 episode matcher and window

For each planted episode, use the truth manifest's onset_utc and a predeclared, half-open detection window `[onset_utc, onset_utc + approved_detection_horizon)`. The earliest qualifying current-monitoring warning episode in that window is a candidate detection. The evaluated warning must have the exact truth identity `(product_id, supplier_id, batch_id, logical_defect_id)`; category/name similarity or partial/unresolved linkage is not a match. Record all evaluation timestamps in UTC. The proposed detection horizon is one frozen parameter shared by the held-out run; its value and any scenario-specific exception remain pending EV-03 and must be approved before held-out lock. Detection-window matching is separate from the detector's fixed 7-day observation and 28-day baseline windows.

Create a bipartite graph from eligible planted episodes to candidate warning episodes, with an edge only when identity and time-window conditions both match. Select a maximum-cardinality one-to-one matching so each planted episode and each warning episode is used at most once. If multiple maximum matchings exist, apply a deterministic tie-break using warning UTC time, episode onset UTC, then stable episode and warning IDs in ascending order. Freeze this algorithm and its implementation before held-out evaluation. One-to-one matching prevents repeated warnings or one warning from inflating episode recall.

### 6.2 Eligibility, denominator, false positives, and recall

Determine eligibility from the locked ground-truth input conditions and the approved source-coverage and linkage policy before running the evaluated classifier or detector. An eligible planted episode has the predeclared source coverage and resolved batch identity required for automatic detection. Do not remove an otherwise eligible episode from the denominator because the evaluated classifier returned uncertainty, failed, omitted a label, or because the detector did not trigger; these outcomes are missed detections. Scenarios deliberately designed to be ineligible because of insufficient coverage or unresolved linkage are reported separately as suppression controls and do not enter the recall denominator.

For the approved eligible set, calculate `episode recall = uniquely matched eligible planted episodes / eligible planted episodes`. Report the matched numerator, eligible denominator, misses, ineligible suppression-control counts/reasons, and a 95% Wilson interval as descriptive uncertainty. If the denominator is zero, report recall as N/A and the reason. Do not count planted rows as episodes.

A false positive is a distinct qualifying CURRENT_MONITORING warning episode left unmatched by the one-to-one matcher. This includes an incident episode emitted for an ineligible suppression control; identify those as suppression-policy violations within the false-positive report, and report them separately as well. Do not count repeated updates to one incident episode as multiple false positives. Report warnings by cluster and scenario/context, including warnings with no planted truth. ProductPulse's warning count and false-positive treatment are frozen before the held-out run.

The PRD's `>=90%` held-out recall remains provisional; EV-03 does not approve it as a gate. The final eligibility denominator, detection horizon, matcher, any sufficiency rule, and recall gate require explicit approval before final held-out evaluation or a numeric gate claim.

## 7. Lead-time comparison with a fixed sentiment baseline

EV-04 approves selecting one simple, reproducible sentiment-score or negative-review comparator during development, documenting its data requirements and threshold, then freezing it before held-out evaluation. The method and threshold are not selected in this plan. Do not build a user-facing sentiment feature solely for evaluation.

Run ProductPulse and the frozen comparator over identical records, event-time ordering, timestamps, and evaluation checkpoints. For each planted episode, define `onset_utc` from the locked scenario truth manifest and determine the first qualifying ProductPulse warning and first comparator warning attributable under the frozen episode-matching rule. For each detected system:

`lead_time = first_warning_utc - onset_utc`

For episodes detected by both:

`lead_time_gain = comparator_lead_time - ProductPulse_lead_time`

A positive gain means ProductPulse warned earlier. Report per-episode timestamps and lead times, the paired median gain and range, and the number of episodes detected by both. Report misses and one-system-only detections separately; do not impute a lead time for a miss or claim improvement from matched episodes alone. Freeze the comparator threshold and matching rule before viewing held-out outcomes.

## 8. Product, supplier, batch, and source-link accuracy (LINK-P01)

Use fixture truth as the oracle; the classifier does not determine these IDs. Measure the complete lineage from `(source_type, source_record_id)` to persisted feedback, classification attempt/labels, detection evidence, and incident where one is expected.

Report:

- Source identity exact-match rate: correct source type and source-record ID links divided by evaluated feedback/classification links.
- Product, supplier, and batch field accuracy separately: correctly matched ID or correctly retained unresolved/null state divided by fields with explicit fixture truth.
- Exact linkage-chain accuracy for records expected to be fully linked: records whose product/supplier/batch IDs and batch-parent relationships all match truth divided by fully linkable records evaluated.
- False-link count: any product/supplier/batch ID assigned where the fixture expects that field unresolved, or any identifier not supported by the source/reference mapping.
- Detection-evidence and incident drill-down integrity: cited source IDs resolve to the exact expected feedback and classification records; `LINKAGE_PENDING` records never gain fabricated supplier/batch links or become incident evidence.

Report counts with rates. PRD's 100% source-reference integrity in test fixtures is a stated gate candidate. Treat unresolved-link cases according to PB-06: labelled product-level analytics may exist when product identity is valid, but there are no product-only incidents or automatic notifications.

## 9. Classification and historical coverage (COV-P01)

### 9.1 Classification coverage

For a declared evaluation cohort, calculate the PRD metric over unique source records with the authoritative completed-attempt policy applied:

`classification coverage = unique validated eligible records with a definitive validated COMPLETED classification / unique validated eligible records`

`COMPLETED` includes definitive defect and definitive no-defect results. `NEEDS_REVIEW`, queued, in-progress, retryable/terminal failure, invalid, and missing results remain in the denominator and are reported by state; they are not treated as `NO_DEFECT`. Break out results by source type, import mode, time period, taxonomy/model version, and classification state where available.

The PP-005 within-version attempt-selection and taxonomy-version applicability policies are approved and aligned across AI_SPEC, DATA_MODEL, API_SPEC, and DETECTION_SPEC. Each evaluation run pins one version and applies the latest fully validated definitive completion within that version; never add attempts or substitute an attempt from another version. Report other-version attempts and states separately; do not infer coverage or detection scores for a different version.

### 9.2 Historical source and classifier coverage

Assess source-input coverage separately from classification completeness. Report explicit source-coverage declarations by UTC interval, source type, and declared scope; show missing intervals and `COMPLETE`, `INCOMPLETE`, or `UNKNOWN` states. For detection periods, report assessed and complete classification record counts and `COMPLETE`, `INCOMPLETE`, or `UNKNOWN` status using the policy version in the detection result.

Missing coverage is unknown, not a zero count. A complete zero baseline is reported as `SUFFICIENT_ZERO`; incomplete or unknown coverage is not a zero baseline. Test late arrivals and changed coverage declarations by confirming affected results are recomputed and their prior snapshots remain traceable. Do not combine source coverage and classification completeness into an undocumented score.

DAI-06 approves this assessment methodology but not the exact source scope, interval combination, completeness evidence, or classifier-completion gate. Keep those values pending and automatic detection disabled until the policy is approved.

## 10. Responses API and Batch API consistency (PATH-P01)

Use a paired evaluation harness over the same preselected synthetic records, with one supported model and the same pinned prompt, strict schema, taxonomy snapshot, and backend validation contract for both API paths. Preserve each record's source context and correlate Batch output by the durable classification ID/custom ID, never by file order. This is an evaluation replay; it does not change an import's immutable processing mode or mutate production classification attempts.

Report per path: submitted and completed records, valid strict-schema outputs, uncertainty, failures by safe state/code, token usage, provider latency, and cost. For records with validated results from both paths, calculate semantic agreement as exact equality of the normalized outcome and primary/secondary category and issue-code tuple. Report the paired-valid denominator and the per-path completion rate separately so failures cannot disappear from the comparison. Also list disagreements by class/state for review. No numeric API-agreement gate is approved.

DAI-05 requires model support for both endpoints and one common model but does not select the model identifier. Resolve model support, taxonomy, and retry/tooling dependencies before the final paired run.

## 11. Token use, latency, cost, dashboard performance, and freshness (OPS-P01)

### 11.1 Classification usage and cost

Record input/output tokens, provider-call latency, API path, model/version, attempt number, and estimated cost where returned or calculable. Null usage or cost stays null and is not reported as zero. Preserve the pricing basis/version used for estimates.

For a cohort, calculate:

`cost per 1,000 eligible records = (sum of recorded estimated cost for all provider attempts / unique eligible source records in the cohort) * 1,000`

Include retries and duplicate provider work when usage/cost is available; report their incremental cost separately. Split totals and per-1,000 cost by `RESPONSES` and `BATCH`, model/version, and cohort. Report input/output tokens per 1,000 unique eligible records and the proportion of attempts with measured usage/cost. Report provider latency per attempt and separately report ingestion-to-classification and classification-to-display durations. For Batch, distinguish submission/polling wall time from per-record processing latency.

EV-05 approves cost reporting only. No numeric spend limit or cost-based release gate is approved.

### 11.2 Dashboard performance and freshness

Measure Overview initial-load p95 on the PRD's seeded 10,000-record dataset in the test environment. Record the commit, database/seed state, environment/hardware, API and worker activity, sample count, and query/page definition. Calculate p95 using the nearest-rank method: sort observed initial-load durations and select rank `ceil(0.95 * n)`. Keep test conditions the same when comparing revisions; include API/worker write contention as required by OPS-04.

The PRD's `<=3 seconds` p95 is a provisional measurement target, not a merge blocker. Measure freshness from persisted UTC timestamps and the first dashboard state that visibly reflects the event, separately as:

- Event time to display.
- Ingestion acceptance/persistence to display.
- Successful classification completion to display.

Also report import, classification, and detection recomputation timestamps, pending queue counts, stale/coverage state, and distribution summaries. The PRD's `<=60 seconds after successful classification` is a provisional target excluding provider queue delays. The 30-second Overview poll is a UI cadence, not an ingestion, classification, detection, or notification SLA. OPS-04 requires confirmation before either target becomes a merge blocker.

## 12. Security and authorization evaluation

Use isolated test accounts, a synthetic database, and benign test inputs. Follow [SECURITY](SECURITY.md) acceptance criteria; do not use real customer data, live external recipients, or production credentials.

| Area | Procedure and expected result | Source/status |
|---|---|---|
| RBAC | Call each Admin-only upload, preview, confirm, ingestion/processing retry, reconciliation, configuration, and detailed-operations route directly as a Business User. Expect `403` and verify no bytes, artifact, preview, job, or mutation was created. Verify authorized Business User reads/actions remain within the API contract. | PRD, SECURITY SEC-AC04; backend authorization is required. |
| CSRF and sessions | For cookie-authenticated mutations, omit or alter the session-bound CSRF value and verify rejection with no side effects. Verify logout/expiry/deactivation behavior against the approved session policy. Login CSRF bootstrap and exact token lifecycle are unresolved; do not finalize this test or implement login until aligned in SECURITY/API. | SECURITY SEC-AC02/03; conditional on open session/CSRF decisions. |
| Prompt injection | Include synthetic feedback that asks to ignore rules, reveal secrets, override taxonomy/output shape, invoke tools, or embeds/quotes instructions. Verify it is handled only as data or explicit uncertainty, no tool or side effect occurs, and output still passes backend validation. | AI_SPEC §14, SECURITY SEC-AC08. |
| SQL injection | Supply harmless quote/metacharacter and SQL-shaped values through filters, request bodies, and CSV fields in the isolated database. Verify query structure, authorization, and stored records are unchanged outside the intended operation; errors/logs expose no raw SQL/database details. | SECURITY §13, SEC-AC13; parameterized-query invariant. |
| XSS | Put inert markup/script-like sentinel text in feedback, CSV headers/values, and rejection-report fields. Inspect every relevant browser surface and verify values render as inert text and create no active HTML or execution. | SECURITY SEC-AC14; UI inert-text rule. |
| CSV formula injection | Export test fields beginning with spreadsheet formula-leading characters, including headers and feedback values. Open or inspect the output with a safe spreadsheet-compatible validation procedure and verify values are escaped and not evaluated; verify stored source values remain unchanged. | SECURITY SEC-AC15; generated exports only. |
| CORS, secrets, and errors | If deployment configures cross-origin requests, test an unlisted origin and verify no permissive credentialed CORS response. Check bundles, responses, logs, and errors for secrets, tokens, raw feedback, provider payloads, paths, or stack traces. | SECURITY SEC-AC06/10/11/16; CORS test is conditional on cross-origin hosting. |

### Security procedure coverage IDs

The procedures below expand the general cases above and are the named evidence units used by the traceability matrix in Section 18.

| Procedure | Procedure and expected result | Source/status |
|---|---|---|
| SEC-P01 Password and account lifecycle | With disposable accounts, verify the selected adaptive salted hash is used and no password/hash appears in API, UI, logs, or audit. Confirm only active users can sign in, only a server-side session is established, the cookie has approved Secure/HttpOnly attributes, and logout, expiry, and deactivation revoke sessions as specified. Verify public self-registration/SSO and any unapproved reset/recovery path are unavailable, first Admin provisioning is restricted to the protected setup command, and deactivation plus session revocation is atomic. | SECURITY SEC-AC01/02/05. Hash parameters, password policy, initial-password delivery, first-login behavior, recovery, and exact session policy remain open prerequisites; do not invent values. |
| SEC-P02 CSRF and backend authorization | Omit or alter the session-bound CSRF value on each cookie-authenticated mutation; verify rejection with no side effects. Call every Admin-only route directly as a Business User, including upload, preview, mapping, confirm, job/report access, retry, reconciliation, and configuration; expect 403 and no bytes, artifact, preview, job, or mutation. Verify allowed Business User operations remain in scope. | SECURITY SEC-AC03/04; login CSRF bootstrap and exact token lifecycle remain open, so final CSRF verification is conditional on cross-document alignment. |
| SEC-P03 Secrets, logs, errors, rate limits, and CORS | Inspect repository content, frontend bundles, API responses, logs, audit snapshots, and errors using synthetic canary values; confirm no provider credential, password/hash, token, raw feedback, provider payload, email/message content, filesystem path, or raw exception leaks. Exercise malformed requests for stable safe problem responses/request IDs and no account-existence disclosure. Verify 429 behavior only against approved rate-limit settings. If cross-origin hosting is configured, an unlisted origin receives no permissive credentialed CORS response and authentication remains enforced. | SECURITY SEC-AC06/10/11/16. Rate limits and CORS deployment choice remain open; CORS test is conditional on cross-origin hosting. |
| SEC-P04 Upload limits, malformed CSV, mapping/hash, and artifact/path security | Test authorized and unauthorized actors. Enforce the approved inclusive 20,000,000-byte file-part ceiling while streaming and the 50,000 logical data-record limit after the header, counting blank records. Accept strict UTF-8 with at most one BOM at byte offset zero; reject malformed UTF-8, alternate encodings, malformed CSV structure, unsupported file kinds, and invalid file-level input without creating a preview. Exercise the approved reviews-v1, returns-v1, product-reference-v1, supplier-reference-v1, and batch-reference-v1 parser contracts; verify offset-aware timestamps, decoded-field byte/code-point limits, exact case-sensitive identifiers, and no trimming, case-folding, or Unicode normalization of accepted values. Confirm row-level partial acceptance, safe reasons, immutable exact-byte SHA-256/parser-version/mapping binding, and fail-closed re-preview after byte or mapping changes. Attempt path traversal, unknown/unresolved artifact IDs, resolution outside the configured root, and unauthorized report access; confirm no client path/filename controls storage and downloads use authorized backend routes. Exercise duplicate and changed-identity conflict behavior. | SECURITY SEC-AC07; API x-csv-input-contract and upload/preview contracts; DATA_MODEL upload/preview rows; PRD AC01/03/23; DAI-01/02/08 approved. The parser, byte/row limits, encoding/BOM, field rules, exact identifiers, mapping/hash, and conflict semantics are resolved; do not invent a different parser default. |
| SEC-P05 Untrusted input and injection | Use the approved synthetic prompt-injection set (ignore instructions, request secrets, taxonomy/output override, tool-use, hidden/quoted instruction); verify no instruction or side effect is executed and backend validation remains authoritative. Use harmless SQL-shaped inputs in filters, bodies, and CSV fields; verify parameterized handling, authorization, and no raw SQL leakage. Render markup/script sentinels from feedback, headers, row values, and rejection reports and verify inert text. Export formula-leading fields and verify safe escaping without changing source values. | AI_SPEC Section 14; SECURITY SEC-AC08/13/14/15; UI inert-text rule. |
| SEC-P06 Manual notification confirmation | Preview and abandon without an outbox row/send; reject unauthorized or inactive recipients, changed preview/hash, invalid CSRF, and mismatched idempotency use; replay the same confirmation without a duplicate event. Verify no unapproved/supplier address is contacted and acceptance is not displayed as delivery. | SECURITY SEC-AC09; PRD AC13/14. Run only against an approved local/sandbox boundary; no real email. Recipient directory, provider, preview-token details, and some idempotency/retry behavior remain open. |
| SEC-P07 Deployment, backup, restore, and rollback evidence | For non-production deployment, retain evidence of TLS, protected server-side secrets, least-privilege database/artifact permissions, the single API/worker topology and shared persistent local store, synthetic/permitted data, and health checks. Capture one consistent SQLite-plus-referenced-artifacts recovery set; restore it and verify database integrity, foreign keys, artifact existence, and stored hashes before restart. Demonstrate application rollback to the previous healthy version and verify health after API/worker restart; disclose any compatible-snapshot/data-loss step. | SECURITY SEC-AC12; PRD AC18. Host selection and backup mechanism, cadence, and retention remain open; this plans evidence without approving deployment. |

Security failures involving authorization, secret disclosure, active content, CSRF, or untrusted-input handling are blocking defects under the applicable approved acceptance criteria. Security-tool choice remains open in TECH_STACK. Report each test by procedure ID and SEC-AC ID, with evidence or a blocked/pending reason.

## 13. Ingestion, incident, and notification reliability

Run these tests against synthetic fixtures and the approved local/sandbox boundary only. Keep external provider calls outside database transactions and use fault injection at transaction boundaries where practical.

### Ingestion and classification idempotency

- **ING-P01 — Partial acceptance and rejection reports:** preview a fixture with valid rows, invalid rows, duplicate rows, and changed-identity conflicts. Verify valid rows may be accepted once, rejected rows receive downloadable row-level reasons, counts distinguish accepted/rejected/duplicate/conflict outcomes, and original feedback is never overwritten. Verify a Business User denial occurs before storage or job creation.
- **ING-P02 — CSV mapping and preview confirmation:** exercise required and optional target mapping, unique target assignments, optional-source IGNORE, and missing-required-target blocking. Confirm the validated mapping is bound to the immutable preview identity and verified hash; byte or mapping changes require a fresh preview, and confirmation applies only to the exact preview/hash reviewed. Test that mapping and confirmation remain Admin-only.
- **ING-P03 — Idempotency and processing mode:** replay the same preview/confirmation and source identities; identical rows are no-ops and changed payload is a conflict. Confirm retries preserve the original HISTORICAL_BATCH or INCREMENTAL_RESPONSES mode and do not duplicate accepted source rows, finalized Batch results, incidents, or notifications.

- Confirming the same immutable preview with the same idempotency key reuses the original outcome; repeated identical source rows are no-ops and are accepted once.
- Re-uploading the same source identity with changed payload produces a conflict and never overwrites original feedback.
- A denied Business User upload creates no artifact, preview, or ingestion job.
- Retries preserve the original `HISTORICAL_BATCH` or `INCREMENTAL_RESPONSES` mode and create a new immutable classification attempt. Replayed finalized Batch results do not double-count; missing, duplicate, malformed, and unknown custom IDs are handled by correlation ID rather than line order.
- Failed, uncertain, and needs-review classifications do not become no-defect records or confirmed complaints.

### Detection and incident behavior

- **DET-P01 — Detection and episode behavior:** exercise the locked evaluation algorithm in Section 6 with exact product/supplier/batch/logical-defect identity, event-window boundaries, complete nonzero and complete zero baselines, insufficient/unknown coverage, unresolved linkage, late arrivals, and held-out eligible/ineligible truth cases. Verify only qualifying current monitoring results create warning predictions, one-to-one matching is deterministic, no individual row inflates episode recall, and no ineligible scenario enters the denominator. Verify historical recomputation does not apply an incident/outbox change.
- **INC-P01 — Incident transitions, recurrence, and chronology:** verify only the approved NEW -> ACKNOWLEDGED -> INVESTIGATING -> RESOLVED transitions and qualifying RESOLVED -> REOPENED -> INVESTIGATING path are accepted. A recurrence at or before the approved 30-day boundary reopens the same incident; a later recurrence creates a linked episode. Assert actor/system, UTC timestamp, before/after state, and ordered audit chronology; stale or conflicting transitions leave a reviewable audit result and do not create a second open incident.
- **INC-P02 — Investigation notes:** append notes through the authorized incident workflow; verify each is attributed, timestamped, immutable, and shown in chronology with status events. Corrections are new notes; editing/deleting a prior note is unavailable. Confirm append and transition history remain linked to the incident/episode.

- Replaying identical inputs/rule/policy versions yields one detection result and no duplicate incident event or outbox intent.
- A qualifying current result whose application is interrupted remains recoverable; incident state, audit, required outbox data, and application completion commit together or roll back together.
- A changed input fingerprint supersedes stale pending work and queues the latest recomputation; a stale result creates no incident or notification.
- Historical recomputation, insufficient coverage, and `LINKAGE_PENDING` evidence do not apply incident or automatic-notification changes. Late arrivals, coverage changes, and Admin linkage reconciliation recompute affected windows while retaining prior evidence.
- Verify the approved 30-day recurrence boundary: exactly 30 days reopens the same incident; later recurrence creates a linked episode. Concurrent/recovered attempts cannot create two open incidents for one cluster. Decreasing counts do not auto-resolve an incident.

### Notification behavior

- **NOT-P01 — Notification state and audit:** verify manual preview/abandonment, explicit confirmation, role/recipient checks, idempotent replay, exact audit action, provider acceptance versus delivery distinction, and no real external send. Exercise cooldown/escalation only for the approved semantics; keep unresolved route, provider, preview-token, retry, and cooldown edge cases blocked.

- Previewing or abandoning a manual notification creates no outbox row and sends nothing. Confirmation requires an authorized actor, approved recipients, CSRF, exact preview binding, and an idempotency key; same-command replay returns the same event, while conflicting key reuse is rejected.
- A current qualifying notification-triggering incident change and its outbox event/recipient snapshot are atomic. Provider unavailability does not erase the incident or required durable outbox intent. A sandbox acceptance is `ACCEPTED`, never proof of delivery.
- Verify the approved 86,400-second same-severity cooldown per incident/severity across routes and escalation bypass only where the approved timestamp anchor and trigger semantics allow a determinate test. Unknown send outcomes are not automatically resent absent provider verification or a separately approved policy.
- Do not send real email. A concrete capture sink/provider, recipient directory/routing, cooldown timestamp anchor, re-crossing/severity-decrease behavior, preview-token lifecycle, retry parameters, and provider verification remain unresolved. ALERT_SPEC v0.2 is still a draft; its cases do not independently approve implementation.

## 14. Local automated verification and pre-merge evidence

Backend/API pytest with FastAPI TestClient, frontend Vitest with React Testing Library, and repeatable local PowerShell check scripts are approved in PP-001. Under ARC-06 and PRD change RC-01, local automation, a documented pre-merge checklist, and retained evidence replace hosted CI merge gates. GitHub Actions and any other hosted CI merge-gate service are excluded. The checklist requires passing results on the exact revision proposed for merge and records commands, revision identity, results, and evidence. A required failure blocks checklist approval until corrected and rerun. The intended check layers are:

| Check layer | Local automated verification and checklist behavior | Status |
|---|---|---|
| Deterministic contract and invariant checks | Run automated unit/integration checks for schema/state rules, source-link integrity, RBAC, CSV validation, CSRF, injection safety, idempotency, detection evidence, and local notification persistence. Fail on violation of an approved acceptance criterion; record required passing results in the checklist. | Required verification methods. PRD lists 100% strict-schema validity for persisted completed results, 100% source-reference integrity in fixtures, zero duplicate incidents, no unauthorized uploads, and no unconfirmed manual sends among planning-default gates. |
| Classification quality | Calculate and report per-class precision/recall/F1, confusion matrix, uncertainty, and configured regression results. Record failures against approved class-specific gates in the checklist. | EV-02 Pending Calibration; no class threshold or macro-accuracy target is approved. |
| Detection quality | Calculate held-out episode recall, false positives, and misses. Record failures against only the approved EV-03 gate and denominator in the checklist. | PRD's `>=90%` is provisional; EV-03 Pending Calibration. |
| Performance/freshness | Publish p95 and latency/freshness measurements under the recorded test conditions. | OPS-04 approves these as provisional measurement targets, not pre-merge blockers; confirm before treating them as checklist gates. |
| Cost | Publish token and cost-per-1,000 reports, including retries and both API paths. | EV-05 reporting approved; no budget or cost gate approved. |

Before EV-01/02/03 decisions are resolved, local scripts may calculate available metrics for development, but must label them exploratory and must not claim a final held-out pass or invent a blocking quality threshold. Once configured, a gate change requires a decision record and a plan/report update; model/prompt/schema/taxonomy changes require versioned regression evaluation. PRD AC17's deliberate failing-test/restoration demonstration remains required as local evidence; retain both run results and revision identities. It is separate from deployment rollback evidence.

## 15. Held-out protection and leakage prevention

- Split by unique source record and planted scenario/episode, as AI_SPEC requires. Keep exact duplicates, near-duplicate paraphrases, shared story/template families, and all records belonging to one episode in one partition.
- Keep planted development episodes distinct from held-out episodes. Do not tune prompt wording, class definitions, model choice, detection thresholds, coverage policy, sentiment threshold, episode matcher, or evaluator on held-out content or results. Any held-out result that guides one of these changes consumes that set; lock a fresh held-out set before a new final claim.
- Freeze approved taxonomy semantics and label guide before the split is locked. A taxonomy or scenario change that crosses partitions invalidates the affected split and requires a new manifest.
- Store partition membership and source/episode group IDs in a manifest; hash the manifest and evaluation inputs. Keep held-out labels separate from the development view until the evaluated configuration is frozen.
- Freeze the evaluation code and metric definitions with the dataset manifest. Record every held-out run, including failed or exploratory runs, and whether the set was unsealed or used for tuning.
- Do not claim stable class or scenario results when EV-01 minimum representation is not met. Report counts and uncertainty, and keep the class/episode gate pending.

The final held-out record count, class minimums, episode count, scenario minimums, and any confidence/representation sufficiency criteria are pending EV-01. This plan deliberately sets no split percentage or sample size.

## 16. Required evidence and report format

Each evaluation report should include:

1. **Run identity:** date/time in UTC, code revision, environment, dataset/manifest hash, evaluated population, model ID, API path, prompt/schema/taxonomy versions, detection rule and coverage-policy versions, comparator version, and local script/tool identifiers.
2. **Calibration boundary:** which parameters were tuned on development, which were frozen, which decisions remain pending, and whether held-out data was ever inspected or consumed.
3. **Classification:** per-class support, precision, recall, F1, confusion matrix, primary/secondary agreement, gold-uncertain outcome distribution, NEEDS_REVIEW capture and overconfident-definitive rates, attempt-selection status, uncertainty/failure counts, schema validity, and descriptive intervals.
4. **Coverage and linkage:** record/state counts, classification-coverage numerator/denominator, source-coverage intervals/status, classification completeness counts, per-field linkage accuracy, exact-chain accuracy, false-link count, and drill-down integrity.
5. **Detection and lead time:** eligibility definition, detection horizon and matcher version, eligible and ineligible scenario counts/reasons, detected/total episodes, false positives including suppression violations, misses, interval, per-episode detector/comparator timestamps, paired lead-time gains, and descriptive intervals.
6. **Path and operations:** Responses/Batch paired-valid agreement and completion rates; tokens; recorded and missing usage/cost; retry cost; latency distributions; dashboard p95; event/ingestion/classification-to-display freshness; SQLite contention conditions; and backup/restore/rollback evidence where applicable.
7. **Security and reliability:** pass/fail and evidence reference per applicable SEC-P and SEC-AC criterion, account/session/CSRF/RBAC outcomes, prompt-injection cases, upload/mapping/hash/path checks, ingestion/idempotency results, incident/outbox recovery, notification states, backup/restore/rollback proof, and any unresolved or blocked tests.
8. **Gate outcome:** each configured gate, its decision-register authority, observed result, pass/fail/not-configured state, and any failure/exception. A pending gate is shown as pending, never as passed.
9. **Limitations and conclusion:** class imbalance, unsupported or insufficient coverage, small scenario counts, provider/model variability, missing usage values, non-production environment, and what the evidence does and does not establish.

Retain the dataset/label manifests, locked configuration, evaluator output, confusion matrix, security triage, local check output, completed pre-merge checklist, and environment notes as capstone evidence. Use IDs and aggregates in reports; keep even synthetic raw feedback in the governed data path and out of generic logs. Record exact commands/configuration in the implementing tickets and scripts when introduced. The test runners and local PowerShell check runner are selected; no hosted CI service is used.

## 17. Pending decisions and approval gates

| Decision | Current status | Required before |
|---|---|---|
| EV-01 held-out record, class, episode, and scenario counts/minimum representation | Pending Calibration. Proposed manifest structure and representation strata are in §4.1; final sizes, per-class/scenario minimums, split proportions, and sufficiency rules remain unselected. | Locking the final held-out set or claiming stable metrics. |
| EV-02 class-specific precision/recall or regression gates | Pending Calibration. Development-only calibration method is in §3.1; numeric class gates, gate form per class, support/sufficiency rule, and pre-merge checklist behavior remain unselected. | Final classification gates and held-out evaluation approval. |
| EV-03 episode denominator, matching/detection horizon, and recall gate | Pending Calibration. Proposed exact-identity one-to-one matcher and half-open window are in §6.1-6.2; eligibility rules, horizon value, any sufficiency rule, and gate remain unapproved. PRD `>=90%` remains provisional. | Final detection evaluation or numeric pre-merge gate. |
| DAI-06 coverage scope, interval-combination/completeness evidence, and classification-completeness gate | Method approved; parameters Pending Calibration. | Final historical baseline interpretation and automatic detection activation. |
| PB-01 detection minimum counts, ratios, and any baseline-support rule | Pending Calibration; PRD values are hypotheses. | Activating incident-producing detection and final detection evaluation. |
| DAI-05 model ID and initial approved taxonomy/issue-code seed | Selection process approved; values unresolved. | AI implementation and final classification evaluation. |
| Authoritative completed-classification attempt selection and applicability | Latest validated definitive result within each explicitly applicable taxonomy version is approved and aligned. An evaluation run uses its pinned taxonomy version; the Product Owner approved no-fallback, version-scoped general aggregates on 24 November. | Scoring uses the pinned version and approved selector. Initial taxonomy seed/issue-code policy, model selection, and calibration remain separate pending gates for their dependent work. |
| EV-04 sentiment comparator method and threshold | Selection/freeze process approved; comparator not yet selected. | Held-out lead-time comparison. |
| EV-05 cost limit | Reporting approved; no spend limit or gate approved. | Any cost-based blocking decision. |
| Cost-per-1,000 API denominator | AI_SPEC defines eligible feedback records; API_SPEC exposes the cost-per-1,000 field without documenting its denominator. This plan uses the AI_SPEC eligible-record denominator. | Align API/operations metric semantics before exposing the value as an API result. |
| OPS-04 performance targets | Provisional measurement targets approved; checklist gate status requires confirmation. | Turning p95/freshness into blocking checklist gates. |
| PB-05 dashboard KPI definitions | Glossary creation approved; active warnings, critical warnings, and products-at-risk definitions remain unresolved. | Numeric correctness evaluation for those KPI values; until then verify pending/null handling only. |
| Test runners and local check runner | Approved in TECH_STACK v1.0: pytest/FastAPI TestClient, Vitest/React Testing Library, repeatable local PowerShell scripts, and a documented pre-merge checklist. No browser E2E framework is selected. | Implement checks with the relevant tickets; preserve automated acceptance coverage and security requirements. |
| Verification and pre-merge evidence | Approved in ARC-06 and PRD change RC-01: local PowerShell automation, documented checklist, exact-revision results, and failure/restoration evidence. GitHub Actions and hosted CI merge gates are excluded. | Implement selected scripts and retain checklist evidence with applicable tickets; EV-01/02/03 still control final held-out claims and numeric quality gates. |
| SECURITY login CSRF bootstrap, session/cookie policy, and other listed security dependencies | Open in SECURITY/API. | Complete authentication/CSRF implementation and corresponding final security evaluation. |
| ALERT_SPEC approval, route/provider/recipient choices, preview-token lifecycle, retry/uncertain-send parameters, and cooldown edge cases | Draft/open as recorded in ALERT_SPEC and Decision Register. | Full notification integration and edge-case evaluation; real sends remain out of MVP scope. |

## 18. PRD and Security acceptance-criteria traceability

The matrices below map every PRD acceptance criterion and every SECURITY specification test criterion to a planned procedure or evidence item. A mapped procedure is not an assertion that the behavior has been implemented or passed. Conditions and open approvals remain in force.

### 18.1 PRD acceptance criteria

| PRD ID | Evaluation procedure(s) | Coverage/evidence |
|---|---|---|
| AC01 | SEC-P02, SEC-P04 | Direct Business User upload denial; verify no bytes, artifact, preview, or job. |
| AC02 | ING-P01, ING-P03, PATH-P01 | Admin preview/confirmation, single persistence, explicit import mode, automatic classification path, and one-time acceptance. |
| AC03 | ING-P01 | Partial acceptance and downloadable row-level rejection reasons; reference imports need no feedback mode. |
| AC04 | ING-P03, INC-P01 | Duplicate/retry idempotency, preserved import mode, and no duplicate source/incident. |
| AC05 | AI-P01, LINK-P01 | Strict-schema completed classification linked to the original source record. |
| AC06 | SEC-P05 | Adversarial feedback remains data; no instruction or side-effect execution. |
| AC07 | PATH-P01 | Historical import dispatches through Batch; finalized results correlate and count once. |
| AC08 | PATH-P01, OPS-P01 | Incremental import uses Responses; dashboard reflects completed work and freshness is measured. |
| AC09 | DET-P01 | Planted spike yields reproducible counts/baseline evidence under a frozen rule; PB-01 remains pending. |
| AC10 | INC-P01, NOT-P01 | Existing incident updates without duplication; same-severity notification behavior is tested only where approved. |
| AC11 | NOT-P01 | Escalation behavior is verified only for approved trigger/cooldown semantics; open edge cases remain blocked. |
| AC12 | LINK-P01 | Incident evidence resolves to the correct review/return, supplier, batch, and calculation rationale. |
| AC13 | NOT-P01, SEC-P06 | Authorized confirmation and exact audit action in a local/sandbox provider boundary; no real send. |
| AC14 | NOT-P01, SEC-P06 | Abandoned/unconfirmed manual composition creates no notification or send. |
| AC15 | INC-P01, INC-P02 | Valid transitions and append-only investigation notes appear in actor/time/state chronology. |
| AC16 | OPS-P01 | Ingestion/classification freshness and delayed/failed processing state are visible and measured. |
| AC17 | Sections 3, 5, 6, 8, 10, 14, and 16 | Evaluation metrics, approved configured regressions, local verification output, exact-revision checklist, and failure/restoration evidence. Held-out claims/gates remain blocked until EV-01/02/03 approval. |
| AC18 | SEC-P07 | Non-production rollback restores the previous healthy version and passes health checks; evidence is external to runtime APIs. |
| AC19 | LINK-P01, ING-P02, DET-P01 | LINKAGE_PENDING suppression, no fabricated IDs, and recomputation after Admin mapping reconciliation. |
| AC20 | DET-P01, COV-P01 | Complete zero-baseline count-only behavior with no infinity multiplier; configured PB-01 values remain pending. |
| AC21 | DET-P01, COV-P01 | Insufficient coverage is visible and suppresses automatic warning/email behavior under the approved policy. |
| AC22 | INC-P01 | At or before the approved 30-day boundary, reopen the same incident; later recurrence creates a linked episode. |
| AC23 | ING-P01, ING-P03 | Changed payload for an existing identity is reported as a conflict and never overwrites source text. |
| AC24 | AI-P01, COV-P01 | Pending/needs-review outputs are excluded from definitive complaints and represented as incomplete coverage, not NO_DEFECT. |

### 18.2 Security Specification acceptance criteria

| SECURITY ID | Evaluation procedure(s) | Conditions/evidence |
|---|---|---|
| SEC-AC01 | SEC-P01 | Hash storage and non-disclosure; selected algorithm/parameters must be approved first. |
| SEC-AC02 | SEC-P01 | Active-account sessions, cookie/storage controls, expiry/logout/deactivation; exact session policy remains open. |
| SEC-AC03 | SEC-P02 | Invalid/missing CSRF blocks mutations; login bootstrap/token lifecycle must be aligned first. |
| SEC-AC04 | SEC-P02, SEC-P04 | Backend Admin authorization, including upload denial before artifact/job creation. |
| SEC-AC05 | SEC-P01 | No self-registration/SSO, protected initial Admin, atomic deactivation/revocation. |
| SEC-AC06 | SEC-P03 | No provider credentials in repository, bundle, prompts, logs, snapshots, responses, or errors. |
| SEC-AC07 | SEC-P04 | Limits, malformed/unsupported uploads, mapping/hash binding, identity conflicts, path escape, authorized artifact access, fail-closed hash/ID behavior. |
| SEC-AC08 | SEC-P05 | Prompt-injection cases remain data/uncertainty, with no tool or side effect. |
| SEC-AC09 | SEC-P06 | Preview, recipient, CSRF, hash, idempotency, replay, and no-real-recipient checks. |
| SEC-AC10 | SEC-P03 | Log/audit review for all prohibited sensitive or raw content. |
| SEC-AC11 | SEC-P03 | Safe stable errors/request IDs and approved 429 guidance; numeric rate limits remain open. |
| SEC-AC12 | SEC-P07 | TLS, secret/storage controls, single-instance topology, health, consistent backup/restore, and rollback evidence. |
| SEC-AC13 | SEC-P05 | SQL-shaped inputs do not change query structure, permissions, or expose database details. |
| SEC-AC14 | SEC-P05 | User-controlled content remains inert in UI surfaces and reports. |
| SEC-AC15 | SEC-P05 | Formula-leading export fields are safely escaped; source values remain unchanged. |
| SEC-AC16 | SEC-P03 | Unlisted-origin CORS behavior, conditional on cross-origin configuration; authentication remains independent. |

Final evaluation-plan approval requires the EV-01/02/03 calibrations and review of the pending methods identified above. This plan does not clear any implementation, detection activation, notification activation, deployment, email, or data-use gate recorded by AGENTS.md or the specifications.

## 19. Consistency review

The traceability matrices now cover every PRD AC01-AC24 and SECURITY SEC-AC01-SEC-AC16. The new procedures add account lifecycle, upload/parser and preview/hash/path checks, joint backup/restore and rollback evidence, partial ingestion and mapping confirmation, incident transitions/recurrence, and investigation-note/audit chronology. They identify open decisions as conditional or pending rather than assigning test defaults.

EV-01 proposes record/episode strata and a manifest without numeric holdout sizes; EV-02 proposes development-only class-gate calibration without numeric gates; EV-03 proposes exact-identity, one-to-one matching and a half-open detection horizon whose value remains pending. These proposals leave EV-01/02/03 Pending Calibration in the Decision Register, preserve the PRD's >=90% recall as provisional, and retain the approved attempt-selection/applicability policies as fixed methodology without approving model or calibration values.

The plan preserves the PRD's evaluation scope, synthetic-data boundary, taxonomy and source lineage, UTC event windows, 30-second dashboard polling caveat, and separate classification/detection/lead-time/source-link/performance/cost evidence. It uses AI_SPEC's shared Responses/Batch contract, explicit uncertainty handling, split by source and scenario, backend-only prompt-injection boundary, per-class metrics, path cost reporting, and pending gates. It follows the security baseline's SEC-AC13–16 tests and keeps the conditional CSRF/CORS dependencies visible. It also follows the conditional API/Data Model/UI baselines for role checks, `LINKAGE_PENDING`, coverage visibility, immutable lineage, and idempotent result application.

ARC-06's local verification and pre-merge evidence approach is approved under PRD change RC-01. No PRD requirement specifically requires browser E2E evidence; the PRD's live end-to-end demo and integration flows remain system-level evidence and are not defined as browser automation. Workshop evaluation, security, deployment, rollback, runbook, live-demo, and failure/restoration deliverables remain required. One contract detail remains ambiguous: API_SPEC exposes an estimated-cost-per-1,000-records field without defining its denominator, while AI_SPEC specifies eligible feedback records. This plan follows the AI_SPEC definition and flags API alignment before implementation exposes the value. The plan does not promote the DETECTION_SPEC v1.1 draft or ALERT_SPEC v0.4 draft to approved implementation specifications. It does not treat PRD's provisional `>=90%` planted-episode recall or OPS-04's `<=3 seconds`/`<=60 seconds` targets as approved pre-merge gates. EV-01, EV-02, EV-03, DAI-06, and PB-01 remain pending; PP-005's taxonomy-version applicability policy was approved 24 November. Final evaluation approval and dependent implementation/activation remain gated accordingly.
