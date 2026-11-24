"""Admin-only API for explicit source-payload and reference-mapping decisions."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from productpulse.api_common import ApiError, page_meta, request_id, safe_audit, validate_idempotency_key
from productpulse.api_schemas import (
    ConflictKind,
    ConflictState,
    IngestionConflictPage,
    IngestionConflictResponse,
    ResolveConflictRequest,
)
from productpulse.auth_api import AuthContext, _check_session_csrf, get_admin_context
from productpulse.ingestion.reference_imports import (
    REFERENCE_KINDS,
    _hash as mapping_hash,
    _lookup as lookup_reference,
    _stored_mapping as stored_mapping,
    _values as reference_values,
)
from productpulse.models import (
    AuditEvent,
    Batch,
    CsvUpload,
    Feedback,
    IngestionConflict,
    Product,
    Supplier,
    UploadPreview,
    UploadPreviewRow,
)
from productpulse.security.sessions import utc_text


router = APIRouter()
_SOURCE_KINDS = {"REVIEWS", "RETURNS"}


def _iso_bound(value: datetime | None, name: str) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ApiError(422, "VALIDATION_ERROR", f"{name} must include a timezone.", "Validation failed")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _context(db, conflict: IngestionConflict):
    preview = db.get(UploadPreview, conflict.preview_id)
    if preview is None:
        raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved conflict preview is unavailable.", "Conflict")
    upload = db.get(CsvUpload, preview.upload_id)
    row = db.get(UploadPreviewRow, (conflict.preview_id, conflict.row_number))
    if upload is None or row is None or row.row_status != "CONFLICT" or row.normalized_row_text is None:
        raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved conflict preview row is unavailable.", "Conflict")
    digest = hashlib.sha256(row.normalized_row_text.encode("utf-8")).hexdigest()
    if row.row_payload_sha256 != digest or conflict.incoming_value_hash != digest:
        raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved conflict preview row failed integrity validation.", "Conflict")
    try:
        payload = json.loads(row.normalized_row_text)
    except (json.JSONDecodeError, TypeError) as error:
        raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved conflict preview row is invalid.", "Conflict") from error
    if not isinstance(payload, dict):
        raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved conflict preview row is invalid.", "Conflict")
    if conflict.conflict_kind == "SOURCE_PAYLOAD":
        expected_source_type = "REVIEW" if upload.upload_kind == "REVIEWS" else "RETURN"
        if (
            upload.upload_kind not in _SOURCE_KINDS
            or row.source_type != expected_source_type
            or row.source_type != conflict.source_type
            or row.source_record_id != conflict.source_record_id
        ):
            raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved source conflict provenance is inconsistent.", "Conflict")
    elif conflict.conflict_kind == "REFERENCE_MAPPING":
        if upload.upload_kind not in REFERENCE_KINDS:
            raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved reference conflict provenance is inconsistent.", "Conflict")
        try:
            values = reference_values(upload.upload_kind, payload)
        except (KeyError, TypeError) as error:
            raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved reference conflict is invalid.", "Conflict") from error
        id_field = "product_id" if upload.upload_kind == "PRODUCT_REFERENCE" else "supplier_id" if upload.upload_kind == "SUPPLIER_REFERENCE" else "batch_id"
        if conflict.mapping_key != f"{upload.upload_kind}:{values[id_field]}":
            raise ApiError(409, "CONFLICT_PREVIEW_INVALID", "The saved reference conflict provenance is inconsistent.", "Conflict")
    else:
        raise ApiError(409, "CONFLICT_INVALID", "The saved conflict type is invalid.", "Conflict")
    return preview, upload, row, payload


def _current_existing_hash(db, conflict: IngestionConflict) -> str | None:
    _preview, upload, _row, payload = _context(db, conflict)
    if conflict.conflict_kind == "SOURCE_PAYLOAD":
        source = db.get(Feedback, conflict.existing_feedback_id) if conflict.existing_feedback_id else None
        if source is None and conflict.source_type and conflict.source_record_id:
            source = db.scalar(select(Feedback).where(
                Feedback.source_type == conflict.source_type,
                Feedback.source_record_id == conflict.source_record_id,
            ))
        return source.payload_sha256 if source is not None else conflict.existing_value_hash
    values = reference_values(upload.upload_kind, payload)
    existing = lookup_reference(db, upload.upload_kind, values)
    current = stored_mapping(upload.upload_kind, existing)
    return mapping_hash(current) if current is not None else conflict.existing_value_hash


def _response(db, conflict: IngestionConflict) -> IngestionConflictResponse:
    return IngestionConflictResponse(
        conflict_id=conflict.conflict_id,
        preview_id=conflict.preview_id,
        row_number=conflict.row_number,
        conflict_kind=conflict.conflict_kind,
        existing_feedback_id=conflict.existing_feedback_id,
        source_type=conflict.source_type,
        source_record_id=conflict.source_record_id,
        existing_value_hash=_current_existing_hash(db, conflict),
        incoming_value_hash=conflict.incoming_value_hash,
        mapping_key=conflict.mapping_key,
        state=conflict.state,
        resolution_note=conflict.resolution_note,
        created_at=conflict.created_at,
        resolved_by=conflict.resolved_by,
        resolved_at=conflict.resolved_at,
    )


def _request_fingerprint(body: ResolveConflictRequest) -> str:
    serialized = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _replay(db, conflict_id: str, key_hash: str, fingerprint: str) -> IngestionConflictResponse | None:
    audits = db.scalars(select(AuditEvent).where(
        AuditEvent.action == "INGESTION_CONFLICT_RESOLVED",
        AuditEvent.resource_type == "INGESTION_CONFLICT",
        AuditEvent.resource_id == conflict_id,
    ).order_by(AuditEvent.created_at.desc(), AuditEvent.audit_event_id.desc())).all()
    for audit in audits:
        try:
            after = json.loads(audit.after_state_text or "{}")
        except (json.JSONDecodeError, TypeError):
            after = {}
        if after.get("idempotency_key_sha256") != key_hash:
            continue
        if after.get("request_fingerprint") != fingerprint:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "The Idempotency-Key was already used for a different conflict decision.", "Conflict")
        conflict = db.get(IngestionConflict, conflict_id)
        if conflict is None:
            raise ApiError(404, "CONFLICT_NOT_FOUND", "The requested conflict was not found.", "Not found")
        return _response(db, conflict)
    return None


def _apply_reference(db, upload_kind: str, payload: dict[str, object], conflict: IngestionConflict, body: ResolveConflictRequest) -> dict[str, object]:
    values = reference_values(upload_kind, payload)
    existing = lookup_reference(db, upload_kind, values)
    current_mapping = stored_mapping(upload_kind, existing)
    if existing is None or current_mapping is None:
        raise ApiError(409, "CONFLICT_STATE_CHANGED", "The reference mapping no longer exists. Reload the conflict before resolving it.", "Conflict")
    current_hash = mapping_hash(current_mapping)
    if body.expected_existing_value_hash is None:
        raise ApiError(422, "EXPECTED_HASH_REQUIRED", "The current mapping hash is required to apply an incoming reference.", "Validation failed")
    if body.expected_existing_value_hash != current_hash or (
        conflict.existing_value_hash is not None and conflict.existing_value_hash != current_hash
    ):
        raise ApiError(409, "STALE_REFERENCE_MAPPING", "The reference mapping changed. Reload the conflict before applying it.", "Conflict")

    before = dict(current_mapping)
    if upload_kind == "PRODUCT_REFERENCE":
        if values.get("name") is not None:
            existing.name = values["name"]
        if values.get("category") is not None:
            existing.category = values["category"]
        existing.updated_at = utc_text()
    elif upload_kind == "SUPPLIER_REFERENCE":
        if values.get("name") is not None:
            existing.name = values["name"]
        existing.updated_at = utc_text()
    else:
        product = db.get(Product, str(values["product_id"]))
        supplier = db.get(Supplier, str(values["supplier_id"]))
        if product is None or supplier is None:
            raise ApiError(422, "REFERENCE_DEPENDENCY_MISSING", "The referenced product and supplier must exist before applying this mapping.", "Validation failed")
        conflicting_feedback = db.scalar(select(func.count()).select_from(Feedback).where(
            Feedback.batch_id == existing.batch_id,
            or_(Feedback.product_id != product.product_id, Feedback.supplier_id != supplier.supplier_id),
        ))
        if conflicting_feedback:
            raise ApiError(409, "REFERENCE_MAPPING_IN_USE", "The batch mapping is in use by feedback with different exact links.", "Conflict")
        existing.product_id = product.product_id
        existing.supplier_id = supplier.supplier_id
        existing.updated_at = utc_text()
    db.flush()
    after = stored_mapping(upload_kind, existing)
    return {
        "before": before,
        "after": after,
        "before_hash": current_hash,
        "after_hash": mapping_hash(after),
    }


@router.get("/admin/reconciliation/conflicts", response_model=IngestionConflictPage, tags=["Reconciliation"])
def list_conflicts(
    conflict_kind: ConflictKind | None = Query(default=None),
    state: ConflictState = Query(default="PENDING"),
    from_utc: datetime | None = Query(default=None, alias="from_utc"),
    to_utc: datetime | None = Query(default=None, alias="to_utc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    context: AuthContext = Depends(get_admin_context),
) -> IngestionConflictPage:
    db = context.db
    statement = select(IngestionConflict).where(IngestionConflict.state == state)
    count_statement = select(func.count()).select_from(IngestionConflict).where(IngestionConflict.state == state)
    if conflict_kind is not None:
        statement = statement.where(IngestionConflict.conflict_kind == conflict_kind)
        count_statement = count_statement.where(IngestionConflict.conflict_kind == conflict_kind)
    start = _iso_bound(from_utc, "from_utc")
    end = _iso_bound(to_utc, "to_utc")
    if start is not None:
        statement = statement.where(IngestionConflict.created_at >= start)
        count_statement = count_statement.where(IngestionConflict.created_at >= start)
    if end is not None:
        statement = statement.where(IngestionConflict.created_at <= end)
        count_statement = count_statement.where(IngestionConflict.created_at <= end)
    if start is not None and end is not None and start > end:
        raise ApiError(422, "VALIDATION_ERROR", "from_utc must not be later than to_utc.", "Validation failed")
    total = int(db.scalar(count_statement) or 0)
    conflicts = db.scalars(statement.order_by(IngestionConflict.created_at.desc(), IngestionConflict.conflict_id.desc())
                           .offset((page - 1) * page_size).limit(page_size)).all()
    return IngestionConflictPage(
        items=[_response(db, conflict) for conflict in conflicts],
        page=page_meta(page, page_size, total),
    )


@router.get(
    "/admin/reconciliation/conflicts/{conflict_id}",
    response_model=IngestionConflictResponse,
    tags=["Reconciliation"],
)
def get_conflict(
    conflict_id: str = Path(min_length=1, max_length=36),
    context: AuthContext = Depends(get_admin_context),
) -> IngestionConflictResponse:
    conflict = context.db.get(IngestionConflict, conflict_id)
    if conflict is None:
        raise ApiError(404, "CONFLICT_NOT_FOUND", "The requested conflict was not found.", "Not found")
    return _response(context.db, conflict)


@router.post(
    "/admin/reconciliation/conflicts/{conflict_id}/resolve",
    response_model=IngestionConflictResponse,
    tags=["Reconciliation"],
)
def resolve_conflict(
    conflict_id: str = Path(min_length=1, max_length=36),
    body: ResolveConflictRequest = ...,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
) -> IngestionConflictResponse:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    fingerprint = _request_fingerprint(body)
    db = context.db
    db.rollback()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        replay = _replay(db, conflict_id, key_hash, fingerprint)
        if replay is not None:
            db.commit()
            return replay
        conflict = db.get(IngestionConflict, conflict_id)
        if conflict is None:
            raise ApiError(404, "CONFLICT_NOT_FOUND", "The requested conflict was not found.", "Not found")
        if conflict.state != "PENDING":
            raise ApiError(409, "CONFLICT_ALREADY_RESOLVED", "The conflict has already been reviewed.", "Conflict")
        _preview, upload, row, payload = _context(db, conflict)

        mapping_audit: dict[str, object] | None = None
        if conflict.conflict_kind == "SOURCE_PAYLOAD":
            if body.decision == "APPLY_INCOMING_REFERENCE":
                raise ApiError(422, "DECISION_INVALID_FOR_CONFLICT", "Source payload conflicts cannot apply incoming text.", "Validation failed")
            current_source = None
            if conflict.source_type and conflict.source_record_id:
                current_source = db.scalar(select(Feedback).where(
                    Feedback.source_type == conflict.source_type,
                    Feedback.source_record_id == conflict.source_record_id,
                ))
            if conflict.existing_feedback_id and (
                current_source is None or current_source.feedback_id != conflict.existing_feedback_id
            ):
                raise ApiError(409, "CONFLICT_STATE_CHANGED", "The source identity changed. Reload the conflict before resolving it.", "Conflict")
            if (
                current_source is not None
                and conflict.existing_value_hash is not None
                and current_source.payload_sha256 != conflict.existing_value_hash
            ):
                raise ApiError(409, "CONFLICT_STATE_CHANGED", "The existing source payload changed. Reload the conflict before resolving it.", "Conflict")
            if body.expected_existing_value_hash is not None:
                raise ApiError(422, "DECISION_INVALID_FOR_CONFLICT", "An expected mapping hash is valid only for applying a reference mapping.", "Validation failed")
            before = {
                "state": conflict.state,
                "source_type": conflict.source_type,
                "source_record_id": conflict.source_record_id,
                "existing_feedback_id": current_source.feedback_id if current_source is not None else conflict.existing_feedback_id,
                "existing_payload_sha256": current_source.payload_sha256 if current_source is not None else conflict.existing_value_hash,
                "incoming_payload_sha256": conflict.incoming_value_hash,
                "source_payload_changed": False,
            }
        else:
            if body.decision == "APPLY_INCOMING_REFERENCE":
                mapping_audit = _apply_reference(db, upload.upload_kind, payload, conflict, body)
            elif body.expected_existing_value_hash is not None:
                raise ApiError(422, "DECISION_INVALID_FOR_CONFLICT", "An expected mapping hash is used only when applying an incoming reference.", "Validation failed")
            before = {
                "state": conflict.state,
                "preview_id": conflict.preview_id,
                "row_number": conflict.row_number,
                "mapping_key": conflict.mapping_key,
                "existing_value_hash": mapping_audit["before_hash"] if mapping_audit else _current_existing_hash(db, conflict),
                "incoming_value_hash": conflict.incoming_value_hash,
                "mapping": mapping_audit["before"] if mapping_audit else None,
            }

        now = utc_text()
        new_state = "DISMISSED" if body.decision == "DISMISS" else "RESOLVED"
        conflict.state = new_state
        conflict.resolution_note = body.resolution_note
        conflict.resolved_by = context.user.user_id
        conflict.resolved_at = now
        db.flush()
        after = {
            "state": new_state,
            "decision": body.decision,
            "resolution_note": body.resolution_note,
            "preview_id": conflict.preview_id,
            "row_number": conflict.row_number,
            "mapping_key": conflict.mapping_key,
            "mapping": mapping_audit["after"] if mapping_audit else before.get("mapping"),
            "source_type": conflict.source_type,
            "source_record_id": conflict.source_record_id,
            "existing_payload_sha256": before.get("existing_payload_sha256"),
            "incoming_payload_sha256": conflict.incoming_value_hash if conflict.conflict_kind == "SOURCE_PAYLOAD" else None,
            "mapping_value_hash": mapping_audit["after_hash"] if mapping_audit else before.get("existing_value_hash"),
            "expected_existing_value_hash": body.expected_existing_value_hash,
            "idempotency_key_sha256": key_hash,
            "request_fingerprint": fingerprint,
            "source_payload_changed": False,
        }
        safe_audit(
            db,
            action="INGESTION_CONFLICT_RESOLVED",
            resource_type="INGESTION_CONFLICT",
            resource_id=conflict.conflict_id,
            actor_user_id=context.user.user_id,
            before=before,
            after=after,
            request_id_value=request_id(context.request),
        )
        db.commit()
        return _response(db, conflict)
    except ApiError:
        if db.in_transaction():
            db.rollback()
        raise
    except IntegrityError as error:
        if db.in_transaction():
            db.rollback()
        raise ApiError(409, "CONFLICT_STATE_CHANGED", "The conflict or reference mapping changed while resolving it.", "Conflict") from error
    except OperationalError as error:
        if db.in_transaction():
            db.rollback()
        raise ApiError(503, "CONFLICT_UPDATE_FAILED", "The conflict could not be resolved. Try again.", "Request failed") from error
    except Exception as error:
        if db.in_transaction():
            db.rollback()
        raise ApiError(503, "CONFLICT_UPDATE_FAILED", "The conflict could not be resolved. Try again.", "Request failed") from error
