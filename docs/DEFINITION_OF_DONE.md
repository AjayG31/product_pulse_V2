# ProductPulse Definition of Done

**Purpose:** A practical closure checklist for solo, ticket-driven development with Codex.  
**Applies to:** Decision-resolution, implementation, evaluation, and deployment tickets.  
**Milestone workflow:** Approved by the Product Owner on 21 November 2026.  
**Requirements source:** [PRD](PRD.md)  
**Planning and dependency order:** [Implementation Plan](IMPLEMENTATION_PLAN.md)  
**Decision status:** [Decision Register](DECISION_REGISTER.md)

## 1. How to use this document

Use this checklist with the approved ticket and the specifications it names. The PRD defines product behavior. The Decision Register is authoritative for whether a choice is Approved, Proposed, Open, Deferred, or Pending Calibration. The Implementation Plan defines ticket dependencies and readiness. The API, data model, security, AI, detection, alert, evaluation, UI, architecture, and stack specifications own their respective implementation contracts.

An approved design baseline can still be conditional. Before work starts, confirm that the ticket's listed prerequisites are closed and its dependent specifications are approved at the scope the ticket needs. Do not infer an implementation choice from a proposal, draft, example, or pending value. If sources conflict, stop and reconcile them before proceeding.

Keep implementation work bounded to one ticket at a time. Per [AGENTS.md](../AGENTS.md), one approval authorizes a bounded milestone, while each ticket retains its own readiness gates and evidence requirements. This document does not make a blocked ticket ready or authorize work outside an approved scope.

### 1.1 Milestone authorization and reporting

One explicit human approval authorizes the named implementation tickets in a milestone. The milestone brief must include the ticket IDs, scope and exclusions, execution order and dependencies, specification versions, readiness status, per-ticket automated acceptance checks and tests, and evidence to retain. Include tickets that are Implementation Ready or explicitly `IR after` named earlier implementation tickets in the same milestone. All non-ticket prerequisites must already be approved and resolved. Recheck readiness before starting each ticket; it cannot start until every dependency is complete and its acceptance evidence passes.

The milestone approval authorizes implementation within the listed scope. It does not decide an unresolved product or security question, approve a change to an approved specification, waive a security check, authorize an external action, or activate gated functionality. These require their own explicit approval. If a decision or specification conflict appears, stop the affected work, record the issue and dependency, and keep dependent tickets blocked.

If a prerequisite decision or dependency for implementation is unresolved, do not start—or, if already underway, stop—the affected implementation ticket and all dependent tickets. A decision-resolution ticket may continue only within its approved evidence-gathering scope and cannot settle the decision without the Product Owner's explicit disposition. If a mandatory test fails, fix it only within the approved ticket and milestone scope; if it cannot be fixed there, stop the affected work, report the failure, and keep the ticket incomplete. If a security or authorization issue is discovered, stop affected work immediately, preserve safe evidence, report the issue and proposed remediation, and wait for explicit user direction before resuming. If a change to an approved requirement or specification is necessary, stop and obtain explicit approval before changing the approved source or dependent implementation. If a consequential external action needs approval, stop before the action and obtain that approval. Independent tickets may continue only if their prerequisites are satisfied and they remain within the approved scope.

Each implementation ticket must retain its own criteria-to-check mapping and automated test evidence. At the end of the milestone, provide one consolidated review report listing each ticket's status, checks and test results, review findings, approved scope changes, unresolved gates, and risks. There is no separate human implementation or closure approval per ticket in an approved milestone. A ticket with a failed or missing required check remains incomplete and is reported as blocked or partial.

## 2. Decision-resolution tickets

A decision-resolution ticket is complete when it has:

- Named the decision ID, the owning specification, the question to resolve, and the implementation or evaluation work it blocks.
- Reviewed the relevant requirements and recorded enough evidence, options, trade-offs, and a recommendation for the Product Owner to make the decision.
- Recorded the Product Owner's explicit disposition: approve, reject, defer, or leave unresolved. A proposal or Codex recommendation is not approval.
- Updated the Decision Register and every affected specification consistently when a decision is approved or changed. Updated the Implementation Plan's dependency/readiness notes when the decision changes ticket gates.
- Preserved open conditions and downstream blockers when the outcome is deferred or unresolved. Did not create application code, tickets, migrations, or configuration defaults as a side effect of decision work.

Close the decision ticket only after its disposition and evidence are recorded. A deferred or unresolved decision can be closed as decision work only when the Product Owner explicitly accepts that disposition; dependent implementation remains blocked.

## 3. Required closure criteria for every implementation ticket

Every implementation ticket must require and record all of the following before it can be closed:

