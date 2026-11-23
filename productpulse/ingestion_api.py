from __future__ import annotations

import hashlib
import json
import logging
import asyncio
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import column, func, insert, select, table, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from productpulse.api_common import ApiError, page_meta, validate_idempotency_key
from productpulse.api_schemas import (
    UploadColumnMapping,
    UploadKind,
    UploadPreviewCounts,
    UploadPreviewResponse,
    UploadPreviewRowPage,
    UploadPreviewRowResponse,
)
from productpulse.auth_api import AuthContext, _check_session_csrf, get_admin_context
from productpulse.db_session import get_db
from productpulse.ingestion.artifacts import ArtifactStore, StagedUpload
from productpulse.ingestion.parser import (
    MAX_FILE_BYTES,
    CsvInputError,
    PreviewParse,
    parse_preview,
    template_bytes,
)
from productpulse.models import CsvUpload, UploadPreview, UploadPreviewRow
from productpulse.security.sessions import utc_text
from productpulse.settings import get_settings


router = APIRouter()
_UPLOAD_LOG = logging.getLogger("productpulse.security.ingestion")
_MAPPING_FIELD_MAX_BYTES = MAX_FILE_BYTES
_SOURCE_LOOKUP_CHUNK = 250
_FEEDBACK_ROWS = table(
    "feedback",
    column("source_type"),
    column("source_record_id"),
    column("payload_sha256"),
)


class _BoundedMultiPartParser(MultiPartParser):
    """Reject an over-limit file part during multipart streaming."""

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._current_file_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._current_file_bytes += end - start
            if self._current_file_bytes > MAX_FILE_BYTES:
                raise CsvInputError(
                    "UPLOAD_TOO_LARGE",
                    "The file exceeds the 20,000,000-byte limit.",
                    status=413,
                )
        super().on_part_data(data, start, end)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _request_fingerprint(upload_kind: str, file_sha256: str, mappings: list[dict[str, object]]) -> str:
    payload = {
        "upload_kind": upload_kind,
        "file_sha256": file_sha256,
        "column_mappings": mappings,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _json_mapping(form: FormData) -> tuple[str, list[dict[str, object]], UploadFile]:
    kind_values = form.getlist("upload_kind")
    mapping_values = form.getlist("column_mappings")
    file_values = form.getlist("file")
    if len(kind_values) != 1 or len(mapping_values) != 1 or len(file_values) != 1:
        raise CsvInputError("UPLOAD_FORM_INVALID", "Provide one upload kind, mapping, and CSV file.")

    kind_value, mapping_value, file_value = kind_values[0], mapping_values[0], file_values[0]
    if not isinstance(kind_value, str) or kind_value not in {
        "REVIEWS", "RETURNS", "PRODUCT_REFERENCE", "SUPPLIER_REFERENCE", "BATCH_REFERENCE"
    }:
        raise CsvInputError("UPLOAD_KIND_INVALID", "Choose a supported CSV type.")
    if not isinstance(mapping_value, str):
        raise CsvInputError("MAPPING_INVALID", "The column mapping must be JSON text.")
    if not isinstance(file_value, UploadFile):
        raise CsvInputError("UPLOAD_FORM_INVALID", "Provide the CSV file as a file part.")
    filename = file_value.filename or ""
    if not filename.lower().endswith(".csv"):
        raise CsvInputError("FILE_EXTENSION_UNSUPPORTED", "Upload a file with the .csv extension.", status=415)
    try:
        decoded = json.loads(mapping_value)
        if not isinstance(decoded, list):
            raise ValueError
        mappings = [UploadColumnMapping.model_validate(item).model_dump() for item in decoded]
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
        raise CsvInputError("MAPPING_INVALID", "The column mapping is invalid.") from error
    return kind_value, mappings, file_value


async def _parse_form(request: Request) -> FormData:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Upload a multipart CSV form.", "Unsupported media type")
    parser = _BoundedMultiPartParser(
        request.headers,
        request.stream(),
        max_files=1,
        max_fields=2,
        max_part_size=_MAPPING_FIELD_MAX_BYTES,
    )
    try:
        return await parser.parse()
    except CsvInputError as error:
        raise ApiError(error.status, error.code, error.detail, "Upload validation failed") from error
    except MultiPartException as error:
        raise ApiError(422, "UPLOAD_FORM_INVALID", "The multipart upload is malformed.", "Upload validation failed") from error


def _parse_with_stored_conflicts(db: Session, artifact_path, kind: str, mappings: list[dict[str, object]]) -> PreviewParse:
    parsed = parse_preview(artifact_path, kind, mappings)
    candidates = sorted({
        (row.source_type, row.source_record_id)
        for row in parsed.rows
        if row.row_status == "ACCEPTED" and row.source_type and row.source_record_id
    })
    if not candidates or db.scalar(text("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")) is None:
        return parsed

    stored: dict[tuple[str, str], str] = {}
    for offset in range(0, len(candidates), _SOURCE_LOOKUP_CHUNK):
        batch = candidates[offset : offset + _SOURCE_LOOKUP_CHUNK]
        rows = db.execute(
            select(
                _FEEDBACK_ROWS.c.source_type,
                _FEEDBACK_ROWS.c.source_record_id,
                _FEEDBACK_ROWS.c.payload_sha256,
            ).where(tuple_(_FEEDBACK_ROWS.c.source_type, _FEEDBACK_ROWS.c.source_record_id).in_(batch))
        ).all()
        stored.update({(row[0], row[1]): row[2] for row in rows})
    return parse_preview(artifact_path, kind, mappings, stored)


def _preview_response(preview: UploadPreview, upload: CsvUpload) -> UploadPreviewResponse:
    return UploadPreviewResponse(
        preview_id=preview.preview_id,
        upload_id=upload.upload_id,
        upload_kind=upload.upload_kind,
        original_filename=upload.original_filename,
        file_size_bytes=upload.file_size_bytes,
        verified_sha256=preview.verified_sha256,
        parser_contract_version=preview.parser_contract_version,
        column_mappings=json.loads(preview.column_mappings_text),
        state=preview.state,
        counts=UploadPreviewCounts(
            total_rows=preview.total_row_count,
            accepted_rows=preview.accepted_row_count,
            rejected_rows=preview.rejected_row_count,
            duplicate_noop_rows=preview.duplicate_row_count,
            conflict_rows=preview.conflict_row_count,
        ),
        uploaded_by=upload.uploaded_by,
        created_at=preview.created_at,
        confirmed_by=preview.confirmed_by,
        confirmed_at=preview.confirmed_at,
    )


def _missing_preview() -> ApiError:
    return ApiError(404, "PREVIEW_NOT_FOUND", "The requested preview was not found.", "Not found")


def _is_artifact_referenced(db: Session, artifact_id: str) -> bool | None:
    try:
        db.rollback()
        return db.scalar(select(CsvUpload.upload_id).where(CsvUpload.artifact_id == artifact_id)) is not None
    except Exception:
        db.rollback()
        return None


@router.get("/admin/ingestion/templates/{upload_kind}")
def download_ingestion_template(
    upload_kind: UploadKind,
    context: AuthContext = Depends(get_admin_context),
) -> Response:
    del context
    try:
        content = template_bytes(upload_kind)
    except CsvInputError as error:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "The requested template was not found.", "Not found") from error
    digest = hashlib.sha256(content).hexdigest()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{upload_kind.lower()}_template.csv"',
            "X-Content-SHA256": digest,
        },
    )


