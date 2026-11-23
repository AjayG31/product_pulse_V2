# ProductPulse Security Specification

**Version:** 1.1  
**Status:** Approved — Design Baseline  
**Approval date:** 22 November 2026  
**Requirements source:** [PRD](PRD.md) v1.7  
**Decision basis:** [Decision Register](DECISION_REGISTER.md) v1.8  
**Related specifications:** Architecture v1.4 (Approved); Data Model v1.5 (Approved — Design Baseline, conditional); API_SPEC.yaml v1.5.0 (Approved — Design Baseline, conditional); UI_SPEC.md v0.4 (Approved — Design Baseline, conditional); Tech Stack v1.1; AI_SPEC.md v1.0 (Approved — Design Baseline); ALERT_SPEC.md v0.2 (Draft); DETECTION_SPEC.md v1.1 (Draft clarification; v1.0 remains the Approved — Design Baseline).

## 1. Purpose and approval boundary

This document defines the security boundary and records the details that must be decided before dependent implementation. The PRD remains the source of product requirements. The Decision Register supplies approved security decisions and their limits. The API and Data Model are conditional design baselines; they do not close their listed dependencies.

SEC-01 approves secure email/password authentication, server-side sessions, secure password hashes, `Secure` and `HttpOnly` session cookies, CSRF protection, expiry and logout invalidation, protected first-Admin provisioning, no public self-registration or SSO, and Admin-managed creation/deactivation. SEC-02 approves the two-role, single-retailer, backend-enforced authorization boundary. SEC-03 approves an Admin-managed sandbox directory, no arbitrary or supplier recipients, and no real sending in the MVP. SEC-04 approves keeping source feedback in governed records and authorized evidence views while redacting it from logs and telemetry.

The approved password, session, cookie, CSRF/CORS, initial Admin, account lifecycle/recovery, login-throttling, audit-event, and CSV parser choices are detailed in §§3-7, 9, and 12-13 below. This conditional design baseline does not authorize application code, migrations, real email, activation of detection/notifications, or deployment. Remaining dependencies are listed in §16.

## 2. Security boundary and data classification

ProductPulse is a single-retailer MVP with one FastAPI backend, one SQLite database shared with one worker, and a React browser client. The backend is authoritative for identity, authorization, validation, ingestion, classification, detection, and notification decisions. The browser is not trusted to enforce access or business rules.

The capstone data boundary is synthetic or permitted public, non-sensitive data. Do not use real customer, client, C5i, personal, or health data. Any expansion to real or sensitive data requires a separate privacy and provider-data decision before transmission or use.

Protect these data classes according to their purpose:

| Data | Handling |
|---|---|
| Passwords, session bearer tokens, API keys, mail credentials | Never log, audit, include in response bodies, expose through browser JavaScript, or commit. Deliver the session bearer only through the configured `HttpOnly` cookie; persist passwords and session bearer tokens only as approved one-way hashes. Keep provider secrets in protected server-side configuration. |
| CSRF and manual-preview tokens | Never log or include in audit snapshots. Return only through the explicit API flow that needs the value over TLS; the UI may retain the session-bound CSRF value as specified. ProductPulse issues no recovery token or reset link; recovery uses the approved Admin-assisted temporary-password handoff. Preview-token persistence, expiry, and replay remain open under ALERT_SPEC.md. |
| Original review/return text and preview rows | Keep only in governed source/preview stores needed for ingestion, traceability, and authorized investigation. Treat all text as untrusted. Exclude raw text from operational logs, traces, generic audit snapshots, and safe errors. |
| Manual notification content and recipients | Use only in the approved sandbox workflow. Preserve the exact confirmed message and recipient snapshot in the protected notification record as required by the PRD. Exclude addresses and arbitrary message content from generic audit snapshots and logs. |
| Upload and rejection-report bytes | Store in the approved protected local artifact directory, outside public/static delivery and Git. Resolve opaque IDs only on the backend. Include referenced artifacts with SQLite in one recovery set. |
| Operational identifiers and diagnostics | Prefer opaque resource/job/request IDs, stable safe error codes, counts, and timestamps. Do not include raw exception text, provider payloads, filesystem paths, or secrets. |