1. **Approved prerequisites and specifications.** The ticket lists its dependency IDs, relevant specification versions and approval scope, and any required decisions. All prerequisites are satisfied. Conditional baselines have their applicable conditions resolved. The ticket is named in an approved milestone and passes a readiness check immediately before work starts. Dependencies inside the milestone must be completed first.
2. **Acceptance criteria satisfied.** Each ticket criterion is mapped to implementation and review evidence. Related PRD acceptance criteria are included where applicable. No requirement is silently weakened, omitted, or replaced with an unapproved default.
3. **Automated acceptance checks and tests passing.** Every implementation ticket has automated checks mapped to its acceptance criteria, focused automated coverage for new or changed behavior, and passing relevant existing checks. Include contract, integration, recovery, evaluation, or security checks when the changed boundary needs them. Record commands, results, and evidence links in the ticket; explain any unavailable or blocked check instead of implying it passed. If a criterion inherently requires human observation, record why and the reproducible manual evidence in addition to applicable automated checks.
4. **Security and authorization checks.** Verify the relevant permitted and denied paths at the backend boundary, including direct API calls and side effects where applicable. Check input handling, output exposure, secrets, logging, and error behavior for the changed surface. If a ticket adds no security or access boundary, record why and confirm it did not create one.
5. **No unintended changes.** Review the complete change against the ticket scope. Remove unrelated changes and generated or sensitive artifacts. Record any necessary scope adjustment in the ticket and get it approved before including it.
6. **Codex code review and verification evidence.** Codex reviews the completed change against the ticket, acceptance criteria, and relevant specifications; resolve findings or record their approved disposition. Record automated acceptance results for the ticket. For visual or interactive criteria, verify actual UI states; for backend criteria, verify behavior through the applicable API or operational surface. A human performs a manual check when the criterion requires human observation or the governing specification requires it.
7. **Updated documentation and evidence.** Update affected specifications, user/developer documentation, and runbook material when behavior or operations change. Link concise evidence from the ticket: test results, manual verification, security/review notes, and any required screenshots, evaluation report, or deployment artifact. Keep sensitive values and raw feedback out of general-purpose logs and evidence.
8. **Milestone reporting.** Include the ticket's status and evidence in the consolidated milestone report. A separate Product Owner implementation or closure approval is not required for each ticket in an approved milestone. Explicit approval remains required for decision dispositions, approved-spec changes, security exceptions, consequential external actions, and any scope expansion.

Keep evidence in the ticket or its existing evidence location. A small ticket needs a concise checklist and links, not a separate report unless a specification requires one.

### 3.1 Consolidated milestone review

At milestone end, provide one report with the included ticket IDs and outcomes; per-ticket acceptance criteria, automated check and test evidence; code-review findings and dispositions; approved changes to scope or specifications; unresolved decisions and gates; and residual risks or limitations. Report the milestone complete only when every included implementation ticket meets its Definition of Done. If a ticket is blocked, identify its failed or missing gate and report the milestone as partial or blocked. This review replaces repeated per-ticket manual closure reviews; it does not replace any separately required approval.

## 4. Additional criteria by ticket type

### 4.1 Application implementation

- Implements only the approved ticket scope and preserves the existing architecture and product behavior.
- Exercises the changed acceptance path, including relevant loading, empty, error, stale, or recovery states; UI checks do not substitute for server-side enforcement.
- Preserves source-to-result traceability, truthful status/freshness, and audit behavior where the feature uses them.
- Keeps independent work moving without presenting undefined metrics as zero or gated functionality as active.

### 4.2 API and database changes

- Updates the API contract, data model, and affected UI or security contracts together. Request/response shapes, validation, errors, authorization, pagination, idempotency, and side effects agree across the implementation and specifications.
- Confirms the server enforces the API contract even when client controls are bypassed. Exercise success, invalid input, forbidden access, conflict/replay, and relevant failure paths.
- Uses only the approved SQLite design: one primary relational database shared by the API and one worker on persistent local storage. Verify relevant constraints, foreign keys, uniqueness, and idempotency; keep write transactions short and provider calls outside them.
- Uses only an approved ORM and migration approach. Before a schema or data change, verify the forward change, existing-data handling, integrity, and the approved recovery/rollback procedure. Do not assume application rollback reverses a schema change. Tooling or migration policy that remains open is a prerequisite, not a default to choose in the ticket.
- For artifacts, keep uploaded CSVs and generated rejection reports in protected storage outside public delivery and Git. Verify opaque-ID resolution, hash binding, authorization, and database/artifact consistency where applicable.

### 4.3 AI and detection functionality

