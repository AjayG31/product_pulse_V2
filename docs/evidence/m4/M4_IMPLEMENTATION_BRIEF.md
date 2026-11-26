# ProductPulse M4 implementation brief

**Milestone:** M4 — Admin security verification and management workflows  
**Prepared:** 25 November 2026  
**Authorization:** Product Owner explicitly approved PP-029, PP-048, and PP-037 in this order on 25 November 2026. Approval covers their implementation/verification, focused tests, minimal backwards-compatible local check-runner support, and M4 evidence. It does not authorize other tickets, production changes, live AI/provider calls, deployment, commits, pushes, or merges.

## 1. Active source and baseline

- Active checkout: `D:\Roshni_Luthria_OneDrive\OneDrive - C5i\Desktop\capstone project - ajay`.
- Branch: `dev-roshni`; starting Git revision: `b287b97a52e14c6bc4525e65bcb54b1bde74303a`.
- The working tree was clean at preparation. The attached chat handoff was used as context only; its former “M4 not approved” statement is superseded by the current explicit milestone approval.
- M3 closure and its PP-036 API acceptance evidence are present in `M3_COMPLETION_REPORT.md` and `PP-036.txt`. The current ticket files record PP-029, PP-048, and PP-037 as Implementation Ready (reviewed 24 November 2026), each with complete dependencies. The Implementation Plan ticket table still has older “blocked by” wording for PP-029/PP-048, and Architecture §5 still cites API_SPEC 1.5.3. These are stale status/version notes: the dependencies are Done in retained M1/M2/M3 evidence, the current Decision Register is v2.3, and the current API_SPEC is v1.5.4. They do not change the approved contracts or block the tickets.

## 2. Governing requirements and specifications

- Product requirements: PRD v1.7; implementation sequencing and readiness: Implementation Plan v1.3; closure gates: Definition of Done.
- Architecture: v1.6; API contract: API_SPEC.yaml v1.5.4; UI contract: UI_SPEC.md v0.4.3; security contract: SECURITY.md v1.1; Decision Register v2.3; current data model baseline v1.5.5.
- PP-029: SEC-01/02 Approved; PP-003 and PP-012 Done. Scope covers SEC-AC01–05 as applicable, focused on authentication/session lifecycle, CSRF, authorization, account lifecycle, password secrecy, initial Admin setup, and denied side effects.
- PP-048: DAI-01/02 Approved; PP-001, PP-010, PP-012, and PP-036 Done. The UI must consume the existing PP-036 API and preserve its kind-specific choices: SOURCE_PAYLOAD allows KEEP_EXISTING/DISMISS; REFERENCE_MAPPING also permits APPLY_INCOMING_REFERENCE only with the expected mapping hash. Only API-approved safe fields may be shown. Conflict review and feedback linkage remain separate workflows.
- PP-037: PP-001, PP-010, and PP-012 Done; SEC-01/02 Approved. Only ADMIN and BUSINESS_USER roles exist. The existing API owns user listing, create, deactivate, and temporary-password reset; create/reset values are write-only and never appear in public user responses.

## 3. Bounded scope and execution order

1. **PP-029 — Security verification.** Recheck its named dependencies and SEC-01/02 immediately before start; inspect and test the existing server boundary before other M4 work. Add focused tests where existing automated coverage does not map to acceptance. Any material vulnerability, authorization bypass, or serious unresolved security finding is an immediate stop: retain safe evidence, document impact/reproduction/remediation, and wait for explicit direction. Do not repair such a finding and continue under this approval.
2. **PP-048 — Admin conflict review UI.** Only after PP-029 checks pass. Add the Admin queue, filters, safe detail, and explicit permitted resolution controls against PP-036. Cover loading, empty, error, success, stale 409, Admin/Business User access, safe data rendering, and no guessed action. No backend/API/schema/database changes.
3. **PP-037 — Admin user-management UI.** Only after PP-048 acceptance passes. Add Admin list, provisioning, deactivation, and reset flows against PP-012. Cover validation, authorization, errors, write-only temporary-password handling, and clearing values after submit/dismiss. No backend/API/schema/database changes.

