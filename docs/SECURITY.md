# ProductPulse Security Specification

**Version:** 1.0  
**Status:** Approved — Design Baseline  
**Approval date:** 21 November 2026  
**Requirements source:** [PRD](PRD.md) v1.7  
**Decision basis:** [Decision Register](DECISION_REGISTER.md) v1.7  
**Related specifications:** [Architecture](ARCHITECTURE.md) v1.4 (Approved); [Data Model](DATA_MODEL.md) v1.4 (Approved — Design Baseline, conditional); [API](API_SPEC.yaml) v1.4.0 (Approved — Design Baseline, conditional); [UI](UI_SPEC.md) v0.3 (Approved — Design Baseline, conditional); [Tech Stack](TECH_STACK.md) v1.0; [AI](AI_SPEC.md) v1.0 (Approved — Design Baseline); [Alert](ALERT_SPEC.md) v0.2 (Draft); [Detection](DETECTION_SPEC.md) v1.1 (Draft clarification; v1.0 remains the Approved — Design Baseline).

## 1. Purpose and approval boundary

This document defines the security boundary and records the details that must be decided before dependent implementation. The PRD remains the source of product requirements. The Decision Register supplies approved security decisions and their limits. The API and Data Model are conditional design baselines; they do not close their listed dependencies.

SEC-01 approves secure email/password authentication, server-side sessions, secure password hashes, `Secure` and `HttpOnly` session cookies, CSRF protection, expiry and logout invalidation, protected first-Admin provisioning, no public self-registration or SSO, and Admin-managed creation/deactivation. SEC-02 approves the two-role, single-retailer, backend-enforced authorization boundary. SEC-03 approves an Admin-managed sandbox directory, no arbitrary or supplier recipients, and no real sending in the MVP. SEC-04 approves keeping source feedback in governed records and authorized evidence views while redacting it from logs and telemetry.

This conditional design baseline does not select unapproved values, providers, libraries, or recovery flows. In particular, it does not settle the password policy, hashing algorithm and cost parameters, cookie lifetime, CSRF bootstrap, CORS origins, numeric rate limits, account recovery, preview-token lifetime, artifact retention, or deployment provider. Dependent implementation must wait for the decisions listed in §16. This approval does not authorize application code, migrations, real email, activation of detection/notifications, or deployment.

## 2. Security boundary and data classification

ProductPulse is a single-retailer MVP with one FastAPI backend, one SQLite database shared with one worker, and a React browser client. The backend is authoritative for identity, authorization, validation, ingestion, classification, detection, and notification decisions. The browser is not trusted to enforce access or business rules.

The capstone data boundary is synthetic or permitted public, non-sensitive data. Do not use real customer, client, C5i, personal, or health data. Any expansion to real or sensitive data requires a separate privacy and provider-data decision before transmission or use.

Protect these data classes according to their purpose:

| Data | Handling |
|---|---|
| Passwords, session bearer tokens, API keys, mail credentials | Never log, audit, include in response bodies, expose through browser JavaScript, or commit. Deliver the session bearer only through the configured `HttpOnly` cookie; persist passwords and session bearer tokens only as approved one-way hashes. Keep provider secrets in protected server-side configuration. |
| CSRF, recovery, and manual-preview tokens | Never log or include in audit snapshots. Return only through the explicit API flow that needs the value over TLS; the UI may retain the session-bound CSRF value as specified. Hash/persistence, expiry, and replay rules for recovery and preview tokens remain subject to their open decisions. |
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

- Store only a one-way, salted, adaptive password hash in `users.password_hash`. Never store or log a clear-text password, reversible password value, or password in an audit snapshot.
- Use a maintained password-hashing implementation; do not implement a custom hash scheme. The algorithm, parameters, dependency, and any rehash-on-login policy must be selected and recorded before authentication implementation.
- Compare submitted credentials using the selected library's safe verification function. Keep hash metadata sufficient to identify the scheme and parameters for later upgrades.
- Apply the same password handling to initial Admin provisioning and Admin-created users. `initial_password` is write-only, sent only over TLS, cleared from UI state after submission, hashed server-side, and never returned.
- Do not infer a minimum length, maximum length, composition rule, breached-password check, password age, or first-login change requirement. These are open policy choices in §16.

## 4. Server-side sessions, cookies, CSRF, and CORS

### 4.1 Server-side sessions