- Keeps OpenAI calls, credentials, and provider payload handling on the backend worker. Uses the approved common, versioned contract for Responses and Batch work, records required lineage/usage, and validates provider results before persistence.
- Tests malformed, refused, unsupported, uncertain, and needs-review outcomes. None may be converted to `NO_DEFECT` or included in confirmed counts. Feedback remains untrusted data; it cannot change instructions, taxonomy, linkage, or cause tool use or side effects.
- Keeps defect counting, coverage decisions, thresholds, severity, incident eligibility, and notification eligibility deterministic and server-side. Model hints are not authoritative rules.
- Verifies source identity and evidence grounding, immutable attempt/result identity, idempotent recomputation, UTC window handling, late-arrival behavior, and `LINKAGE_PENDING` handling when relevant.
- Keeps draft/review work separate from activation. Detection, incident-producing current results, and automatic notifications remain fail-closed until classification-attempt authority, the detection specification, coverage/calibration, applicable evaluation decisions, the alert specification, and routing/provider decisions are explicitly approved. Manual notifications also remain gated on approved directory, provider, and preview-token requirements. Never fill a pending threshold, coverage parameter, model, taxonomy, route, or provider value with an invented default.
- Reports classification, detection, coverage, path consistency, cost, and latency using the approved definitions and versions. Treat an unapproved gate as pending, not passed.

### 4.4 Security-sensitive changes

- Covers the changed trust boundary with positive and negative checks: unauthenticated, Business User, Admin, inactive/revoked account, and resource/state authorization cases as applicable. Confirm denied actions cause no upload, preview, job, incident, notification, or other protected side effect.
- Checks input validation and safe rendering/export, CSRF and CORS behavior where applicable, path/artifact access, parameterized database use, rate-limit behavior under approved policy, and stable redacted errors.
- Verifies that passwords, session/CSRF/recovery/preview tokens, API keys, provider payloads, raw feedback, message content, and other restricted values do not leak to browser bundles, logs, generic audit snapshots, or errors.
- Tests prompt injection and formula-leading export values at their relevant boundaries. Preserve source values while making rendered text and exported cells inert.
- Uses only synthetic or permitted public non-sensitive data. No real email, supplier email, or external side effect occurs without the separate explicit approval required by the governing specification and AGENTS.md.

### 4.5 Local automated verification and evaluation evidence

- Uses the approved evaluation protocol, definitions, dataset custody, and versions. Freeze and hash the held-out manifest/configuration before final evaluation; keep grouped duplicates and planted episodes within one partition and record any holdout use that informed a change.
- Reports denominators, support, failures, uncertainty, limitations, and actual results. Do not claim stable results without approved representation criteria or treat provisional targets as gates.
- Runs the repeatable local PowerShell verification scripts selected in PP-001 and records the exact command, code revision, result, and evidence with the ticket. Backend/API checks use pytest and FastAPI TestClient; frontend checks use Vitest and React Testing Library. Preserve all applicable automated functional, integration, authorization, security, and evaluation checks.
- Before merge approval, complete the documented pre-merge checklist against the exact proposed revision. Every required check must pass; record its command, result, revision, and evidence reference. A failed, skipped, or unavailable required check blocks checklist approval until resolved and rerun. Local scripts report outcomes; they do not automatically prevent a merge, so the documented review process must verify checklist completion.
- Record each pre-merge review with: exact revision; backend/API pytest and FastAPI TestClient results; frontend Vitest and React Testing Library results; applicable security-check results; applicable evaluation command, manifest/configuration identity, and gate outcomes; reviewer/date; and links to retained output. Mark checks not applicable only with a ticket-specific reason. Do not record a pending threshold as passed.
- Keep exploratory metrics non-blocking while decision status is pending. Use only explicitly approved thresholds and gates; pending metrics must be labeled pending, not passed. A gate change requires an approved decision and aligned PRD/specification/evaluation updates.
- For the applicable capstone ticket, retain evidence of a deliberately failing automated test followed by restoration to a passing state, including both revision identities, commands, and results. Keep this local verification demonstration distinct from deployment rollback evidence under AC18.

### 4.6 Deployment, backup, and rollback

- Confirms the target and its suitability are explicitly approved before deployment. Provider selection/suitability work is a decision ticket; it does not itself deploy. Deploy only to the approved non-production scope and after explicit deployment approval.
- Verifies the approved single-instance topology: one API and one separate worker share one persistent local SQLite file and protected artifact directory. Verify TLS, protected server-side secrets, least-privilege storage, health checks, logs, and required operational visibility.
- Captures SQLite and every referenced artifact as one coherent recovery set using the approved backup method. Restore with API and worker stopped; verify database integrity, foreign keys, artifact references, and hashes before restart.
- Demonstrates rollback to the prior healthy application version and verifies health afterward. Separately prove any required schema/data recovery; application rollback alone does not reverse a migration.
- Updates the solo-developer runbook with startup/restart, failure visibility, recovery, backup/restore, and rollback steps. Record target, version, check results, and known limitations without including secrets.

## 5. Not done

A ticket is not done when any required criterion is unchecked, a test or approval is implied but not recorded, a dependent decision is still open, the change exceeds its approved scope, or evidence cannot be reviewed. Mark the ticket blocked or return it for the missing work; do not close it as complete. Do not use this checklist to promote a draft, proposal, or conditional design baseline to approved status.