## 3. Authentication and password storage

### 3.1 Authentication requirements

- Authenticate existing users by email and password through the backend. Only `ADMIN` and `BUSINESS_USER` accounts exist in the MVP.
- Use a generic login failure response that does not reveal whether an email is registered, inactive, or has an incorrect password. Do not return raw authentication or provider details.
- Do not expose public registration or SSO. The first Admin is provisioned by a protected setup command; later users are provisioned by an Admin through the authenticated API.
- Only active accounts may establish a session. Authentication and authorization decisions are made on the server for every protected request.
- Do not store an authentication token in browser local storage, session storage, URLs, or application logs. The UI may retain only the public user representation and the CSRF value returned by the API.

### 3.2 Password hashing

- Store only a salted adaptive password hash in users.password_hash. Use the maintained Python argon2-cffi Argon2id implementation with 19 MiB memory, 2 iterations, and parallelism 1. Benchmark authentication latency in the implementation environment and increase the cost when practical; do not lower these values silently.
- Keep self-describing scheme/parameter metadata in the encoded hash. On successful login, rehash when the stored scheme or parameters are below the approved settings. Use the library's constant-time verification function.
- Normalize passwords to Unicode NFC before validation, hashing, and verification. Require 15-128 Unicode code points; allow Unicode and spaces. Reject overlength input without truncation. Reject passwords on a maintained local common/compromised-password blocklist. Do not impose composition rules or periodic expiry.
- Apply this policy to the first Admin, Admin-created temporary passwords, and Admin resets. The first Admin chooses the password at secure setup. Admin-created users and reset users receive temporary passwords and must change them before normal use.
- Initial and temporary passwords are write-only over TLS, cleared from UI state after submission, hashed server-side, never returned or logged. Never store a clear-text or reversible password or include password values/hashes in audit snapshots.
## 4. Server-side sessions, cookies, CSRF, and CORS

### 4.1 Server-side sessions

- Generate an opaque cryptographically random session bearer and validate it against a server-side record. Persist only a one-way hash in sessions.token_hash.
- A session has a 30-minute idle limit and an 8-hour absolute limit from creation. Update last_seen_at from authenticated activity and reject a session when idle time or absolute expiry is reached. Cookie expiry must not exceed the earlier remaining limit.
- Concurrent sessions are allowed. Rotate the session bearer and session-bound CSRF token on successful login and after password reset/change. Logout revokes the current server session; account deactivation and password reset/change revoke all sessions for the account. A successful password change then establishes one fresh session and CSRF value for the user.
- Load current account status and role on each protected request. Reject missing, expired, revoked, inactive-account, or must_change_password sessions as appropriate. A user whose must_change_password is true may only read the current session, log out, or complete password change; block all other application routes server-side.
- Deactivation and its active-session revocations are atomic. A revoked/expired session returns the user to login; never automatically replay a prior mutation.

### 4.2 Cookie requirements

- Name the host-only session cookie __Host-productpulse_session. Set Secure, HttpOnly, SameSite=Lax, Path=/, and no Domain. The __Host- prefix requires Secure, Path=/, and no Domain.
- Refresh cookie expiry from the server only as permitted by the current idle limit, and never later than absolute expiry. Clear it on logout with matching scope and attributes.
- Serve the deployed application/API over TLS. Do not use an insecure cookie configuration for the non-production deployment.

### 4.3 CSRF protection