- Generate an opaque, unpredictable session bearer token and validate it against a server-side session record. Persist only a one-way hash of the token in `sessions.token_hash`; never persist the browser bearer token.
- The session record is linked to one user and includes creation, expiry, optional last-seen, and revocation timestamps. Reject missing, expired, revoked, or inactive-user sessions.
- Logout revokes the server-side session and expires its cookie. Deactivation revokes that user's active sessions together with the deactivation operation. An expired/revoked session returns the user to login; the client must not automatically replay a prior mutation after re-authentication.
- Do not treat the session cookie as proof of role or permission. Load the current account status and role at the backend authorization boundary.
- Session duration, idle versus absolute expiry, renewal, token rotation, concurrent-session policy, cleanup cadence, and session revocation on password recovery/change require decisions before implementation. No numeric duration is approved here.

### 4.2 Cookie requirements

- Session cookies must be `Secure` and `HttpOnly`, as required by SEC-01. The API baseline names the cookie `productpulse_session`; this name is subject to the API/security review noted in that contract.
- Select and document `SameSite`, `Path`, `Domain`, lifetime/expiry attributes, and any deployment-specific cookie scope before implementation. Do not broaden cookie scope to unrelated hosts.
- Serve the deployed application and API over TLS. Do not use an insecure cookie configuration as a local or deployment shortcut without an explicitly scoped development configuration that cannot be used in the non-production deployment.

### 4.3 CSRF protection

- Require the session-bound CSRF value on every state-changing cookie-authenticated request, including logout, user/configuration changes, upload preview/confirmation, incident actions, and notification preview/confirmation. A read-only `GET` must not perform a state change.
- The API baseline names `X-CSRF-Token` and returns a session-bound value from login/session endpoints. Treat the header name as an API contract candidate pending its stated security review. A missing or invalid token must prevent the action and its side effects.
- Do not rely on `SameSite` alone as CSRF protection. Define token creation, storage, rotation, comparison, login/bootstrap handling, and any Origin/Referer or Fetch Metadata checks before implementation.
- Manual notification preview tokens are separate from CSRF tokens. Preview-token binding, expiry, replay handling, and storage are governed by the open dependency in §11 and §16.

**Contract gap:** `POST /auth/login` references `X-CSRF-Token`, while login is unauthenticated and the API does not define how a browser obtains a pre-authentication token. Resolve the bootstrap design and align the API contract before implementing login.

### 4.4 CORS

The API contract describes a same-origin API, while the frontend's static delivery host is unselected. Keep the deployed arrangement same-origin where possible. Do not add permissive cross-origin access as a convenience default.

If a deployment requires cross-origin browser requests, define the exact trusted origin allowlist after the frontend host is selected. Credentialed requests may be allowed only for explicitly listed origins; do not use `Access-Control-Allow-Origin: *` with credentials, reflect arbitrary request origins, or expose broad methods/headers. Document the required methods and headers, including the session cookie and CSRF header, and reject unlisted origins. The origin list and whether cross-origin access is needed remain open decisions.

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

- Provision the first Admin only through a protected setup command. There is no public bootstrap endpoint. Restrict command execution to the deployment operator's authorized server-side context and keep any supplied credential out of process listings, shell history, logs, and command output. The precise one-time guard and secure input method must be decided before implementation.
- Admins create `ADMIN` or `BUSINESS_USER` accounts through the authenticated API. Validate the role against those two values. No public self-registration, Viewer, delete, or reactivation operation is in scope.
- Return only the public user representation. Never return password hashes, passwords, reset tokens, session tokens, or CSRF secrets in user records.
- Deactivate rather than delete accounts. Deactivation and revocation of active sessions occur together. Preserve account and audit history under the approved capstone retention expectation.
- The API/UI baselines accept a write-only initial password. They do not define how an Admin securely delivers it, whether a first-login password change is required, or how an account is recovered. Decide the onboarding procedure before provisioning is implemented.
- Email canonicalization and case-insensitive uniqueness are open. Do not silently normalize account identifiers until the rule is selected and aligned with the `email_normalized` unique-index target in the Data Model.

## 7. Password reset, account recovery, and session expiry

The current UI/API baseline defines no reset or account-recovery flow. Do not add a reset endpoint or UI control until a recovery approach is approved. Before implementation, decide whether recovery is Admin-assisted, user-initiated, or out of scope for the MVP; identify a permitted delivery/verification channel; and specify token secrecy, storage, expiry, single use, replay resistance, account-enumeration behavior, rate limiting, audit events, and effects on existing sessions. Real email recovery cannot be assumed because real sending is not approved for the MVP.

