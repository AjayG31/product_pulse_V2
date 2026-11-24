"""Exact, no-overwrite reference import planning and persistence."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from productpulse.ingestion.parser import PreviewParse, RowResult
from productpulse.models import (
    Batch,
    CsvUpload,
    IngestionConflict,
    Product,
    Supplier,
    UploadPreviewRow,
)


REFERENCE_KINDS = frozenset({"PRODUCT_REFERENCE", "SUPPLIER_REFERENCE", "BATCH_REFERENCE"})
_SAFE_MAPPING_CONFLICT = "The reference identifier already has a different stored mapping."
_SAFE_REFERENCE_DEPENDENCY = "The referenced product or supplier must be imported before this batch."


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _values(kind: str, payload: dict[str, object]) -> dict[str, object]:
    if kind == "PRODUCT_REFERENCE":
        return {"product_id": payload["product_id"], "name": payload.get("name"), "category": payload.get("category")}
    if kind == "SUPPLIER_REFERENCE":
        return {"supplier_id": payload["supplier_id"], "name": payload.get("name")}
    return {"batch_id": payload["batch_id"], "product_id": payload["product_id"], "supplier_id": payload["supplier_id"]}


def _lookup(db: Session, kind: str, values: dict[str, object]):
    identity = values["product_id" if kind == "PRODUCT_REFERENCE" else "supplier_id" if kind == "SUPPLIER_REFERENCE" else "batch_id"]
    model = Product if kind == "PRODUCT_REFERENCE" else Supplier if kind == "SUPPLIER_REFERENCE" else Batch
    return db.get(model, str(identity))


def _stored_mapping(kind: str, existing) -> dict[str, object] | None:
    if existing is None:
        return None
    if kind == "PRODUCT_REFERENCE":
        return {"product_id": existing.product_id, "name": existing.name, "category": existing.category}
    if kind == "SUPPLIER_REFERENCE":
        return {"supplier_id": existing.supplier_id, "name": existing.name}
    return {"batch_id": existing.batch_id, "product_id": existing.product_id, "supplier_id": existing.supplier_id}


def _classify(db: Session, kind: str, row: RowResult) -> tuple[RowResult, tuple[str, str] | None]:
    if row.normalized_row_text is None or row.row_payload_sha256 is None:
        return row, None
    try:
        payload = json.loads(row.normalized_row_text)
    except (json.JSONDecodeError, TypeError):
        return replace(row, row_status="REJECTED", normalized_row_text=None, row_payload_sha256=None,
                       rejection_codes=("REFERENCE_ROW_INVALID",), rejection_detail="The saved reference row is invalid."), None
    if not isinstance(payload, dict):
        return replace(row, row_status="REJECTED", normalized_row_text=None, row_payload_sha256=None,
                       rejection_codes=("REFERENCE_ROW_INVALID",), rejection_detail="The saved reference row is invalid."), None

    values = _values(kind, payload)
    id_field = "product_id" if kind == "PRODUCT_REFERENCE" else "supplier_id" if kind == "SUPPLIER_REFERENCE" else "batch_id"
    identity = str(values[id_field])
    identity_key = (kind, identity)
    existing = _lookup(db, kind, values)

    if kind == "BATCH_REFERENCE":
        product_exists = db.get(Product, str(values["product_id"])) is not None
        supplier_exists = db.get(Supplier, str(values["supplier_id"])) is not None
        if existing is None and not (product_exists and supplier_exists):
            return replace(row, row_status="REJECTED", normalized_row_text=None, row_payload_sha256=None,
                           rejection_codes=("REFERENCE_DEPENDENCY_MISSING",), rejection_detail=_SAFE_REFERENCE_DEPENDENCY), identity_key
        if existing is None:
            return replace(row, row_status="ACCEPTED", rejection_codes=(), rejection_detail=None), identity_key
        stored = _stored_mapping(kind, existing)
        if stored == values:
            return replace(row, row_status="DUPLICATE_NOOP", rejection_codes=(), rejection_detail=None), identity_key
        return replace(row, row_status="CONFLICT", rejection_codes=("REFERENCE_MAPPING_CONFLICT",),
                       rejection_detail=_SAFE_MAPPING_CONFLICT), identity_key

    if existing is None:
        return replace(row, row_status="ACCEPTED", rejection_codes=(), rejection_detail=None), identity_key
    stored = _stored_mapping(kind, existing)
    changed_existing_value = any(
        values[field] is not None and stored[field] is not None and values[field] != stored[field]
        for field in values if field != id_field
    )
    if changed_existing_value:
        return replace(row, row_status="CONFLICT", rejection_codes=("REFERENCE_MAPPING_CONFLICT",),
                       rejection_detail=_SAFE_MAPPING_CONFLICT), identity_key
    has_fill = any(
        values[field] is not None and stored[field] is None
        for field in values if field != id_field
    )
    if has_fill:
        return replace(row, row_status="ACCEPTED", rejection_codes=(), rejection_detail=None), identity_key
    return replace(row, row_status="DUPLICATE_NOOP", rejection_codes=(), rejection_detail=None), identity_key


def reclassify_reference_preview(db: Session, kind: str, parsed: PreviewParse) -> PreviewParse:
    if kind not in REFERENCE_KINDS:
        return parsed
    seen: dict[tuple[str, str], str] = {}
    final: list[RowResult] = []
    for row in parsed.rows:
        if row.row_status == "REJECTED" or row.normalized_row_text is None:
            final.append(row)
            continue
        try:
            payload = json.loads(row.normalized_row_text)
            if not isinstance(payload, dict):
                raise ValueError
            values = _values(kind, payload)
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            final.append(replace(row, row_status="REJECTED", normalized_row_text=None, row_payload_sha256=None,
                                 rejection_codes=("REFERENCE_ROW_INVALID",), rejection_detail="The saved reference row is invalid."))
            continue
        id_field = "product_id" if kind == "PRODUCT_REFERENCE" else "supplier_id" if kind == "SUPPLIER_REFERENCE" else "batch_id"
        identity_key = (kind, str(values[id_field]))
        previous_hash = seen.get(identity_key)
        seen.setdefault(identity_key, row.row_payload_sha256 or "")
        if previous_hash is not None:
            if previous_hash == row.row_payload_sha256:
                final.append(replace(row, row_status="DUPLICATE_NOOP", rejection_codes=(), rejection_detail=None))
            else:
                final.append(replace(row, row_status="CONFLICT", rejection_codes=("REFERENCE_MAPPING_CONFLICT",),
                                     rejection_detail=_SAFE_MAPPING_CONFLICT))
            continue
        classified, _key = _classify(db, kind, row)
        final.append(classified)

    accepted = sum(row.row_status == "ACCEPTED" for row in final)
    rejected = sum(row.row_status == "REJECTED" for row in final)
    duplicates = sum(row.row_status == "DUPLICATE_NOOP" for row in final)
    conflicts = sum(row.row_status == "CONFLICT" for row in final)
    return replace(
        parsed,
        rows=tuple(final),
        state="READY" if accepted else "INVALID",
        accepted_count=accepted,
        rejected_count=rejected,
        duplicate_count=duplicates,
        conflict_count=conflicts,
    )


def assert_reference_preview_current(db: Session, kind: str, preview_id: str) -> bool:
    stored = db.scalars(
        select(UploadPreviewRow).where(UploadPreviewRow.preview_id == preview_id).order_by(UploadPreviewRow.row_number)
    ).all()
    seen: dict[tuple[str, str], str] = {}
    for row in stored:
        if row.row_status == "REJECTED" or row.normalized_row_text is None:
            continue
        parsed_row = RowResult(
            row_number=row.row_number,
            row_status=row.row_status,
            source_type=row.source_type,
            source_record_id=row.source_record_id,
            normalized_row_text=row.normalized_row_text,
            row_payload_sha256=row.row_payload_sha256,
            rejection_codes=tuple(json.loads(row.rejection_codes_text or "[]")),
            rejection_detail=row.rejection_detail,
        )
        try:
            payload = json.loads(row.normalized_row_text)
            values = _values(kind, payload)
        except (json.JSONDecodeError, TypeError, KeyError):
            return False
        id_field = "product_id" if kind == "PRODUCT_REFERENCE" else "supplier_id" if kind == "SUPPLIER_REFERENCE" else "batch_id"
        identity_key = (kind, str(values[id_field]))
        previous_hash = seen.get(identity_key)
        if previous_hash is not None:
            current_status = "DUPLICATE_NOOP" if previous_hash == row.row_payload_sha256 else "CONFLICT"
        else:
            seen[identity_key] = row.row_payload_sha256 or ""
            current_status, _ = _classify(db, kind, parsed_row)
            current_status = current_status.row_status
        if current_status != row.row_status:
            return False
    return True


def persist_reference_rows(db: Session, preview: object, upload: CsvUpload, now: str) -> int:
    rows = db.scalars(
        select(UploadPreviewRow).where(
            UploadPreviewRow.preview_id == preview.preview_id,
            UploadPreviewRow.row_status == "ACCEPTED",
        ).order_by(UploadPreviewRow.row_number)
    ).all()
    for row in rows:
        if not row.normalized_row_text or hashlib.sha256(row.normalized_row_text.encode("utf-8")).hexdigest() != row.row_payload_sha256:
            raise ValueError("reference preview integrity check failed")
        values = json.loads(row.normalized_row_text)
        if upload.upload_kind == "PRODUCT_REFERENCE":
            existing = db.get(Product, values["product_id"])
            if existing is None:
                db.add(Product(product_id=values["product_id"], name=values.get("name"), category=values.get("category"), created_at=now, updated_at=now))
            else:
                if existing.name is None and values.get("name") is not None:
                    existing.name = values["name"]
                    existing.updated_at = now
                if existing.category is None and values.get("category") is not None:
                    existing.category = values["category"]
                    existing.updated_at = now
        elif upload.upload_kind == "SUPPLIER_REFERENCE":
            existing = db.get(Supplier, values["supplier_id"])
            if existing is None:
                db.add(Supplier(supplier_id=values["supplier_id"], name=values.get("name"), created_at=now, updated_at=now))
            elif existing.name is None and values.get("name") is not None:
                existing.name = values["name"]
                existing.updated_at = now
        elif upload.upload_kind == "BATCH_REFERENCE":
            if db.get(Batch, values["batch_id"]) is None:
                db.add(Batch(
                    batch_id=values["batch_id"], product_id=values["product_id"], supplier_id=values["supplier_id"],
                    created_at=now, updated_at=now,
                ))
        else:
            raise ValueError("unsupported reference upload kind")
    db.flush()
    return len(rows)


def persist_conflict_rows(db: Session, preview_id: str, upload_kind: str, rows: tuple[RowResult, ...], now: str) -> None:
    for row in rows:
        if row.row_status != "CONFLICT":
            continue
        existing_feedback_id = None
        source_type = None
        source_record_id = None
        existing_hash = None
        mapping_key = None
        conflict_kind = "SOURCE_PAYLOAD"
        if upload_kind in REFERENCE_KINDS:
            conflict_kind = "REFERENCE_MAPPING"
            payload = json.loads(row.normalized_row_text or "{}")
            values = _values(upload_kind, payload)
            id_field = "product_id" if upload_kind == "PRODUCT_REFERENCE" else "supplier_id" if upload_kind == "SUPPLIER_REFERENCE" else "batch_id"
            mapping_key = f"{upload_kind}:{values[id_field]}"
            existing = _lookup(db, upload_kind, values)
            stored = _stored_mapping(upload_kind, existing)
            if stored is not None:
                existing_hash = _hash(stored)
        else:
            source_type = row.source_type
            source_record_id = row.source_record_id
            if source_type and source_record_id:
                from productpulse.models import Feedback
                feedback = db.scalar(select(Feedback).where(Feedback.source_type == source_type, Feedback.source_record_id == source_record_id))
                if feedback is not None:
                    existing_feedback_id = feedback.feedback_id
                    existing_hash = feedback.payload_sha256
        db.add(IngestionConflict(
            conflict_id=f"icf_{uuid.uuid4().hex}",
            preview_id=preview_id,
            row_number=row.row_number,
            conflict_kind=conflict_kind,
            existing_feedback_id=existing_feedback_id,
            source_type=source_type,
            source_record_id=source_record_id,
            existing_value_hash=existing_hash,
            incoming_value_hash=row.row_payload_sha256,
            mapping_key=mapping_key,
            state="PENDING",
            resolution_note=None,
            created_at=now,
            resolved_by=None,
            resolved_at=None,
        ))
    db.flush()