- At browser bootstrap, unauthenticated GET /auth/csrf creates a cryptographically random pre-login CSRF value, sets a host-only __Host-productpulse_prelogin_csrf cookie with Secure, HttpOnly, SameSite=Strict, Path=/, no Domain, and Max-Age=600, and returns the matching value in JSON. The UI keeps that value in memory only.
- POST /auth/login requires X-CSRF-Token to match both the returned pre-login value and the HttpOnly cookie. It also requires an exact same-origin Origin; use Referer only when Origin is absent, and reject when neither provides a valid same-origin value. Clear the pre-login cookie after successful login.
- Bind a fresh session CSRF value to the authenticated session and return it from login/session responses. Require the matching X-CSRF-Token on every cookie-authenticated state-changing request, including logout. Rotate it with the session at login and after reset/change. A missing or invalid value blocks the action and all side effects.
- Do not rely on SameSite alone. A read-only GET never changes state. Manual notification preview tokens remain separate and are governed by §16.

### 4.4 CORS

Production browser deployment is same-origin. Do not enable cross-origin credentialed browser requests or permissive CORS headers. Cross-origin browser access requires a separate deployment/product decision; wildcard origins, arbitrary-origin reflection, and credentialed wildcard CORS are forbidden.
## 5. Roles and authorization

Authorization is enforced on the backend for every protected operation and relevant resource. UI navigation and hidden controls are usability only. The application has one retailer and no tenant, product, or supplier scopes. Do not add a Viewer role or granular permission system in the MVP.

| Capability | Admin | Business User |
|---|---:|---:|
| Sign in/out; view dashboard, products, feedback, incidents, evidence, and permitted notification history | Yes | Yes |
| Add investigation notes; acknowledge, investigate, resolve, or reopen incidents as allowed by the API | Yes | Yes |
| Compose and explicitly confirm a manual notification to active approved directory recipients | Yes, only when the notification prerequisites are approved and enabled | Yes, only when the notification prerequisites are approved and enabled |
| Upload, preview, map, confirm, inspect ingestion jobs/row errors, reconcile, or retry ingestion/processing | Yes | No |
| Manage users, taxonomy, detection rules, recipient directory/groups, routing configuration, and detailed operations | Yes | No |
| Retry an eligible known-failed notification | Yes | No |
| Configure or read OpenAI/mail credentials | No application UI or Business User capability; deployment administrator only | No |

For a denied Business User ingestion request, reject before storing file bytes, creating a preview, or creating an ingestion job. Apply the same backend rule to direct API calls and object IDs. Do not rely on role fields supplied by the client. Resource-not-found and out-of-scope behavior must follow the API's safe error contract without disclosing protected data.

## 6. Initial Admin and user account lifecycle

- Provision the first Admin only with a protected one-time setup command. It fails closed if any Admin already exists. Read the password through a secure hidden prompt; never accept it via argv, environment variables, shell history, command output, or logs. There is no public bootstrap endpoint.
- Admins may create only ADMIN and BUSINESS_USER accounts. No public self-registration, SSO, Viewer role, deletion, or reactivation exists. Admin-created accounts receive a compliant temporary password and must change it before normal use.
- Normalize email for identity by trimming outer ASCII whitespace, applying Unicode NFC, converting the domain to lowercase IDNA ASCII, then case-folding the full resulting address for email_normalized. Preserve the trimmed entered address and its casing for display. Do not rewrite plus/dot aliases or apply provider-specific alias rules. Login uses the same canonicalization; a normalized duplicate is rejected.
- Return only the public user representation. Never return password hashes, passwords, reset values, session tokens, or CSRF secrets.
- Deactivate rather than delete accounts. Deactivation and revocation of all active sessions occur together. Accounts cannot be reactivated under this contract.
## 7. Password reset, account recovery, and session expiry

Recovery is Admin-assisted only. An authorized Admin sets a compliant temporary password through the Admin API; the target account is marked must_change_password, and all existing sessions are revoked. The Admin hands the temporary credential directly to the verified user in person outside ProductPulse. ProductPulse does not email reset credentials or provide a public self-service reset flow.

After login with a temporary credential, restrict the account to session inspection, logout, and password change. The password-change operation validates the current temporary password and new password policy, stores a new Argon2id hash, clears must_change_password, revokes all prior sessions, and establishes a fresh session with rotated session/CSRF values. Audit reset/change events without storing the credential. This boundary avoids a recovery token and an unapproved email channel, at the cost of requiring Admin availability and verified in-person handoff.
## 8. OpenAI and other secrets

