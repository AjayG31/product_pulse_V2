# ProductPulse

ProductPulse is an AI-powered retail product quality monitoring and early-warning platform. The approved MVP stack is React + TypeScript, FastAPI, SQLite, and one separate Python worker.

## Local foundation

- Use Node.js 22.22 or newer and npm 11.20.0 for the frontend.
- Use CPython 3.12.16 and the project-pinned uv release in `tooling/uv.version` for the backend. `.tools/` contains only ignored local tooling and caches.
- Install project dependencies with `uv sync --locked` and `npm ci` after the lockfiles are created.
- Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Ticket PP-010` for the foundation checks. The approved local runner uses pytest/FastAPI TestClient, Vitest/React Testing Library, Bandit, pip-audit, and npm audit as applicable. It does not use GitHub Actions or Playwright.
- See [the local pre-merge checklist](docs/PRE_MERGE_CHECKLIST.md) for exact-revision evidence requirements.

The public `GET /health` route reports only the coarse process health contract. It does not assert that optional dependencies or worker handlers are ready.

## Configuration boundary

The backend reads `PRODUCTPULSE_DATA_DIR` and `PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS` from the server process environment when database access is initialized. Neither has a default. PP-007 owns the busy-timeout value; until that decision is recorded, do not invent one. `PRODUCTPULSE_OPENAI_API_KEY` is an optional backend-only secret setting and is unused in this foundation. Never put secrets in frontend variables, source control, logs, or API responses.

Copy `.env.example` only as a reference; its blank values are placeholders, not runnable defaults. Authentication, ingestion, classification, detection activation, and notification behavior are outside the current milestone.