Session expiry and logout invalidation are approved requirements; exact absolute/idle lifetimes, renewal behavior, revocation timing, and cleanup are not. After a recovery or password change, the session-revocation policy must be explicit. Until those details are decided, recovery and dependent session behavior are not implementation-ready.

## 8. OpenAI and other secrets

- OpenAI and mail-provider calls execute only on the backend through provider adapters. The browser never receives provider credentials, provider request payloads, or a direct provider capability.
- Supply API keys through protected server-side configuration, such as an environment variable or secrets manager. Never put credentials in source control, frontend bundles, prompts, job summaries, logs, audit snapshots, API errors, or user-visible responses.
- Credential management is reserved for the backend deployment administrator; it is not an application role capability. Do not return secrets through readiness or Admin operations endpoints.
- Keep provider request IDs and non-secret usage/latency/cost measurements only as required for traceability. Redact provider payloads and raw exception text.
- The specific deployment secret store, local development method, access permissions, rotation/revocation process, and provider are not selected. Resolve these for the chosen non-production host before deployment. Do not add a numeric model-cost gate; none is approved.

## 9. CSV upload, validation, and artifact/path security

### 9.1 Authorization and validation

- Only Admins may upload, preview, map, confirm, inspect reports/jobs, or retry ingestion. Enforce this before persisting bytes or creating upload/preview/job state.
- Apply the PRD's maximum of 20 MB and 50,000 rows. The exact byte interpretation of 20 MB is open; do not guess between decimal MB and MiB. Enforce the selected byte ceiling while receiving the upload, before parsing or publication.
- Accept only supported CSV upload kinds and parse file contents as data. Do not trust the client filename or declared content type. Reject unsupported extensions, malformed CSV, unsupported encoding, and structurally invalid files. The API's UTF-8 choice and BOM behavior remain under review.
- Validate required fields, non-empty feedback/reason, timestamps, IDs, and upload-kind constraints on the backend. Enforce approved column-mapping rules, bind mapping/header indices and text to the immutable preview, and require a new preview when bytes or mappings change.
- Keep preview confirmation bound to the immutable preview ID and verified hash of the exact staged bytes. Validate the hash again at confirmation. Preserve original source text and event time; identical re-uploads are no-ops and changed payloads are conflicts, never silent overwrites.
- Do not silently normalize source IDs or accept offset-free timestamps until their parsing/normalization rules are approved. Maximum CSV field/feedback length and model-context preflight are not defined; select them with the parser/model contract without silently truncating source text.
- Escape formula-leading values in any generated/exported CSV. Rejection reports contain safe row-level reasons and must not include secrets or unnecessary raw feedback.

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

- Keep append-only audit history for account, configuration, ingestion, reconciliation, and other administrative actions not already represented in incident history or notification attempts. Record actor, action, resource, outcome, request/correlation ID, timestamp, and idempotency identity where applicable.
- Keep audit before/after snapshots to the approved safe-field allowlist. Never include raw feedback, email addresses, password hashes, passwords, session IDs/tokens, CSRF values, API keys, arbitrary message subject/body, provider payloads, filesystem paths, or raw exceptions in generic audit snapshots.
- Preserve incident actions in append-only incident history. Preserve confirmed notification content only in its protected notification record, not generic audit/log records. Follow the API/Data Model contracts for the separate governed source and notification records.
- Logs and traces use safe error codes and opaque IDs. Do not record request bodies wholesale, credentials, raw uploaded rows, prompts, or feedback excerpts. Redact sensitive fields before telemetry is emitted.
- Decide which authentication and authorization events (for example, successful/failed sign-in, denied Admin operation, logout, and session revocation) belong in append-only audit history versus restricted operational security logs. No security-event taxonomy or dedicated event contract is currently approved; preserve generic login responses and never log submitted credentials or tokens.
- The approved capstone expectation is to retain synthetic operational history and audit evidence through the capstone period. This is not a production retention policy. Exact artifact expiry, backup cadence/retention, and deletion effects remain open under OPS-03.

## 13. API validation, rate limiting, and error handling