- OpenAI and mail-provider calls execute only on the backend through provider adapters. The browser never receives provider credentials, provider request payloads, or a direct provider capability.
- Supply API keys through protected server-side configuration, such as an environment variable or secrets manager. Never put credentials in source control, frontend bundles, prompts, job summaries, logs, audit snapshots, API errors, or user-visible responses.
- Credential management is reserved for the backend deployment administrator; it is not an application role capability. Do not return secrets through readiness or Admin operations endpoints.
- Keep provider request IDs and non-secret usage/latency/cost measurements only as required for traceability. Redact provider payloads and raw exception text.
- The specific deployment secret store, local development method, access permissions, rotation/revocation process, and provider are not selected. Resolve these for the chosen non-production host before deployment. Do not add a numeric model-cost gate; none is approved.

## 9. CSV upload, validation, and artifact/path security

### 9.1 Authorization and validation

- Only Admins may upload, preview, map, confirm, inspect reports/jobs, or retry ingestion. Enforce authorization before persisting bytes or creating upload/preview/job state.
- Enforce an inclusive file-part ceiling of 20,000,000 bytes while streaming, before parsing/publication. Permit no more than 50,000 logical CSV data records after the header; blank records count. Return 413 when the file part exceeds its byte ceiling and 422 when the logical data-row cap is exceeded.
- Accept strict UTF-8 only. Strip one UTF-8 BOM only at byte offset zero. Reject malformed UTF-8, alternate encodings, malformed CSV/file structure, and unsupported upload kinds. Use the RFC-4180-style parser contract and the version identifiers reviews-v1, returns-v1, product-reference-v1, supplier-reference-v1, and batch-reference-v1. Increment the relevant identifier when parser, validation, or normalization semantics change.
- Accept timestamps only as RFC 3339/ISO-8601 with Z or an explicit offset and at most three fractional-second digits. Normalize to UTC at fixed millisecond precision. Reject offset-free timestamps and excess fractional precision; do not guess or round.
- Enforce decoded value limits without truncation: feedback text 16,384 Unicode code points; identifiers 256 code points; all other mapped text 1,024 code points; and every decoded field at most 65,536 UTF-8 bytes. Reject empty, whitespace-only, or leading/trailing-whitespace identifiers. Preserve all other accepted source identifier/text code points without trim, case-fold, or Unicode normalization. Compare identifiers exactly and case-sensitively.
- Admin mapping remains by source-column index and exact header; every required target maps exactly once, no canonical target is duplicated, and only optional source columns may map to IGNORE. The server validates the mapping against the staged bytes.
- Bind every preview immutably to exact staged-byte SHA-256, parser-contract version, canonical mapping snapshot, and row outcomes/counts. A repeated Idempotency-Key with the same canonical request returns its original preview; a changed request under the same key returns 409; a new key creates a new preview. Confirmation re-reads and rehashes the staged bytes. Any file or mapping change needs a new preview.
- Identical stored or first-valid-in-file source identity/payload is a no-op. Within one file, the first valid row is the candidate; subsequent same-payload rows are duplicate no-ops and differing rows are conflicts. A differing stored source payload creates an Admin-visible conflict and never overwrites source text or event time.
- For reference conflicts, KEEP_EXISTING marks reviewed with no data change; DISMISS records dismissal with no data change; APPLY_INCOMING_REFERENCE applies only validated incoming fields if the expected existing-value hash still matches. Apply atomically and audit before/after values with source-row provenance; return 409 on stale expected state. Source-payload conflicts cannot apply incoming source text.
- A preview is READY only when it has at least one eligible new row; it may also contain rejected/conflicting rows. It is INVALID when none are eligible. Malformed file-level input creates no preview and returns 422. Generate a rejection report only when rejected/conflicting rows exist; include rejected/conflicting rows, not DUPLICATE_NOOP rows, while retaining all outcome counts in the preview. Reports are UTF-8 CSV, formula-safe, and contain row number, outcome, parsed source type/identity when available, stable reason code, and safe explanation; exclude raw feedback.
- Preserve DAI-01 mapping precedence, DAI-02 no-overwrite, DAI-08 Admin mapping, PRD partial acceptance, and the approved protected-artifact requirements. Artifact expiry/retention remains open under OPS-03.
### 9.2 Storage and path security

