from contextlib import asynccontextmanager
from datetime import UTC, datetime
import threading
from typing import Literal
import uuid

from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from productpulse.api_common import ApiError, problem_response, request_id
from productpulse.auth_api import router as auth_router
from productpulse.auth_state import LoginThrottle, PreLoginTokens
from productpulse.conflicts_api import router as conflicts_router
from productpulse.logging_config import configure_logging
from productpulse.ingestion_api import router as ingestion_router
from productpulse.ingestion_confirmation import router as ingestion_confirmation_router
from productpulse.ingestion_jobs_api import router as ingestion_jobs_router
from productpulse.linkage_api import router as linkage_router
from productpulse.product_api import router as product_router
from productpulse.settings import Settings


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy"]
    checked_at: datetime


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            engine = application.state.database_engine
            if engine is not None:
                engine.dispose()

    app = FastAPI(title="ProductPulse API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database_engine = None
    app.state.database_lock = threading.Lock()
    app.state.prelogin_tokens = PreLoginTokens()
    app.state.login_throttle = LoginThrottle()

    @app.middleware("http")
    async def safe_request_headers(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id(request)
        if request.url.path.startswith(("/auth/", "/admin/users", "/admin/ingestion", "/admin/reconciliation")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        response = problem_response(request, error)
        if request.url.path.startswith(("/auth/", "/admin/users", "/admin/ingestion", "/admin/reconciliation")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        response = JSONResponse(
            {
                "type": "https://productpulse.invalid/problems/validation_error",
                "title": "Validation failed",
                "status": 422,
                "code": "VALIDATION_ERROR",
                "detail": "The request contains invalid fields.",
                "instance": request.url.path,
                "request_id": request_id(request),
                "errors": [
                    {
                        "field": ".".join(str(part) for part in issue.get("loc", ())[1:]) or "request",
                        "code": "INVALID_VALUE",
                        "message": "The value is invalid.",
                    }
                    for issue in error.errors()
                ],
            },
            status_code=422,
        )
        if request.url.path.startswith(("/auth/", "/admin/users", "/admin/ingestion", "/admin/reconciliation")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        status_code = error.status_code
        title = "Not found" if status_code == 404 else "Request failed"
        code = "NOT_FOUND" if status_code == 404 else "HTTP_ERROR"
        response = JSONResponse(
            {
                "type": f"https://productpulse.invalid/problems/{code.lower()}",
                "title": title,
                "status": status_code,
                "code": code,
                "detail": "The requested resource was not found." if status_code == 404 else "The request could not be completed.",
                "instance": request.url.path,
                "request_id": request_id(request),
            },
            status_code=status_code,
            headers=error.headers,
        )
        if request.url.path.startswith(("/auth/", "/admin/users")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health", tags=["Operations"], response_model=HealthResponse)
    def get_health() -> HealthResponse:
        """Return the public coarse process health probe without dependencies."""

        return HealthResponse(status="healthy", checked_at=datetime.now(UTC))

    app.include_router(auth_router)
    app.include_router(ingestion_router)
    app.include_router(ingestion_confirmation_router)
    app.include_router(ingestion_jobs_router)
    app.include_router(linkage_router)
    app.include_router(conflicts_router)
    app.include_router(product_router)

    return app


app = create_app()

