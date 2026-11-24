from __future__ import annotations

import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy import column, func, insert, select, table, text, tuple_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from productpulse.api_common import ApiError, validate_idempotency_key
from productpulse.api_common import safe_audit
from productpulse.api_schemas import (
    ConfirmPreviewRequest,
    IngestionJobCounts,
    IngestionJobResponse,
    RetryEligibility,
)
from productpulse.auth_api import AuthContext, _check_session_csrf, get_admin_context
from productpulse.ingestion.artifacts import ArtifactIntegrityError, ArtifactStore
from productpulse.ingestion.reference_imports import REFERENCE_KINDS, assert_reference_preview_current, persist_reference_rows
from productpulse.models import (
    BackgroundJob, Batch, CsvUpload, Feedback, IngestionJob, Product, Supplier, UploadPreview, UploadPreviewRow,
)
from productpulse.security.sessions import utc_text
from productpulse.settings import get_settings


router = APIRouter()
_IMPORT_LOG = logging.getLogger("productpulse.security.ingestion")
INGESTION_CHUNK_SIZE = 500
_SQLITE_LOOKUP_CHUNK = 250
CLASSIFICATION_MAX_ATTEMPTS = 3
_FEEDBACK_IDENTITIES = table("feedback", column("source_type"), column("source_record_id"))


def _api_job(job: IngestionJob) -> IngestionJobResponse:
    return IngestionJobResponse(
        job_id=job.job_id,
        preview_id=job.preview_id,
        idempotency_key=job.idempotency_key,
        processing_mode=job.processing_mode,
        status=job.status,
        counts=IngestionJobCounts(
            total_rows=job.total_row_count,
            accepted_rows=job.accepted_row_count,
            rejected_rows=job.rejected_row_count,
            duplicate_noop_rows=job.duplicate_row_count,
            conflict_rows=job.conflict_row_count,
            persisted_feedback=job.persisted_feedback_count,
        ),
        retry_eligibility=RetryEligibility(eligible=False, reason_code="NOT_FAILED"),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        last_error_code=job.last_error_code,
    )


def _preview_not_found() -> ApiError:
    return ApiError(404, "PREVIEW_NOT_FOUND", "The requested preview was not found.", "Not found")


def _load_preview_rows(db: Session, preview_id: str, *, offset: int, limit: int) -> list[UploadPreviewRow]:
    return db.scalars(
        select(UploadPreviewRow)
        .where(UploadPreviewRow.preview_id == preview_id, UploadPreviewRow.row_status == "ACCEPTED")
        .order_by(UploadPreviewRow.row_number)
        .offset(offset)
        .limit(limit)
    ).all()


def _validated_source_row(upload: CsvUpload, row: UploadPreviewRow) -> dict[str, object]:
    if not row.normalized_row_text or not row.row_payload_sha256 or not row.source_type or not row.source_record_id:
        raise ApiError(503, "PREVIEW_DATA_INVALID", "The saved preview cannot be imported safely.", "Request failed")
    actual_hash = hashlib.sha256(row.normalized_row_text.encode("utf-8")).hexdigest()
    if actual_hash != row.row_payload_sha256:
        raise ApiError(503, "PREVIEW_DATA_INVALID", "The saved preview cannot be imported safely.", "Request failed")
    try:
        values = json.loads(row.normalized_row_text)
    except (json.JSONDecodeError, TypeError) as error:
        raise ApiError(503, "PREVIEW_DATA_INVALID", "The saved preview cannot be imported safely.", "Request failed") from error
    if not isinstance(values, dict):
        raise ApiError(503, "PREVIEW_DATA_INVALID", "The saved preview cannot be imported safely.", "Request failed")
    identity_field = "review_id" if upload.upload_kind == "REVIEWS" else "return_id"
    event_field = "review_timestamp" if upload.upload_kind == "REVIEWS" else "return_timestamp"
    text_field = "review_text" if upload.upload_kind == "REVIEWS" else "return_reason"
    source_type = "REVIEW" if upload.upload_kind == "REVIEWS" else "RETURN"
    if (
        values.get(identity_field) != row.source_record_id
        or row.source_type != source_type
        or not isinstance(values.get("product_id"), str)
        or not isinstance(values.get(event_field), str)
        or not isinstance(values.get(text_field), str)
    ):
        raise ApiError(503, "PREVIEW_DATA_INVALID", "The saved preview cannot be imported safely.", "Request failed")
    return {
        "row_number": row.row_number,
        "source_type": source_type,
        "source_record_id": row.source_record_id,
        "product_id": values["product_id"],
        "reported_supplier_id": values.get("supplier_id"),
        "reported_batch_id": values.get("batch_id"),
        "event_time_utc": values[event_field],
        "feedback_text": values[text_field],
        "rating": values.get("rating") if upload.upload_kind == "REVIEWS" else None,
        "source_label": values.get("source") if upload.upload_kind == "REVIEWS" else None,
        "return_quantity": values.get("return_quantity") if upload.upload_kind == "RETURNS" else None,
        "return_category": values.get("return_category") if upload.upload_kind == "RETURNS" else None,
        "payload_sha256": row.row_payload_sha256,
    }


