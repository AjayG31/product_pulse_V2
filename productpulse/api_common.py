from collections.abc import Iterable
from dataclasses import dataclass
import json
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from productpulse.models import AuditEvent
from productpulse.security.sessions import utc_text


@dataclass
class ApiError(Exception):
    status: int
    code: str
    detail: str
    title: str = "Request failed"
    headers: dict[str, str] | None = None
    retry_eligibility: dict[str, object] | None = None


def request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if value is None:
        value = uuid.uuid4().hex
        request.state.request_id = value
    return value


def problem_response(request: Request, error: ApiError) -> JSONResponse:
    body = {
        "type": f"https://productpulse.invalid/problems/{error.code.lower()}",
        "title": error.title,
        "status": error.status,
        "code": error.code,
        "detail": error.detail,
        "instance": request.url.path,
        "request_id": request_id(request),
    }
    if error.retry_eligibility is not None:
        body["retry_eligibility"] = error.retry_eligibility
    return JSONResponse(body, status_code=error.status, headers=error.headers)


def safe_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    actor_user_id: str | None,
    outcome: str = "SUCCESS",
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    request_id_value: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        audit_event_id=uuid.uuid4().hex,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        before_state_text=json.dumps(before, sort_keys=True, separators=(",", ":")) if before else None,
        after_state_text=json.dumps(after, sort_keys=True, separators=(",", ":")) if after else None,
        request_id=request_id_value,
        created_at=utc_text(),
    )
    db.add(event)
    return event


def add_request_id_header(response, request: Request) -> None:
    response.headers["X-Request-ID"] = request_id(request)


def validate_idempotency_key(value: str | None) -> str:
    if value is None or not 1 <= len(value) <= 128 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ApiError(400, "INVALID_IDEMPOTENCY_KEY", "A valid Idempotency-Key header is required.", "Invalid request")
    return value


def page_meta(page: int, page_size: int, total: int) -> dict[str, int]:
    return {
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": (total + page_size - 1) // page_size,
    }