- Validate every request on the server, including authentication state, role, resource state, request shape, allowed values, length bounds, pagination/filter bounds, and idempotency behavior. Frontend validation is advisory only.
- Use parameterized SQL. Do not interpolate request values into SQL, shell commands, filesystem paths, logs, prompts, or HTML. Escape untrusted text in UI rendering and CSV exports.
- Enforce authorization on every protected endpoint and re-check state-sensitive permissions at mutation time. For notification confirmation, re-check recipient authorization and preview binding rather than trusting an earlier preview. For retries, re-check server-derived eligibility at submission.
- Rate limits are required for authentication and other abuse/cost-sensitive endpoints, but exact scopes, thresholds, windows, and retry behavior are open. Select them before dependent implementation. The API baseline supports `429` and `Retry-After`; clients must not enter retry loops.
- Follow the API problem contract: `401` for missing/expired/invalid authentication; `403` for denied role/action; `404` for unavailable resources where that avoids disclosure; `409` for stale state, hash, or idempotency conflicts; `413` for upload size; `415` for unsupported input; `422` for invalid requests; `429` for rate limiting; and generic redacted `5xx`/`503` responses for internal or provider failures.
- Error responses must not reveal account existence, secrets, local paths, raw SQL/provider errors, prompt/feedback text, or stack traces. Return stable safe codes and a request ID when available; retain restricted internal diagnostics without sensitive payloads.
- API version prefix, detailed CORS policy, and numeric rate limits remain unresolved. Do not treat current OpenAPI response shapes as approval of those omitted policies.

## 14. Security testing and acceptance criteria

These are specification-level acceptance criteria for future implementation verification. They do not select a test framework or authorize application code/tests in this change.

| ID | Acceptance criterion |
|---|---|
| SEC-AC01 | Passwords are stored only as secure salted adaptive hashes; no API, log, audit, or UI response exposes a password or hash. The selected algorithm and parameters are recorded before implementation. |
| SEC-AC02 | Login establishes only a server-side session for an active account; the browser receives a `Secure`, `HttpOnly` cookie and never stores the bearer token in web storage. Expiry, logout, and account deactivation invalidate sessions according to the approved session policy. |
| SEC-AC03 | Missing or invalid CSRF protection blocks every cookie-authenticated state-changing request without side effects. Login bootstrap, token issuance/rotation, cookie policy, and CORS behavior match the approved security decision. |
| SEC-AC04 | Direct requests by a Business User to each Admin-only route return `403`; an upload denial stores no bytes and creates no upload preview or job. Admin-only user/configuration/processing permissions are enforced even when UI controls are bypassed. |
| SEC-AC05 | Public self-registration and SSO are unavailable. The first Admin is created only through the protected setup command. User deactivation and session revocation are atomic from the application's perspective. |
| SEC-AC06 | OpenAI and mail credentials are absent from browser bundles, repository content, prompts, logs, generic audit snapshots, responses, and errors. |
| SEC-AC07 | Upload tests cover authorized and unauthorized actors, exact configured byte and row limits, malformed/unsupported inputs, mapping/hash changes, duplicate/conflicting identities, and path-escape attempts. Artifact access is through an authorized backend route; a mismatched hash or unresolved ID fails closed. |
| SEC-AC08 | Adversarial feedback that requests secrets, instruction override, taxonomy override, output-shape override, or tool use is treated only as classification data or uncertainty. No tool or side effect is executed; output validation remains server-side. |
| SEC-AC09 | A manual email preview creates no outbox row/send. Confirmation rejects unauthorized or inactive recipients, changed preview content, invalid CSRF, or mismatched idempotency use. A replay of the same confirmation does not duplicate the event. No supplier or unapproved real address is contacted. |
| SEC-AC10 | Audit/log review finds no raw feedback, passwords, hashes, session/CSRF/reset tokens, provider secrets/payloads, arbitrary message content, email addresses in generic snapshots, filesystem paths, or raw exception details. |
| SEC-AC11 | Invalid requests return safe, stable problem responses and request IDs where specified; no error leaks secrets, account existence, or internal stack details. Rate-limited requests receive `429` and the approved retry guidance. |
| SEC-AC12 | The non-production deployment uses TLS, protected server-side secrets, least-privilege SQLite/artifact storage, one active API/worker instance with shared persistent local storage, synthetic/permitted non-sensitive data, health checks, backup/restore verification, and a demonstrated rollback. |
| SEC-AC13 | SQL-injection test inputs supplied through query parameters, request bodies, filters, and uploaded-file fields do not alter query structure, bypass authorization, or expose or modify data outside the caller's permissions. Database access uses parameterized queries; responses and logs do not disclose raw SQL or database errors. |
| SEC-AC14 | Stored and reflected user-controlled content, including feedback, CSV headers and values, and rejection-report content, is rendered as inert text. Test markup and script payloads do not execute in the browser or create active HTML in any UI surface. |
| SEC-AC15 | CSV export tests include formula-leading values in feedback, headers, and other user-controlled fields. Exported values are safely escaped so spreadsheet software does not evaluate them as formulas, while source data remains unchanged. |
| SEC-AC16 | When cross-origin requests are configured, a request from an origin outside the approved exact-origin allowlist receives no permissive `Access-Control-Allow-Origin` or credential-sharing response. The server does not use wildcard credentialed CORS or reflect arbitrary origins; backend authentication and authorization remain enforced independently of CORS. |

