# ProductPulse

ProductPulse is an AI-powered retail product quality monitoring and early-warning platform. The approved MVP stack is React + TypeScript, FastAPI, SQLite, and one separate Python worker.

## Local foundation

- Use Node.js 22.22 or newer and npm 11.20.0 for the frontend.
- Use CPython 3.12.16 and the project-pinned uv release in `tooling/uv.version` for the backend. `.tools/` contains only ignored local tooling and caches.
- Install project dependencies with `uv sync --locked` and `npm ci` after the lockfiles are created.
- Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Ticket PP-010` for the foundation checks. M2 ticket checks use `-Ticket PP-012`, `PP-013`, or `PP-014` and retain per-ticket evidence under `docs/evidence/m2/`. The approved local runner uses pytest/FastAPI TestClient, Vitest/React Testing Library, Bandit, pip-audit, and npm audit as applicable. It does not use GitHub Actions or Playwright.
- See [the local pre-merge checklist](docs/PRE_MERGE_CHECKLIST.md) for exact-revision evidence requirements.

The public `GET /health` route reports only the coarse process health contract. It does not assert that optional dependencies or worker handlers are ready.

## Configuration boundary

The backend reads `PRODUCTPULSE_DATA_DIR` and `PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS` from the server process environment when database access is initialized. Neither has a default. Keep `PRODUCTPULSE_DATA_DIR` outside the application repository and public/static directories; it stores the SQLite database and protected CSV artifacts. PP-007 owns the busy-timeout value; until that decision is recorded, do not invent one. `PRODUCTPULSE_OPENAI_API_KEY` is an optional backend-only secret setting and is unused in this foundation. Never put secrets in frontend variables, source control, logs, or API responses.

Copy `.env.example` only as a reference; its blank values are placeholders, not runnable defaults. For local authentication, configure `PRODUCTPULSE_DATA_DIR` and `PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS`, apply schema migrations with `uv run alembic upgrade head`, and provision the first Admin with `uv run python -m productpulse.bootstrap_admin`. The setup command accepts the password only through a hidden prompt. Login throttles are process-local and reset when the API process restarts. OpenAI classification, detection activation, and notifications remain outside M2.

For PP-014 feedback confirmation, choose an explicit processing mode. Confirmation persists the feedback, ingestion job, and one durable `CLASSIFICATION` queue item in the same SQLite transaction. The queue item snapshots `max_attempts=3`; M2 does not claim or execute it, retry it, or call OpenAI. Remaining retry and recovery parameters stay with PP-007.