- Store uploaded CSV and generated rejection-report bytes in a protected persistent local directory accessible to the API and one worker. Keep it outside public/static delivery and Git. SQLite stores opaque artifact IDs and metadata, not file bytes.
- Generate artifact IDs server-side. Treat original filenames as sanitized display metadata only. Never accept a client path or use a client filename to construct a storage path. Resolve an ID only through a server-controlled mapping beneath the configured root; fail closed if an artifact is missing, outside the root, or its stored hash does not match.
- Preserve the file hash, size, actor where available, timestamps, immutable preview/hash binding, and audit lineage. Publish artifacts atomically before committing the SQLite reference; remove a newly published file if the database commit fails. Reconcile unreferenced orphan files without deleting referenced artifacts.
- Serve downloads only through authorized backend routes; never expose local paths or a public artifact URL. Use least-privilege filesystem permissions. Back up and restore the SQLite database and its referenced artifacts together as one consistent recovery set.
- Artifact/preview/report expiry and deletion ordering are unresolved. Keep them available for the approved preview, confirmation, and rejection-report workflow until retention/expiry is defined. Do not add an automatic purge rule in this document.

## 10. Prompt-injection and model-output protection

Customer review and return text, CSV headers, row values, and user-authored fields are untrusted input. Follow the approved AI specification:

- Pass feedback as a JSON-encoded data field separated from system instructions. Never concatenate feedback into developer/system instructions.
- Tell the model to classify the text, not follow embedded instructions, reveal secrets, override taxonomy, or call tools. Provide no tools, code execution, network, database, or email capability.
- Send only the minimum approved classification fields. Do not send credentials, unrelated source text, or inferred product/supplier/batch/customer facts.
- Treat structured output as untrusted. Validate schema, allowed taxonomy values, source identity correspondence, and evidence grounding on the backend. Do not let model output authorize a request, set final severity, compute defect totals, change routing, or send a message.
- Log neither raw feedback nor full prompts. Include the approved adversarial prompt-injection cases in security evaluation and expect the content to remain data or yield explicit uncertainty, with no instruction execution.
- Do not transmit real or sensitive customer data under the current MVP boundary. A future data-scope change requires a separate privacy/provider-data decision first.

## 11. Manual email recipient authorization and confirmation

SEC-03 approves an Admin-managed sandbox directory only: no arbitrary address entry, supplier recipients, or real sending in the MVP. The final directory/fallback, routing behavior, and concrete sandbox/local capture sink remain open and require the approvals recorded in the Decision Register and Alert Specification. Detection and automatic notifications remain gated by their own unresolved coverage/calibration prerequisites.

When an approved manual notification flow is enabled:

1. The user starts from one incident and selects active recipient IDs returned from the server's approved directory. No free-form email field is accepted.
2. The server checks the actor's active session/role, incident, recipient status/authorization, content limits, and CSRF token. It returns the complete exact preview; previewing, refreshing, abandoning, or closing it sends nothing and creates no outbox event.
3. Confirmation requires the displayed preview token/hash and a stable `Idempotency-Key`. The server revalidates the actor/session, incident, current recipient permission, exact content hash, and preview binding before storing one confirmed event.
4. Persist the exact confirmed content and recipient snapshot with the actor and audit lineage. A changed message or recipient selection requires a fresh preview. A repeated identical confirmation must not create a second event.
5. A queued notification is not provider-accepted or delivered. Report only persisted states; do not claim delivery without provider evidence. Provider calls occur in the worker after durable outbox commit.

