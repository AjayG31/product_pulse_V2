from __future__ import annotations

import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from productpulse.api_common import ApiError, request_id, safe_audit, validate_idempotency_key
from productpulse.api_schemas import FeedbackLinkageRequest, FeedbackLinkageResponse
from productpulse.auth_api import AuthContext, _check_session_csrf, get_admin_context
from productpulse.models import AuditEvent, BackgroundJob, Batch, Feedback, FeedbackLinkageEvent, Supplier
from productpulse.security.sessions import utc_text


router = APIRouter()
MAX_ATTEMPTS = 3


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(body: FeedbackLinkageRequest) -> str:
    return hashlib.sha256(_canonical(body.model_dump()).encode("utf-8")).hexdigest()


def _response(event: FeedbackLinkageEvent) -> FeedbackLinkageResponse:
    if not event.new_supplier_id or not event.new_batch_id or not event.recompute_job_id:
        raise ApiError(503, "LINKAGE_EVENT_INVALID", "The saved linkage event is unavailable.", "Request failed")
    return FeedbackLinkageResponse(
        feedback_id=event.feedback_id,
        linkage_status=event.new_status,
        supplier_id=event.new_supplier_id,
        batch_id=event.new_batch_id,
        linkage_event_id=event.linkage_event_id,
        recompute_job_id=event.recompute_job_id,
        updated_at=event.created_at,
    )


def _existing_idempotent_result(context: AuthContext, work_key: str, fingerprint: str) -> FeedbackLinkageResponse | None:
    db = context.db
    job = db.scalar(select(BackgroundJob).where(BackgroundJob.work_key == work_key))
    if job is None:
        return None
    event = db.scalar(select(FeedbackLinkageEvent).where(FeedbackLinkageEvent.recompute_job_id == job.background_job_id))
    if event is None:
        raise ApiError(503, "LINKAGE_EVENT_INVALID", "The saved linkage event is unavailable.", "Request failed")
    audit = db.scalar(select(AuditEvent).where(
        AuditEvent.action == "FEEDBACK_LINKAGE_UPDATED",
        AuditEvent.resource_type == "FEEDBACK_LINKAGE_EVENT",
        AuditEvent.resource_id == event.linkage_event_id,
    ))
    try:
        recorded = json.loads(audit.after_state_text or "{}") if audit is not None else {}
    except (json.JSONDecodeError, TypeError):
        recorded = {}
    if recorded.get("request_fingerprint") != fingerprint:
        raise ApiError(409, "IDEMPOTENCY_CONFLICT", "The Idempotency-Key was already used for a different linkage request.", "Conflict")
    return _response(event)


@router.put(
    "/admin/feedback/{feedback_id}/linkage",
    response_model=FeedbackLinkageResponse,
    tags=["Reconciliation"],
)
def reconcile_feedback_linkage(
    feedback_id: str,
    body: FeedbackLinkageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
) -> FeedbackLinkageResponse:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    work_key = f"linkage-recompute:{feedback_id}:{key_hash}"
    fingerprint = _fingerprint(body)
    db = context.db
    db.rollback()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        replay = _existing_idempotent_result(context, work_key, fingerprint)
        if replay is not None:
            db.commit()
            return replay

        feedback = db.scalar(select(Feedback).where(Feedback.feedback_id == feedback_id))
        if feedback is None:
            raise ApiError(404, "FEEDBACK_NOT_FOUND", "The requested feedback record was not found.", "Not found")
        if (
            feedback.linkage_status != body.expected_linkage_status
            or feedback.supplier_id != body.expected_supplier_id
            or feedback.batch_id != body.expected_batch_id
        ):
            raise ApiError(409, "LINKAGE_STATE_CONFLICT", "The feedback linkage changed. Reload it before reconciling.", "Conflict")

        supplier = db.get(Supplier, body.supplier_id)
        batch = db.scalar(select(Batch).where(
            Batch.batch_id == body.batch_id,
            Batch.product_id == feedback.product_id,
            Batch.supplier_id == body.supplier_id,
        ))
        if supplier is None or batch is None:
            raise ApiError(422, "LINKAGE_REFERENCE_INVALID", "Choose an existing supplier and a batch linked to this product and supplier.", "Validation failed")

        now = utc_text()
        prior_supplier = feedback.supplier_id
        prior_batch = feedback.batch_id
        prior_status = feedback.linkage_status
        recompute_job = BackgroundJob(
            background_job_id=f"bgj_{uuid.uuid4().hex}",
            job_type="RECONCILIATION",
            work_key=work_key,
            ingestion_job_id=None,
            status="QUEUED",
            attempt_count=0,
            max_attempts=MAX_ATTEMPTS,
            scheduled_at=now,
            next_attempt_at=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            provider_input_file_id=None,
            provider_batch_id=None,
            last_error_code=None,
            last_error_summary=None,
            created_at=now,
            started_at=None,
            completed_at=None,
        )
        db.add(recompute_job)
        db.flush()
        feedback.supplier_id = supplier.supplier_id
        feedback.batch_id = batch.batch_id
        feedback.linkage_status = "LINKED"
        event = FeedbackLinkageEvent(
            linkage_event_id=f"fle_{uuid.uuid4().hex}",
            feedback_id=feedback.feedback_id,
            actor_user_id=context.user.user_id,
            ingestion_job_id=None,
            previous_supplier_id=prior_supplier,
            previous_batch_id=prior_batch,
            new_supplier_id=supplier.supplier_id,
            new_batch_id=batch.batch_id,
            previous_status=prior_status,
            new_status="LINKED",
            resolution_method="ADMIN_RECONCILIATION",
            reason=body.reason,
            recompute_job_id=recompute_job.background_job_id,
            created_at=now,
        )
        db.add(event)
        db.flush()
        safe_audit(
            db,
            action="FEEDBACK_LINKAGE_UPDATED",
            resource_type="FEEDBACK_LINKAGE_EVENT",
            resource_id=event.linkage_event_id,
            actor_user_id=context.user.user_id,
            before={"linkage_status": prior_status, "supplier_id": prior_supplier, "batch_id": prior_batch},
            after={
                "linkage_status": "LINKED",
                "supplier_id": supplier.supplier_id,
                "batch_id": batch.batch_id,
                "recompute_job_id": recompute_job.background_job_id,
                "request_fingerprint": fingerprint,
                "reason": body.reason,
            },
            request_id_value=request_id(context.request),
        )
        db.commit()
        return _response(event)
    except ApiError:
        if db.in_transaction():
            db.rollback()
        raise
    except IntegrityError as error:
        if db.in_transaction():
            db.rollback()
        raise ApiError(409, "LINKAGE_STATE_CONFLICT", "The linkage changed while the request was being processed.", "Conflict") from error
    except Exception as error:
        if db.in_transaction():
            db.rollback()
        raise ApiError(503, "LINKAGE_UPDATE_FAILED", "The linkage could not be updated. Try again.", "Request failed") from error