@router.post(
    "/admin/ingestion/previews",
    response_model=UploadPreviewResponse,
    response_model_exclude_none=True,
    status_code=201,
)
async def create_ingestion_preview(
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
    db: Session = Depends(get_db),
) -> UploadPreviewResponse:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    form = await _parse_form(request)
    staged: StagedUpload | None = None
    published_artifact_id: str | None = None
    store = ArtifactStore(context.request.app.state.settings or get_settings())
    try:
        kind, mappings, upload_file = _json_mapping(form)
        staged = await asyncio.to_thread(store.stage, upload_file.file, upload_file.filename)
        if not staged.filename.lower().endswith(".csv"):
            raise CsvInputError("FILE_EXTENSION_UNSUPPORTED", "Upload a file with the .csv extension.", status=415)
        parsed = await asyncio.to_thread(
            _parse_with_stored_conflicts,
            db,
            staged.temporary_path,
            kind,
            mappings,
        )
        db.rollback()
        canonical_mappings = [dict(item) for item in parsed.mappings]
        fingerprint = _request_fingerprint(kind, staged.sha256, canonical_mappings)
        db.execute(text("BEGIN IMMEDIATE"))
        referenced_ids = set(db.scalars(select(CsvUpload.artifact_id)).all())
        store.reconcile_unreferenced(referenced_ids)
        previous = db.scalar(
            select(UploadPreview).where(UploadPreview.preview_idempotency_key == key)
        )
        if previous is not None:
            upload = db.get(CsvUpload, previous.upload_id)
            if upload is None:
                db.rollback()
                raise ApiError(503, "PREVIEW_UNAVAILABLE", "The saved preview is temporarily unavailable.", "Request failed")
            if previous.preview_request_sha256 != fingerprint:
                db.rollback()
                raise ApiError(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "The Idempotency-Key was already used for a different preview request.",
                    "Conflict",
                )
            db.commit()
            response.status_code = 200
            return _preview_response(previous, upload)

        upload_id = f"upl_{uuid.uuid4().hex}"
        preview_id = f"prv_{uuid.uuid4().hex}"
        artifact_id = f"art_{uuid.uuid4().hex}"
        created_at = utc_text()
        store.publish(staged, artifact_id)
        published_artifact_id = artifact_id
        upload = CsvUpload(
            upload_id=upload_id,
            upload_kind=kind,
            original_filename=staged.filename,
            artifact_id=artifact_id,
            file_size_bytes=staged.file_size_bytes,
            file_sha256=staged.sha256,
            uploaded_by=context.user.user_id,
            uploaded_at=created_at,
        )
        preview = UploadPreview(
            preview_id=preview_id,
            preview_idempotency_key=key,
            preview_request_sha256=fingerprint,
            upload_id=upload_id,
            verified_sha256=staged.sha256,
            parser_contract_version=parsed.parser_contract_version,
            column_mappings_text=_canonical_json(canonical_mappings),
            state=parsed.state,
            total_row_count=parsed.total_count,
            accepted_row_count=parsed.accepted_count,
            rejected_row_count=parsed.rejected_count,
            duplicate_row_count=parsed.duplicate_count,
            conflict_row_count=parsed.conflict_count,
            created_at=created_at,
            confirmed_by=None,
            confirmed_at=None,
        )
        db.add(upload)
        db.add(preview)
        db.flush()
        if parsed.rows:
            db.execute(
                insert(UploadPreviewRow),
                [
                    {
                        "preview_id": preview_id,
                        "row_number": row.row_number,
                        "row_status": row.row_status,
                        "source_type": row.source_type,
                        "source_record_id": row.source_record_id,
                        "normalized_row_text": row.normalized_row_text,
                        "row_payload_sha256": row.row_payload_sha256,
                        "rejection_codes_text": _canonical_json(list(row.rejection_codes)) if row.rejection_codes else None,
                        "rejection_detail": row.rejection_detail,
                        "created_at": created_at,
                    }
                    for row in parsed.rows
                ],
            )
        db.commit()
        published_artifact_id = None
        return _preview_response(preview, upload)
    except CsvInputError as error:
        if db.in_transaction():
            db.rollback()
        raise ApiError(error.status, error.code, error.detail, "Upload validation failed") from error
    except ApiError:
        if db.in_transaction():
            db.rollback()
        raise
    except IntegrityError as error:
        if db.in_transaction():
            db.rollback()
        if published_artifact_id and _is_artifact_referenced(db, published_artifact_id) is False:
            store.remove_published(published_artifact_id)
            published_artifact_id = None
        existing = db.scalar(select(UploadPreview).where(UploadPreview.preview_idempotency_key == key))
        if existing is not None:
            existing_upload = db.get(CsvUpload, existing.upload_id)
            if existing.preview_request_sha256 == fingerprint and existing_upload is not None:
                db.commit()
                response.status_code = 200
                return _preview_response(existing, existing_upload)
            db.rollback()
            raise ApiError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "The Idempotency-Key was already used for a different preview request.",
                "Conflict",
            ) from error
        raise ApiError(503, "PREVIEW_CREATE_FAILED", "The preview could not be saved. Try again.", "Request failed") from error
    except Exception as error:
        if db.in_transaction():
            db.rollback()
        if published_artifact_id and _is_artifact_referenced(db, published_artifact_id) is False:
            store.remove_published(published_artifact_id)
            published_artifact_id = None
        _UPLOAD_LOG.error("event=PREVIEW_CREATE_FAILED request_id=%s", getattr(request.state, "request_id", "unknown"))
        raise ApiError(503, "PREVIEW_CREATE_FAILED", "The preview could not be saved. Try again.", "Request failed") from error
    finally:
        if staged is not None:
            store.discard_stage(staged)
        await form.close()