The Alert Specification v0.2 is still Draft. Its preview token actor/session/incident/content/recipient binding is the current design direction; exact token storage, expiry, replay, and repeat-preview behavior remain an implementation dependency. Provider verification, external idempotency, route precedence, fallback, and final recipient/sink configuration are also open. Do not enable real email without separate explicit approval and an updated security review.

## 12. Audit logging, privacy, and sensitive data

- Keep append-only audit history for successful sign-in, logout/session revocation, account creation/deactivation/password reset/password change, authorization denials, configuration, ingestion, reconciliation, and other administrative actions not already represented by incident history or delivery attempts. Record actor when known, action, resource class/opaque resource ID where safe, outcome, request/correlation ID, and UTC timestamp.
- Log failed sign-in and login-throttle detail only in a restricted redacted security log, separate from generic application diagnostics. Neither log may include submitted email, source IP, password, session ID/token, CSRF/recovery token, raw request body, provider secret, or raw exception. Failed login audit events do not identify the attempted email/account.
- Generic audit snapshots remain allow-listed and omit raw feedback, names/emails, password values/hashes, session identifiers/tokens, CSRF values, API keys, arbitrary message content, provider payloads, filesystem paths, and raw exceptions.
- Preserve incident actions in append-only incident history. Preserve confirmed notification content only in its protected notification record. Logs and traces use stable safe error codes, opaque IDs, and counts; redact sensitive fields before telemetry.
- The capstone expectation retains synthetic operational/audit history through the capstone period; this is not a production retention policy. Artifact expiry, backup cadence/retention, and deletion effects remain open under OPS-03.
## 13. API validation, rate limiting, and error handling

- Validate every request server-side: authentication state, role, current resource state, request shape, allowed values, length bounds, pagination/filter bounds, and idempotency behavior. Frontend checks are advisory.
- Apply login throttling only to login: 10 failed attempts for a normalized candidate account in a rolling 15-minute window triggers a 15-minute cooldown; cap all login attempts per source IP at 60 in a rolling 15-minute window. Return generic credential failures, and generic 429 responses with Retry-After. Do not reveal whether an account exists or is inactive. These values do not set limits for upload, mutation, provider, or other routes.
- Other abuse/cost-sensitive route limits, retry budgets, and backoff remain assigned to OPS-02 and AI_SPEC. Do not invent defaults for them. The API problem contract uses 429 and Retry-After without retry loops.
- Use parameterized SQL. Do not interpolate request values into SQL, shell commands, filesystem paths, logs, prompts, or HTML. Escape untrusted text in UI rendering and formula-escape user-controlled CSV export/report cells.
- Enforce role and state-sensitive authorization on every protected endpoint and recheck it at mutation time. For forced-password-change sessions, permit only session inspection, logout, and password change.
- Follow the API problem contract: 401 for missing/expired/invalid authentication; 403 for denied role/action; 404 when needed to avoid disclosure; 409 for stale state/hash/idempotency conflicts; 413 for file-size excess; 415 for unsupported input; 422 for invalid requests/row cap; 429 for rate limiting; and generic redacted 5xx/503 responses for internal/provider failures. Errors never disclose account existence, secrets, local paths, raw SQL/provider errors, feedback, or stack traces.
- Production browser/API deployment is same-origin; cross-origin browser requests are not enabled. The API returns stable safe codes and a request ID where available.
## 14. Security testing and acceptance criteria

These are specification-level acceptance criteria for future implementation verification. They do not select a test framework or authorize application code/tests in this change.