Before a security decision is finalized, verify that test cases use the approved values and do not silently convert an open item into a test default. Backend/API and frontend test runners, repeatable local PowerShell scripts, and the documented pre-merge checklist are selected in TECH_STACK.md under ARC-06 and PRD change RC-01. Security checks remain automated and required; retain their results with the exact-revision checklist evidence.

## 15. Non-production deployment security

- Use only a non-production environment. The PRD requires TLS, protected secrets, health checks, operational visibility, a runbook, and rollback evidence. No production deployment or multi-tenant guarantee is claimed.
- The approved deployment constraint is one active application instance, one API and one worker, and persistent local storage for SQLite plus protected artifacts accessible to both. Do not assume a network filesystem, multi-instance writes, or another database/broker.
- Apply least-privilege filesystem and process access to database, WAL/sidecar files, and artifact storage. Keep artifact storage outside public/static serving and Git. Restrict administrative deployment access and secret access to the backend deployment administrator.
- Keep provider calls in backend processes. Do not configure production mail, supplier mail, public signup, or sensitive production data in this environment.
- Backups must capture SQLite and all referenced artifacts as one consistent recovery set. Quiesce API/worker writes or use an SQLite-consistent mechanism; verify database integrity, foreign keys, artifact resolution, and hashes before restart. Cadence, retention, and exact backup mechanism remain open.
- The preferred single Linux VM/Docker Compose topology is Proposed, not approved. No cloud provider or frontend static-host arrangement is selected. Verify provider support for local persistent storage, secrets, TLS, health, logs, backups, and rollback before deployment approval.

## 16. Unresolved decisions and implementation dependencies

The following remain unresolved and unapproved by this document. Resolve each before implementation that depends on it; preserve current conditional baselines and activation gates.

