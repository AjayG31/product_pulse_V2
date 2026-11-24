from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from productpulse.api_common import ApiError, page_meta, request_id, safe_audit, validate_idempotency_key
from productpulse.api_schemas import (
    BackgroundJobResponse,
    IngestionJobPage,
    IngestionJobResponse,
    IngestionRetryResponse,
    IngestionJobStatus,
    RejectionReportLink,
    RetryEligibility,
    UploadKind,
)
from productpulse.auth_api import AuthContext, _check_session_csrf, get_admin_context
from productpulse.models import (
    AuditEvent,
    BackgroundJob,
    BackgroundJobAttempt,
    CsvUpload,
    IngestionJob,
    RejectionReportArtifact,
    UploadPreview,
)


router = APIRouter()

INGESTION_MAX_ATTEMPTS = 3
SAFE_REPLAY_SUMMARY = "Replay-safe work did not complete and may be attempted again."
UNKNOWN_OUTCOME_SUMMARY = "The job outcome could not be verified; automatic replay was not scheduled."
ABANDONED_OUTCOME_SUMMARY = "The worker lease expired without a persisted result."
_RETRY_WORK_KEY_PREFIX = "ingestion-recovery"


def _latest_run(db: Session, ingestion_job_id: str) -> BackgroundJob | None:
    return db.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.job_type == "INGESTION",
            BackgroundJob.ingestion_job_id == ingestion_job_id,
        )
        .order_by(BackgroundJob.created_at.desc(), BackgroundJob.background_job_id.desc())
        .limit(1)
    )


def _eligibility_for_run(db: Session, run: BackgroundJob | None) -> RetryEligibility:
    if run is None:
        return RetryEligibility(eligible=False, reason_code="NO_RETRYABLE_WORK")
    if run.status in {"QUEUED", "RUNNING", "RETRY_WAIT"}:
        return RetryEligibility(eligible=False, reason_code="WORK_IN_PROGRESS")
    if run.status in {"COMPLETED", "PARTIAL"}:
        return RetryEligibility(eligible=False, reason_code="NOT_FAILED")
    if run.status != "FAILED":
        return RetryEligibility(eligible=False, reason_code="NOT_RETRYABLE")
    if run.max_attempts != INGESTION_MAX_ATTEMPTS:
        return RetryEligibility(eligible=False, reason_code="RETRY_POLICY_BLOCKED")
    if run.attempt_count < 1:
        return RetryEligibility(eligible=False, reason_code="NO_RETRYABLE_WORK")

    attempt = db.get(BackgroundJobAttempt, (run.background_job_id, run.attempt_count))
    if attempt is None:
        return RetryEligibility(eligible=False, reason_code="OUTCOME_UNKNOWN")
    if attempt.outcome == "ABANDONED" or attempt.safe_error_summary in {
        UNKNOWN_OUTCOME_SUMMARY,
        ABANDONED_OUTCOME_SUMMARY,
    }:
        return RetryEligibility(eligible=False, reason_code="OUTCOME_UNKNOWN")
    if (
        attempt.outcome == "TERMINAL_FAILURE"
        and attempt.safe_error_summary == SAFE_REPLAY_SUMMARY
    ):
        if run.attempt_count != run.max_attempts:
            return RetryEligibility(eligible=False, reason_code="RETRY_POLICY_BLOCKED")
        return RetryEligibility(eligible=True, reason_code="ELIGIBLE")
    if attempt.outcome == "TERMINAL_FAILURE":
        return RetryEligibility(eligible=False, reason_code="PERMANENT_FAILURE")
    return RetryEligibility(eligible=False, reason_code="OUTCOME_UNKNOWN")


def _api_status(job: IngestionJob, run: BackgroundJob | None) -> str:
    if run is None:
        return job.status
    return {
        "QUEUED": "QUEUED",
        "RETRY_WAIT": "QUEUED",
        "RUNNING": "RUNNING",
        "COMPLETED": "COMPLETED",
        "PARTIAL": "PARTIAL",
        "FAILED": "FAILED",
    }.get(run.status, job.status)


def _effective_status_expression():
    latest_run_id = (
        select(BackgroundJob.background_job_id)
        .where(
            BackgroundJob.job_type == "INGESTION",
            BackgroundJob.ingestion_job_id == IngestionJob.job_id,
        )
        .order_by(BackgroundJob.created_at.desc(), BackgroundJob.background_job_id.desc())
        .limit(1)
        .correlate(IngestionJob)
        .scalar_subquery()
    )
    latest_status = (
        select(BackgroundJob.status)
        .where(BackgroundJob.background_job_id == latest_run_id)
        .correlate(IngestionJob)
        .scalar_subquery()
    )
    return case(
        (latest_status == "QUEUED", "QUEUED"),
        (latest_status == "RETRY_WAIT", "QUEUED"),
        (latest_status == "RUNNING", "RUNNING"),
        (latest_status == "COMPLETED", "COMPLETED"),
        (latest_status == "PARTIAL", "PARTIAL"),
        (latest_status == "FAILED", "FAILED"),
        else_=IngestionJob.status,
    )