| ID | Acceptance criterion |
|---|---|
| SEC-AC01 | Passwords use Argon2id with the approved parameters, NFC policy, 15-128 code-point bounds, and blocklist; no password/hash is exposed. Rehash on successful login when required. |
| SEC-AC02 | Active accounts receive server-side sessions with 30-minute idle and 8-hour absolute expiry; cookie attributes and reset/change/deactivation revocation match §4. |
| SEC-AC03 | GET /auth/csrf, pre-login cookie/header/origin validation, session CSRF rotation, same-origin CORS, and forced-change route restriction match the approved contract; invalid CSRF has no side effects. |
| SEC-AC04 | Direct requests by a Business User to each Admin-only route return `403`; an upload denial stores no bytes and creates no upload preview or job. Admin-only user/configuration/processing permissions are enforced even when UI controls are bypassed. |
| SEC-AC05 | Public signup/SSO are unavailable; one-time Admin setup is protected; account normalization, temporary-password change, direct handoff, deactivation, and session revocation match the approved contract. |
| SEC-AC06 | OpenAI and mail credentials are absent from browser bundles, repository content, prompts, logs, generic audit snapshots, responses, and errors. |
| SEC-AC07 | Upload checks enforce 20,000,000 bytes, 50,000 logical rows, UTF-8/BOM, parser versions, timestamp/field/ID rules, mapping/hash integrity, duplicates/conflicts, and safe report behavior. |
| SEC-AC08 | Adversarial feedback that requests secrets, instruction override, taxonomy override, output-shape override, or tool use is treated only as classification data or uncertainty. No tool or side effect is executed; output validation remains server-side. |
| SEC-AC09 | A manual email preview creates no outbox row/send. Confirmation rejects unauthorized or inactive recipients, changed preview content, invalid CSRF, or mismatched idempotency use. A replay of the same confirmation does not duplicate the event. No supplier or unapproved real address is contacted. |
| SEC-AC10 | Audit/log review finds no raw feedback, passwords/hashes, email, source IP, session/CSRF/reset tokens, provider secrets/payloads, arbitrary message content, filesystem paths, or raw exceptions. Required auth/security events are present in their approved channels. |
| SEC-AC11 | Invalid requests return safe stable problem responses; login throttling uses the approved account/IP windows and generic 429 with Retry-After. Other route limits remain governed separately. |
| SEC-AC12 | The non-production deployment uses TLS, protected server-side secrets, least-privilege SQLite/artifact storage, one active API/worker instance with shared persistent local storage, synthetic/permitted non-sensitive data, health checks, backup/restore verification, and a demonstrated rollback. |
| SEC-AC13 | SQL-injection test inputs supplied through query parameters, request bodies, filters, and uploaded-file fields do not alter query structure, bypass authorization, or expose or modify data outside the caller's permissions. Database access uses parameterized queries; responses and logs do not disclose raw SQL or database errors. |
| SEC-AC14 | Stored and reflected user-controlled content, including feedback, CSV headers and values, and rejection-report content, is rendered as inert text. Test markup and script payloads do not execute in the browser or create active HTML in any UI surface. |
| SEC-AC15 | CSV export tests include formula-leading values in feedback, headers, and other user-controlled fields. Exported values are safely escaped so spreadsheet software does not evaluate them as formulas, while source data remains unchanged. |
| SEC-AC16 | Production browser/API deployment is same-origin and does not allow cross-origin credentials. Any future cross-origin arrangement is separately approved and exact-origin constrained. |

Security acceptance checks must use the approved values and retain exact-revision local checklist evidence; selected pytest/FastAPI TestClient, Vitest/React Testing Library, PowerShell, and security-check tooling is recorded in TECH_STACK.md.

## 15. Non-production deployment security

- Use only a non-production environment. The PRD requires TLS, protected secrets, health checks, operational visibility, a runbook, and rollback evidence. No production deployment or multi-tenant guarantee is claimed.
- The approved deployment constraint is one active application instance, one API and one worker, and persistent local storage for SQLite plus protected artifacts accessible to both. Do not assume a network filesystem, multi-instance writes, or another database/broker.
- Apply least-privilege filesystem and process access to database, WAL/sidecar files, and artifact storage. Keep artifact storage outside public/static serving and Git. Restrict administrative deployment access and secret access to the backend deployment administrator.
- Keep provider calls in backend processes. Do not configure production mail, supplier mail, public signup, or sensitive production data in this environment.
- Backups must capture SQLite and all referenced artifacts as one consistent recovery set. Quiesce API/worker writes or use an SQLite-consistent mechanism; verify database integrity, foreign keys, artifact resolution, and hashes before restart. Cadence, retention, and exact backup mechanism remain open.
- The preferred single Linux VM/Docker Compose topology is Proposed, not approved. No cloud provider or frontend static-host arrangement is selected. Verify provider support for local persistent storage, secrets, TLS, health, logs, backups, and rollback before deployment approval.