## 4. Acceptance checks and retained evidence

The approved stack is pytest/FastAPI TestClient, Vitest/React Testing Library, local PowerShell scripts, and applicable Bandit/dependency checks. No Playwright or GitHub Actions. Before PP-029 started, `scripts/check.ps1` was extended additively: its `ValidateSet`, M4 evidence-path default, and `switch` now include PP-029/037/048; all existing ticket branches and semantics remain unchanged. It still accepts `-EvidencePath` for ticket transcripts. The runner prefers the local pinned npm under `.tools/npm` when present and otherwise retains its former global npm fallback.

Planned commands and criteria mapping after that additive runner support:

| Ticket | Acceptance focus and automated checks | Evidence |
|---|---|---|
| PP-029 | `scripts/check.ps1 -Ticket PP-029 -EvidencePath docs/evidence/m4/PP-029.txt`; targeted `pytest tests/test_auth.py` plus existing protected-route tests for conflicts, ingestion, and linkage; full `pytest -q`; Bandit; pip-audit. Map to authentication/password, session expiry/revocation, pre-login/session CSRF, Admin/Business User and forced-change restrictions, one-time bootstrap, safe password handling/audit, and denial side effects. | Transcript and review/disposition in `PP-029.txt`; update `tickets/PP-029.md` only if all DoD checks pass. |
| PP-048 | `scripts/check.ps1 -Ticket PP-048 -EvidencePath docs/evidence/m4/PP-048.txt`; `pytest tests/test_conflict_resolution.py -q`; targeted `frontend/src/ConflictReview.test.tsx`; full `npm run test`; `npm run build` (TypeScript + production build); `npm audit`. | Transcript and acceptance/review notes in `PP-048.txt`; link in `tickets/PP-048.md`. |
| PP-037 | `scripts/check.ps1 -Ticket PP-037 -EvidencePath docs/evidence/m4/PP-037.txt`; `pytest tests/test_auth.py -q`; targeted `frontend/src/UserManagement.test.tsx`; full `npm run test`; `npm run build`; `npm audit`. | Transcript and acceptance/review notes in `PP-037.txt`; link in `tickets/PP-037.md`. |

At closeout, run the full backend suite and relevant final frontend/security/dependency checks against the final source; run `git diff --check`, retain the exact Git revision and clean/dirty state, and summarize exact commands/counts/warnings in `M4_COMPLETION_REPORT.md`. No lint command is defined in the active package scripts; `npm run build` performs `tsc --noEmit` and Vite production build. The missing tooling has been restored in workspace-local ignored paths without tracked dependency changes: uv 0.13.9, CPython 3.12.16, Node 24.19.0, npm 11.20.0, and lockfile-installed dependencies. The final PP-029 check passed with 51 focused tests, 110 backend tests, clean Bandit, and no known pip-audit vulnerabilities; see `PP-029.txt` and `PP-029_TEST_TRIAGE.md`.

## 5. Security hold points, exclusions, and evidence rules

- Stop before any dependent M4 work if PP-029 discovers a serious security/authorization issue, if an approved contract/decision is missing or contradictory, or if a required check cannot pass within the ticket scope. Keep any dependent ticket paused. No security exception or spec change is inferred from milestone approval.
- No new API or database behavior, migrations, taxonomy seed/default issue codes, model selection, OpenAI call, classification/detection activation, incident-producing detection, notification provider/routing/sending, production data changes, deployment, commit, push, or merge. Do not implement PP-041, PP-043, PP-049, or any other ticket.
- Use synthetic data and mocked frontend API responses. Temporary passwords are test-only synthetic strings; never place them in evidence output.
- Retain ticket-level command results, pass/fail counts, warnings, revision identity, test mappings, code-review findings, and unresolved risks. If a UI behavior inherently needs visual observation, record a reproducible manual result in addition to its automated coverage.

**Completion rule:** M4 is recommended for acceptance only if all three tickets independently satisfy their Definition of Done in the authorized order. Product Owner acceptance remains pending until explicitly given.