def _next_run_time(previous_created_at: str) -> str:
    current = datetime.now(UTC)
    now = current.replace(microsecond=(current.microsecond // 1000) * 1000)
    previous = datetime.fromisoformat(previous_created_at.replace("Z", "+00:00"))
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=UTC)
    if now <= previous:
        now = previous + timedelta(milliseconds=1)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _api_job(db: Session, job: IngestionJob) -> IngestionJobResponse:
    run = _latest_run(db, job.job_id)
    report = db.scalar(
        select(RejectionReportArtifact).where(RejectionReportArtifact.preview_id == job.preview_id)
    )
    return IngestionJobResponse(
        job_id=job.job_id,
        preview_id=job.preview_id,
        idempotency_key=job.idempotency_key,
        processing_mode=job.processing_mode,
        status=_api_status(job, run),  # type: ignore[arg-type]
        counts={
            "total_rows": job.total_row_count,
            "accepted_rows": job.accepted_row_count,
            "rejected_rows": job.rejected_row_count,
            "duplicate_noop_rows": job.duplicate_row_count,
            "conflict_rows": job.conflict_row_count,
            "persisted_feedback": job.persisted_feedback_count,
        },
        retry_eligibility=_eligibility_for_run(db, run),
        created_at=job.created_at,
        started_at=run.started_at if run is not None else job.started_at,
        completed_at=run.completed_at if run is not None else job.completed_at,
        last_error_code=run.last_error_code if run is not None else job.last_error_code,
        rejection_report=RejectionReportLink(
            available=report is not None,
            href=f"/admin/ingestion/previews/{job.preview_id}/rejection-report" if report else None,
            content_type="text/csv; charset=utf-8" if report else None,
        ),
    )


def _api_run(run: BackgroundJob) -> BackgroundJobResponse:
    return BackgroundJobResponse(
        background_job_id=run.background_job_id,
        job_type=run.job_type,
        status=run.status,
        ingestion_job_id=run.ingestion_job_id,
        attempt_count=run.attempt_count,
        max_attempts=run.max_attempts,
        scheduled_at=run.scheduled_at,
        next_attempt_at=run.next_attempt_at,
        provider_batch_id=run.provider_batch_id,
        last_error_code=run.last_error_code,
        last_error_summary=run.last_error_summary,
        retry_eligibility=RetryEligibility(eligible=False, reason_code="NOT_FAILED"),
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _work_key(ingestion_job_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"{_RETRY_WORK_KEY_PREFIX}:{ingestion_job_id}:{digest}"


def _existing_recovery(
    db: Session,
    *,
    job: IngestionJob,
    work_key: str,
    idempotency_key: str,
) -> BackgroundJob | None:
    run = db.scalar(select(BackgroundJob).where(BackgroundJob.work_key == work_key))
    if run is None:
        return None
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "INGESTION_RECOVERY",
            AuditEvent.resource_type == "INGESTION_JOB",
            AuditEvent.resource_id == job.job_id,
        )
    ).all()
    for event in events:
        try:
            after = json.loads(event.after_state_text or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if after.get("run_id") == run.background_job_id and after.get("idempotency_key") == idempotency_key:
            return run
    raise ApiError(503, "INGESTION_RECOVERY_STATE_INVALID", "The recovery record is temporarily unavailable.", "Request failed")


@router.get(
    "/admin/ingestion/jobs",
    response_model=IngestionJobPage,
)
def list_ingestion_jobs(
    status: IngestionJobStatus | None = Query(default=None),
    upload_kind: UploadKind | None = Query(default=None),
    from_utc: datetime | None = Query(default=None, alias="from_utc"),
    to_utc: datetime | None = Query(default=None, alias="to_utc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    context: AuthContext = Depends(get_admin_context),
) -> IngestionJobPage:
    db = context.db
    stmt = select(IngestionJob)
    count_stmt = select(func.count()).select_from(IngestionJob)
    if upload_kind is not None:
        kind_filter = IngestionJob.preview_id == UploadPreview.preview_id
        stmt = stmt.join(UploadPreview, kind_filter).join(CsvUpload, CsvUpload.upload_id == UploadPreview.upload_id)
        count_stmt = count_stmt.join(UploadPreview, kind_filter).join(CsvUpload, CsvUpload.upload_id == UploadPreview.upload_id)
        stmt = stmt.where(CsvUpload.upload_kind == upload_kind)
        count_stmt = count_stmt.where(CsvUpload.upload_kind == upload_kind)
    if status is not None:
        effective_status = _effective_status_expression()
        stmt = stmt.where(effective_status == status)
        count_stmt = count_stmt.where(effective_status == status)
    if from_utc is not None:
        if from_utc.tzinfo is None:
            raise ApiError(422, "VALIDATION_ERROR", "from_utc must include a timezone.", "Validation failed")
        floor = from_utc.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        stmt = stmt.where(IngestionJob.created_at >= floor)
        count_stmt = count_stmt.where(IngestionJob.created_at >= floor)
    if to_utc is not None:
        if to_utc.tzinfo is None:
            raise ApiError(422, "VALIDATION_ERROR", "to_utc must include a timezone.", "Validation failed")
        ceiling = to_utc.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        stmt = stmt.where(IngestionJob.created_at <= ceiling)
        count_stmt = count_stmt.where(IngestionJob.created_at <= ceiling)
    if from_utc is not None and to_utc is not None and from_utc > to_utc:
        raise ApiError(422, "VALIDATION_ERROR", "from_utc must not be later than to_utc.", "Validation failed")

    total = int(db.scalar(count_stmt) or 0)
    jobs = db.scalars(
        stmt.order_by(IngestionJob.created_at.desc(), IngestionJob.job_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return IngestionJobPage(
        items=[_api_job(db, job) for job in jobs],
        page=page_meta(page, page_size, total),
    )


@router.get(
    "/admin/ingestion/jobs/{job_id}",
    response_model=IngestionJobResponse,
)
def get_ingestion_job(
    job_id: str,
    context: AuthContext = Depends(get_admin_context),
) -> IngestionJobResponse:
    db = context.db
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise ApiError(404, "INGESTION_JOB_NOT_FOUND", "The requested ingestion job was not found.", "Not found")
    return _api_job(db, job)


@router.post(
    "/admin/ingestion/jobs/{job_id}/retry",
    response_model=IngestionRetryResponse,
    status_code=202,
)
def retry_ingestion_job(
    job_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
) -> IngestionRetryResponse:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    db = context.db
    db.rollback()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        job = db.get(IngestionJob, job_id)
        if job is None:
            raise ApiError(404, "INGESTION_JOB_NOT_FOUND", "The requested ingestion job was not found.", "Not found")

        work_key = _work_key(job.job_id, key)
        existing = _existing_recovery(
            db,
            job=job,
            work_key=work_key,
            idempotency_key=key,
        )
        if existing is not None:
            result = IngestionRetryResponse(ingestion_job=_api_job(db, job), run=_api_run(existing))
            db.commit()
            return result

        previous_run = _latest_run(db, job.job_id)
        eligibility = _eligibility_for_run(db, previous_run)
        if not eligibility.eligible or previous_run is None:
            raise ApiError(
                409,
                "retry_not_eligible",
                "This ingestion work is not eligible for recovery.",
                "Retry not eligible",
                retry_eligibility=eligibility.model_dump(),
            )

        now = _next_run_time(previous_run.created_at)
        new_run = BackgroundJob(
            background_job_id=f"bgj_{uuid.uuid4().hex}",
            job_type="INGESTION",
            work_key=work_key,
            ingestion_job_id=job.job_id,
            status="QUEUED",
            attempt_count=0,
            max_attempts=INGESTION_MAX_ATTEMPTS,
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
        db.add(new_run)
        db.flush()
        before = {
            "run_id": previous_run.background_job_id,
            "status": previous_run.status,
            "attempt_count": previous_run.attempt_count,
            "max_attempts": previous_run.max_attempts,
        }
        after = {
            "run_id": new_run.background_job_id,
            "status": new_run.status,
            "attempt_count": new_run.attempt_count,
            "max_attempts": new_run.max_attempts,
            "idempotency_key": key,
        }
        safe_audit(
            db,
            action="INGESTION_RECOVERY",
            resource_type="INGESTION_JOB",
            resource_id=job.job_id,
            actor_user_id=context.user.user_id,
            before=before,
            after=after,
            request_id_value=request_id(request),
        )
        job.status = "QUEUED"
        job.started_at = None
        job.completed_at = None
        job.last_error_code = None
        result = IngestionRetryResponse(ingestion_job=_api_job(db, job), run=_api_run(new_run))
        db.commit()
        return result
    except ApiError:
        if db.in_transaction():
            db.rollback()
        raise
    except IntegrityError as error:
        if db.in_transaction():
            db.rollback()
        raise ApiError(409, "INGESTION_RECOVERY_CONFLICT", "The recovery request conflicts with current job state.", "Conflict") from error
    except Exception:
        if db.in_transaction():
            db.rollback()
        raise