@router.get("/admin/ingestion/previews/{preview_id}", response_model=UploadPreviewResponse, response_model_exclude_none=True)
def get_ingestion_preview(
    preview_id: str,
    context: AuthContext = Depends(get_admin_context),
) -> UploadPreviewResponse:
    preview = context.db.get(UploadPreview, preview_id)
    if preview is None:
        raise _missing_preview()
    upload = context.db.get(CsvUpload, preview.upload_id)
    if upload is None:
        raise ApiError(503, "PREVIEW_UNAVAILABLE", "The saved preview is temporarily unavailable.", "Request failed")
    return _preview_response(preview, upload)


@router.get("/admin/ingestion/previews/{preview_id}/rows", response_model=UploadPreviewRowPage)
def list_ingestion_preview_rows(
    preview_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    row_status: str | None = Query(default=None, pattern="^(ACCEPTED|REJECTED|DUPLICATE_NOOP|CONFLICT)$"),
    context: AuthContext = Depends(get_admin_context),
) -> UploadPreviewRowPage:
    db = context.db
    if db.get(UploadPreview, preview_id) is None:
        raise _missing_preview()
    filters = [UploadPreviewRow.preview_id == preview_id]
    if row_status:
        filters.append(UploadPreviewRow.row_status == row_status)
    total = db.scalar(select(func.count()).select_from(UploadPreviewRow).where(*filters)) or 0
    rows = db.scalars(
        select(UploadPreviewRow)
        .where(*filters)
        .order_by(UploadPreviewRow.row_number)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return UploadPreviewRowPage(
        items=[
            UploadPreviewRowResponse(
                preview_id=row.preview_id,
                row_number=row.row_number,
                row_status=row.row_status,
                source_type=row.source_type,
                source_record_id=row.source_record_id,
                rejection_codes=json.loads(row.rejection_codes_text) if row.rejection_codes_text else [],
                rejection_detail=row.rejection_detail,
            )
            for row in rows
        ],
        page=page_meta(page, page_size, total),
    )