def _assert_no_stale_source_rows(db: Session, preview_id: str, accepted_count: int) -> None:
    for offset in range(0, accepted_count, _SQLITE_LOOKUP_CHUNK):
        rows = _load_preview_rows(db, preview_id, offset=offset, limit=_SQLITE_LOOKUP_CHUNK)
        identities = [(row.source_type, row.source_record_id) for row in rows if row.source_type and row.source_record_id]
        for identity_offset in range(0, len(identities), _SQLITE_LOOKUP_CHUNK):
            batch = identities[identity_offset : identity_offset + _SQLITE_LOOKUP_CHUNK]
            if not batch:
                continue
            existing = db.execute(
                select(_FEEDBACK_IDENTITIES.c.source_type, _FEEDBACK_IDENTITIES.c.source_record_id)
                .where(tuple_(_FEEDBACK_IDENTITIES.c.source_type, _FEEDBACK_IDENTITIES.c.source_record_id).in_(batch))
            ).first()
            if existing is not None:
                raise ApiError(
                    409,
                    "PREVIEW_STALE",
                    "Source records changed after this preview. Create a fresh preview and review its outcomes.",
                    "Conflict",
                )


def _assert_preview_counts(db: Session, preview: UploadPreview) -> None:
    actual = dict(db.execute(
        select(UploadPreviewRow.row_status, func.count())
        .where(UploadPreviewRow.preview_id == preview.preview_id)
        .group_by(UploadPreviewRow.row_status)
    ).all())
    expected = {
        "ACCEPTED": preview.accepted_row_count,
        "REJECTED": preview.rejected_row_count,
        "DUPLICATE_NOOP": preview.duplicate_row_count,
        "CONFLICT": preview.conflict_row_count,
    }
    if any(actual.get(status, 0) != count for status, count in expected.items()) or sum(actual.values()) != preview.total_row_count:
        raise ApiError(503, "PREVIEW_DATA_INVALID", "The saved preview cannot be imported safely.", "Request failed")