| Decision / reference | Still needed | Blocks or constrains |
|---|---|---|
| Password scheme and policy — SEC-01, API `CreateUserRequest` | Hash algorithm/library and parameters; password strength and length policy; initial-password delivery and first-login change behavior; hash upgrade policy. | Password creation, login, and user provisioning. |
| Account identity — DATA_MODEL §4.1 | Email canonicalization, case-insensitive uniqueness, and normalization behavior. | Login lookup and the `email_normalized` unique key. |
| Initial Admin setup — SEC-01 | Secure CLI input method, authorization boundary, and repeat/first-Admin guard. | Bootstrap implementation. |
| Sessions and cookies — SEC-01, API security scheme | Absolute/idle expiry, renewal/rotation, concurrent sessions, cleanup, revocation on recovery/password change, cookie attributes beyond `Secure`/`HttpOnly`, and approval of proposed name `productpulse_session`. | Authentication/session implementation and deployed cookie behavior. |
| CSRF bootstrap and token lifecycle — API `CsrfTokenHeader` | How an unauthenticated browser obtains login protection; token creation, rotation, header name review, and Origin/Referer/Fetch Metadata checks. | Login and every cookie-authenticated mutation. |
| CORS and frontend host — API/Architecture/Tech Stack | Whether cross-origin access is needed; exact origin allowlist, credential handling, methods, and headers after hosting is selected. | Browser/API deployment configuration. |
| Password recovery — SEC-01, UI §4.1 | Whether recovery is Admin-assisted, self-service, or excluded; permitted delivery channel; anti-enumeration, token lifecycle, audit, throttling, and session revocation. | Any reset/recovery flow. Existing UI/API does not define one. |
| Rate limits — API, OPS-02, AI_SPEC §18 | Numeric policies for login, sensitive mutation, upload, provider/cost-sensitive routes, and other public/abuse-sensitive surfaces. | Endpoint implementation and `429` behavior. |
| Security-event audit scope — DATA_MODEL §4.7, API audit contract | Events to record for sign-in outcomes, denied actions, logout/session revocation, storage/access scope, and retention alignment. | Authentication/audit implementation; do not add sensitive fields to the approved audit snapshot allowlist. |
| Upload parser contract — API `x-csv-input-contract`, PRD §7 | Exact 20 MB bytes, BOM/encoding behavior, parser version naming, timezone-offset handling, source-ID normalization, and maximum field/feedback length. | Upload parser and model input preflight. Do not truncate source text silently. |
| Artifact lifecycle — OPS-03/OPS-06 | Preview, upload, rejection-report expiry/retention, cleanup ordering, deletion audit effects, backup cadence/retention/mechanism. | Artifact cleanup and operational recovery. |
| Manual preview token — API, UI §4.7, ALERT_SPEC §5 | Storage, entropy/verification, expiry, replay, repeat-preview behavior, and actor/session binding implementation details. | Manual notification preview and confirmation. |
| Recipient directory and email sink — SEC-03, PRD §19.1, ARC-05 | Formal final sandbox directory/fallback approval, routing semantics, concrete capture sink/provider, provider credential/verification behavior. | Manual/automatic notification configuration and any delivery. No real email. |
| Deployment host and secrets — OPS-01 | Provider selection and proof of single-instance persistent-local-storage fit; secret storage, TLS, CORS origin, file permissions, health, backup, and rollback setup. | Non-production deployment approval. |
| Retention and data scope — PRD §13, OPS-03, AI_SPEC §14 | Artifact/audit operational retention details; any future non-synthetic data requires separate privacy/provider-control approval. | Retention automation or data-scope expansion. |
| Test and local verification tools — TECH_STACK §93 | Backend/API pytest with FastAPI TestClient, frontend Vitest with React Testing Library, and repeatable local PowerShell check scripts with documented pre-merge evidence are approved. GitHub Actions and hosted CI merge gates are excluded. | Implement checks with the relevant tickets; retain security acceptance criteria and exact-revision evidence. Criteria in §14 remain tool-neutral. |

### Cross-document gaps to resolve

1. The login operation references a CSRF header but does not define pre-authentication token acquisition. This must be aligned with API_SPEC.yaml before implementation.
2. The API describes a same-origin server but the static frontend host is not selected. CORS must be reviewed against the chosen deployment topology.
3. The API/Data Model/UI point session and recovery policy here but intentionally leave exact values open. This document enumerates the choices; it does not approve them.
4. The API carries a draft 20 MB limit, UTF-8/BOM and timestamp parsing notes, and a named session cookie/header; those details remain explicitly subject to review. Preserve the open status until approved.
5. ALERT_SPEC.md v0.2 is Draft. Its preview-token and notification controls do not authorize activation. Final recipient/fallback/sink decisions and the PRD's directory sign-off remain outstanding.
6. Detection remains gated by PB-01 threshold calibration, DAI-06 coverage parameters, and authoritative completed-classification attempt selection. Nothing in this document enables detection or automatic email.
7. Exact rate limits, artifact retention, backup cadence/retention/mechanism, deployment provider, and test tooling are not defined in the approved baselines.
8. The current audit contract covers administrative actions and safe snapshots but does not define a security-event taxonomy for authentication successes/failures or denied requests.

## 17. Source consistency and change control

This document is subordinate to the PRD for product behavior and to the Decision Register for approval status. Where a detail in this document conflicts with an approved decision, stop and reconcile the specifications; do not infer that this security baseline supersedes them. In particular:

- Preserve the PRD's Admin/Business User permissions, Admin-only ingestion, protected first-Admin setup, secure password hash, backend sessions, secure cookies, CSRF protection, and no public registration/SSO.
- Preserve SEC-01 through SEC-04 only at their approved scope. An unresolved detail in the open-decision table remains unresolved until separately approved.
- Preserve the API/Data Model/UI conditional design-baseline status and all documented prerequisites. Do not promote an API proposal or Alert/Detection draft into approved behavior by reference here.
- Keep OpenAI calls backend-only, deterministic defect/alert logic on the backend, customer feedback untrusted, and secrets out of frontend/logs/API responses.
- Keep real email and sensitive customer data outside the MVP boundary. No notification, deployment, or detection feature is activated by this security specification.

Changes to an approved security decision require an explicit decision-register update and aligned revisions to affected API, data, architecture, UI, AI, alert, and operations specifications before dependent implementation.
