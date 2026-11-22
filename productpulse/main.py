from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from productpulse.logging_config import configure_logging


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy"]
    checked_at: datetime


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="ProductPulse API", version="0.1.0")

    @app.get("/health", tags=["Operations"], response_model=HealthResponse)
    def get_health() -> HealthResponse:
        """Return the public coarse process health probe without dependencies."""

        return HealthResponse(status="healthy", checked_at=datetime.now(UTC))

    return app


app = create_app()