def _resolve_links(db: Session, rows: list[dict[str, object]]) -> dict[tuple[str, str | None, str | None], tuple[str | None, str | None, str]]:
    supplier_ids = {str(row["reported_supplier_id"]) for row in rows if row["reported_supplier_id"]}
    suppliers = set()
    if supplier_ids:
        supplier_list = sorted(supplier_ids)
        for offset in range(0, len(supplier_list), _SQLITE_LOOKUP_CHUNK):
            batch = supplier_list[offset : offset + _SQLITE_LOOKUP_CHUNK]
            suppliers.update(db.scalars(select(Supplier.supplier_id).where(Supplier.supplier_id.in_(batch))).all())

    batch_candidates = {
        (str(row["reported_batch_id"]), str(row["product_id"]), str(row["reported_supplier_id"]))
        for row in rows
        if row["reported_batch_id"] and row["reported_supplier_id"] in suppliers
    }
    resolved_batches: set[tuple[str, str, str]] = set()
    batch_list = list(batch_candidates)
    for offset in range(0, len(batch_list), _SQLITE_LOOKUP_CHUNK):
        batch = batch_list[offset : offset + _SQLITE_LOOKUP_CHUNK]
        resolved_batches.update(db.execute(
            select(Batch.batch_id, Batch.product_id, Batch.supplier_id).where(
                tuple_(Batch.batch_id, Batch.product_id, Batch.supplier_id).in_(batch)
            )
        ).all())

    result = {}
    for row in rows:
        product_id = str(row["product_id"])
        reported_supplier = row["reported_supplier_id"]
        reported_batch = row["reported_batch_id"]
        supplier_id = str(reported_supplier) if reported_supplier and str(reported_supplier) in suppliers else None
        batch_key = (str(reported_batch), product_id, supplier_id) if reported_batch and supplier_id else None
        batch_id = str(reported_batch) if batch_key and batch_key in resolved_batches else None
        status = "LINKED" if supplier_id is not None and batch_id is not None else "LINKAGE_PENDING"
        result[(product_id, str(reported_supplier) if reported_supplier else None, str(reported_batch) if reported_batch else None)] = (
            supplier_id,
            batch_id,
            status,
        )
    return result


def _persist_feedback_chunks(db: Session, preview: UploadPreview, upload: CsvUpload, job: IngestionJob, now: str) -> int:
    persisted = 0
    for offset in range(0, preview.accepted_row_count, INGESTION_CHUNK_SIZE):
        preview_rows = _load_preview_rows(db, preview.preview_id, offset=offset, limit=INGESTION_CHUNK_SIZE)
        parsed_rows = [_validated_source_row(upload, row) for row in preview_rows]
        product_values = list({
            str(row["product_id"]): {
                "product_id": str(row["product_id"]),
                "created_at": now,
                "updated_at": now,
            }
            for row in parsed_rows
        }.values())
        if product_values:
            db.execute(
                sqlite_insert(Product).on_conflict_do_nothing(index_elements=[Product.product_id]),
                product_values,
            )
        links = _resolve_links(db, parsed_rows)
        feedback_rows = []
        for row in parsed_rows:
            product_id = str(row["product_id"])
            reported_supplier = str(row["reported_supplier_id"]) if row["reported_supplier_id"] else None
            reported_batch = str(row["reported_batch_id"]) if row["reported_batch_id"] else None
            supplier_id, batch_id, linkage_status = links[(product_id, reported_supplier, reported_batch)]
            feedback_rows.append({
                "feedback_id": f"fdb_{uuid.uuid4().hex}",
                "source_type": row["source_type"],
                "source_record_id": row["source_record_id"],
                "product_id": product_id,
                "supplier_id": supplier_id,
                "batch_id": batch_id,
                "reported_supplier_id": reported_supplier,
                "reported_batch_id": reported_batch,
                "linkage_status": linkage_status,
                "event_time_utc": row["event_time_utc"],
                "feedback_text": row["feedback_text"],
                "rating": row["rating"],
                "source_label": row["source_label"],
                "return_quantity": row["return_quantity"],
                "return_category": row["return_category"],
                "payload_sha256": row["payload_sha256"],
                "record_origin": "CSV_UPLOAD",
                "ingestion_job_id": job.job_id,
                "origin_preview_id": preview.preview_id,
                "origin_row_number": row["row_number"],
                "origin_manifest_ref": None,
                "ingested_at": now,
            })
        if feedback_rows:
            db.execute(insert(Feedback), feedback_rows)
            persisted += len(feedback_rows)
    return persisted