## 16. Unresolved decisions and implementation dependencies

The following implementation decisions remain open. They do not reopen the approved SEC-01/02 or DAI-01/02/08 contracts.

| Decision / reference | Still needed | Blocks or constrains |
|---|---|---|
| Other-route rate limits — OPS-02 / AI_SPEC | Numeric policies for upload, sensitive mutations, provider/cost-sensitive routes, and other abuse-sensitive surfaces. Login limits are fixed in §13. | Dependent endpoint implementation and 429 behavior; do not infer the login values apply elsewhere. |
| Artifact lifecycle — OPS-03/OPS-06 | Preview, upload, and rejection-report expiry/retention, cleanup ordering, deletion audit effects, and backup cadence/retention/mechanism. | Artifact cleanup and operational recovery. |
| Manual preview token — API, UI §4.7, ALERT_SPEC §5 | Storage, entropy/verification, expiry, replay, repeat-preview behavior, and actor/session binding. | Manual notification preview and confirmation. |
| Recipient directory and email sink — SEC-03, ARC-05 | Final sandbox directory/fallback, routing semantics, concrete capture sink/provider, provider verification, and external idempotency behavior. | Manual/automatic notification configuration and delivery. No real email. |
| Deployment host and secrets — OPS-01 | Provider selection and proof of single-instance persistent-local-storage fit; secret store, TLS, file permissions, health, backup, and rollback setup. | Non-production deployment approval. |
| Retention and data scope — PRD §13, OPS-03, AI_SPEC §14 | Artifact/audit operational retention details; any future non-synthetic data requires separate privacy/provider-control approval. | Retention automation or data-scope expansion. |

### Cross-document gaps and preserved gates

1. GET /auth/csrf now provides the pre-login token and cookie; login validates the token and same-origin Origin/Referer contract. API_SPEC.yaml and UI_SPEC.md must use that flow.
2. Production is same-origin by design. A future cross-origin deployment requires a separate review and an exact origin policy before configuration.
3. Manual notification preview token storage/lifecycle, final recipient/routing/sink decisions, and any real email remain unapproved.
4. Detection stays disabled until PB-01 thresholds, DAI-06 coverage parameters, and required evaluation/classification-authority gates are approved. This security update does not activate detection or notifications.
5. Numeric rate limits outside login, and OPS-03 artifact retention/backup parameters, remain open. Do not substitute approved login values for those policies.
## 17. Source consistency and change control

This document is subordinate to the PRD for product behavior and to the Decision Register for approval status. Where a detail in this document conflicts with an approved decision, stop and reconcile the specifications; do not infer that this security baseline supersedes them. In particular:

- Preserve the PRD's Admin/Business User permissions, Admin-only ingestion, protected first-Admin setup, secure password hash, backend sessions, secure cookies, CSRF protection, and no public registration/SSO.
- Preserve SEC-01 through SEC-04 only at their approved scope. An unresolved detail in the open-decision table remains unresolved until separately approved.
- Preserve the API/Data Model/UI conditional design-baseline status and all documented prerequisites. Do not promote an API proposal or Alert/Detection draft into approved behavior by reference here.
- Keep OpenAI calls backend-only, deterministic defect/alert logic on the backend, customer feedback untrusted, and secrets out of frontend/logs/API responses.
- Keep real email and sensitive customer data outside the MVP boundary. No notification, deployment, or detection feature is activated by this security specification.

Changes to an approved security decision require an explicit decision-register update and aligned revisions to affected API, data, architecture, UI, AI, alert, and operations specifications before dependent implementation.