def _create_classification_queue_item(db: Session, ingestion_job: IngestionJob, now: str) -> BackgroundJob:
    background_job = BackgroundJob(
        background_job_id=f"bgj_{uuid.uuid4().hex}",
        job_type="CLASSIFICATION",
        work_key=f"classification:{ingestion_job.job_id}",
        ingestion_job_id=ingestion_job.job_id,
        status="QUEUED",
        attempt_count=0,
        max_attempts=CLASSIFICATION_MAX_ATTEMPTS,
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
    db.add(background_job)
    db.flush()
    return background_job


def _assert_classification_queue_exists(db: Session, ingestion_job: IngestionJob) -> None:
    queued = db.scalar(select(BackgroundJob).where(
        BackgroundJob.ingestion_job_id == ingestion_job.job_id,
        BackgroundJob.job_type == "CLASSIFICATION",
    ))
    if queued is None or queued.work_key != f"classification:{ingestion_job.job_id}" or queued.max_attempts != CLASSIFICATION_MAX_ATTEMPTS:
        raise ApiError(503, "IMPORT_QUEUE_INCONSISTENT", "The import queue state is temporarily unavailable.", "Request failed")


@router.post(
    "/admin/ingestion/previews/{preview_id}/confirm",
    response_model=IngestionJobResponse,
    status_code=202,
)
def confirm_ingestion_preview(
    preview_id: str,
    body: ConfirmPreviewRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
) -> IngestionJobResponse:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    db = context.db
    preview = db.get(UploadPreview, preview_id)
    if preview is None:
        raise _preview_not_found()
    upload = db.get(CsvUpload, preview.upload_id)
    if upload is None:
        db.rollback()
        raise ApiError(503, "PREVIEW_UNAVAILABLE", "The saved preview is temporarily unavailable.", "Request failed")
    is_feedback = upload.upload_kind in {"REVIEWS", "RETURNS"}
    mode_supplied = "processing_mode" in body.model_fields_set
    if is_feedback and (not mode_supplied or body.processing_mode is None):
        db.rollback()
        raise ApiError(422, "PROCESSING_MODE_REQUIRED", "Choose a processing mode for this feedback import.", "Validation failed")
    if not is_feedback and mode_supplied:
        db.rollback()
        raise ApiError(422, "PROCESSING_MODE_NOT_ALLOWED", "Reference imports do not use a feedback processing mode.", "Validation failed")
    if not is_feedback and upload.upload_kind not in REFERENCE_KINDS:
        db.rollback()
        raise ApiError(422, "REFERENCE_CONFIRMATION_UNSUPPORTED", "This reference import type is not supported.", "Validation failed")
    if body.verified_sha256 != preview.verified_sha256 or body.verified_sha256 != upload.file_sha256:
        db.rollback()
        raise ApiError(409, "PREVIEW_HASH_MISMATCH", "The supplied hash does not match the immutable preview.", "Conflict")

    # The first read identifies the row; refresh all mutable confirmation state after taking SQLite's writer lock.
    db.rollback()
    artifact_store = ArtifactStore(context.request.app.state.settings or get_settings())
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        preview = db.scalar(
            select(UploadPreview).where(UploadPreview.preview_id == preview_id).execution_options(populate_existing=True)
        )
        if preview is None:
            raise _preview_not_found()
        upload = db.get(CsvUpload, preview.upload_id, populate_existing=True)
        if upload is None:
            raise ApiError(503, "PREVIEW_UNAVAILABLE", "The saved preview is temporarily unavailable.", "Request failed")
        if body.verified_sha256 != preview.verified_sha256 or body.verified_sha256 != upload.file_sha256:
            raise ApiError(409, "PREVIEW_HASH_MISMATCH", "The supplied hash does not match the immutable preview.", "Conflict")
        try:
            artifact_store.verified_path(upload.artifact_id, body.verified_sha256)
        except ArtifactIntegrityError as error:
            raise ApiError(503, "ARTIFACT_INTEGRITY_ERROR", "The protected upload is unavailable or failed its integrity check.", "Request failed") from error

        keyed_job = db.scalar(select(IngestionJob).where(IngestionJob.idempotency_key == key))
        if keyed_job is not None:
            if keyed_job.preview_id != preview_id or keyed_job.processing_mode != body.processing_mode:
                raise ApiError(409, "IDEMPOTENCY_CONFLICT", "The Idempotency-Key was already used for a different confirmation.", "Conflict")
            if is_feedback:
                _assert_classification_queue_exists(db, keyed_job)
            db.commit()
            return _api_job(keyed_job)

        existing_job = db.scalar(select(IngestionJob).where(IngestionJob.preview_id == preview_id))
        if existing_job is not None:
            if existing_job.processing_mode != body.processing_mode:
                raise ApiError(409, "PROCESSING_MODE_CONFLICT", "This preview was already confirmed with a different processing mode.", "Conflict")
            if is_feedback:
                _assert_classification_queue_exists(db, existing_job)
            db.commit()
            return _api_job(existing_job)

        if preview.state != "READY" or preview.accepted_row_count < 1:
            raise ApiError(409, "PREVIEW_NOT_CONFIRMABLE", "Only a READY preview with eligible feedback rows can be confirmed.", "Conflict")
        _assert_preview_counts(db, preview)
        if is_feedback:
            _assert_no_stale_source_rows(db, preview_id, preview.accepted_row_count)
        elif not assert_reference_preview_current(db, upload.upload_kind, preview_id):
            raise ApiError(
                409,
                "PREVIEW_STALE",
                "Reference mappings changed after this preview. Create a fresh preview and review its outcomes.",
                "Conflict",
            )

        now = utc_text()
        job = IngestionJob(
            job_id=f"ing_{uuid.uuid4().hex}",
            preview_id=preview_id,
            idempotency_key=key,
            processing_mode=body.processing_mode,
            status="QUEUED" if is_feedback else "RUNNING",
            total_row_count=preview.total_row_count,
            accepted_row_count=preview.accepted_row_count,
            rejected_row_count=preview.rejected_row_count,
            duplicate_row_count=preview.duplicate_row_count,
            conflict_row_count=preview.conflict_row_count,
            persisted_feedback_count=0,
            created_at=now,
            started_at=None if is_feedback else now,
            completed_at=None,
            last_error_code=None,
        )
        db.add(job)
        db.flush()
        if is_feedback:
            persisted = _persist_feedback_chunks(db, preview, upload, job, now)
            if persisted != preview.accepted_row_count:
                raise ApiError(503, "IMPORT_COUNT_MISMATCH", "The preview rows could not be imported consistently.", "Request failed")
            job.persisted_feedback_count = persisted
            _create_classification_queue_item(db, job, now)
        else:
            imported = persist_reference_rows(db, preview, upload, now)
            if imported != preview.accepted_row_count:
                raise ApiError(503, "IMPORT_COUNT_MISMATCH", "The reference rows could not be imported consistently.", "Request failed")
            job.status = "COMPLETED"
            job.completed_at = now
            safe_audit(
                db,
                action="REFERENCE_IMPORT_CONFIRMED",
                resource_type="INGESTION_JOB",
                resource_id=job.job_id,
                actor_user_id=context.user.user_id,
                after={"upload_kind": upload.upload_kind, "preview_id": preview_id, "accepted_rows": imported},
                request_id_value=getattr(context.request.state, "request_id", None),
            )
        db.execute(
            update(UploadPreview)
            .where(UploadPreview.preview_id == preview_id)
            .values(state="CONFIRMED", confirmed_by=context.user.user_id, confirmed_at=now)
        )
        db.commit()
        return _api_job(job)
    except ApiError:
        if db.in_transaction():
            db.rollback()
        raise
    except IntegrityError as error:
        if db.in_transaction():
            db.rollback()
        reason = str(error.orig)
        safe_reason = reason[:160] if reason.startswith((
            "UNIQUE constraint failed:",
            "NOT NULL constraint failed:",
            "CHECK constraint failed:",
            "FOREIGN KEY constraint failed",
        )) else "database constraint"
        _IMPORT_LOG.error("event=INGESTION_CONFIRM_INTEGRITY_FAILED preview_id=%s constraint=%s", preview_id, safe_reason)
        raise ApiError(503, "INGESTION_CONFIRM_FAILED", "The import could not be confirmed. Try again.", "Request failed") from error
    except Exception as error:
        if db.in_transaction():
            db.rollback()
        _IMPORT_LOG.error("event=INGESTION_CONFIRM_FAILED preview_id=%s", preview_id)
        raise ApiError(503, "INGESTION_CONFIRM_FAILED", "The import could not be confirmed. Try again.", "Request failed") from error
