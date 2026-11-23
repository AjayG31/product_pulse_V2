from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import io
import json
import re
from typing import Any


MAX_FILE_BYTES = 20_000_000
MAX_DATA_ROWS = 50_000
MAX_FIELD_BYTES = 65_536
MAX_IDENTIFIER_CODEPOINTS = 256
MAX_OTHER_CODEPOINTS = 1_024
MAX_FEEDBACK_CODEPOINTS = 16_384
csv.field_size_limit(MAX_FILE_BYTES)

UPLOAD_SPECS: dict[str, dict[str, Any]] = {
    "REVIEWS": {
        "version": "reviews-v1",
        "fields": {"review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text", "rating", "source"},
        "required_headers": {"review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"},
        "required_values": {"review_id", "product_id", "review_timestamp", "review_text"},
        "identity": "review_id",
        "source_type": "REVIEW",
    },
    "RETURNS": {
        "version": "returns-v1",
        "fields": {"return_id", "product_id", "supplier_id", "batch_id", "return_timestamp", "return_reason", "return_quantity", "return_category"},
        "required_headers": {"return_id", "product_id", "supplier_id", "batch_id", "return_timestamp", "return_reason"},
        "required_values": {"return_id", "product_id", "return_timestamp", "return_reason"},
        "identity": "return_id",
        "source_type": "RETURN",
    },
    "PRODUCT_REFERENCE": {
        "version": "product-reference-v1",
        "fields": {"product_id", "name", "category"},
        "required_headers": {"product_id"},
        "required_values": {"product_id"},
        "identity": "product_id",
        "source_type": None,
    },
    "SUPPLIER_REFERENCE": {
        "version": "supplier-reference-v1",
        "fields": {"supplier_id", "name"},
        "required_headers": {"supplier_id"},
        "required_values": {"supplier_id"},
        "identity": "supplier_id",
        "source_type": None,
    },
    "BATCH_REFERENCE": {
        "version": "batch-reference-v1",
        "fields": {"batch_id", "product_id", "supplier_id"},
        "required_headers": {"batch_id", "product_id", "supplier_id"},
        "required_values": {"batch_id", "product_id", "supplier_id"},
        "identity": "batch_id",
        "source_type": None,
    },
}

TEMPLATES: dict[str, tuple[str, ...]] = {
    "REVIEWS": ("review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text", "rating", "source"),
    "RETURNS": ("return_id", "product_id", "supplier_id", "batch_id", "return_timestamp", "return_reason", "return_quantity", "return_category"),
    "PRODUCT_REFERENCE": ("product_id", "name", "category"),
    "SUPPLIER_REFERENCE": ("supplier_id", "name"),
    "BATCH_REFERENCE": ("batch_id", "product_id", "supplier_id"),
}

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,3}))?(?:Z|[+-]\d{2}:\d{2})$")
_IDENTIFIERS = {"review_id", "return_id", "product_id", "supplier_id", "batch_id"}
_FEEDBACK_TEXT = {"review_text", "return_reason"}
_OPTIONAL_TEXT = {"source", "return_category", "name", "category"}
_SAFE_DETAILS = {
    "COLUMN_COUNT_MISMATCH": "The row does not match the mapped column count.",
    "EMPTY_REQUIRED_VALUE": "A required value is empty.",
    "INVALID_IDENTIFIER": "An identifier is empty, padded, or whitespace only.",
    "FIELD_TOO_LONG": "A value exceeds the approved field length.",
    "INVALID_TIMESTAMP": "The timestamp must include Z or an explicit offset and use at most millisecond precision.",
    "INVALID_INTEGER": "The value must be an integer in the allowed range.",
    "INVALID_SOURCE_ID": "The row does not contain a usable source identity.",
}


class CsvInputError(ValueError):
    def __init__(self, code: str, detail: str, *, status: int = 422) -> None:
        super().__init__(detail)
        self.code = code
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class RowResult:
    row_number: int
    row_status: str
    source_type: str | None
    source_record_id: str | None
    normalized_row_text: str | None
    row_payload_sha256: str | None
    rejection_codes: tuple[str, ...]
    rejection_detail: str | None


@dataclass(frozen=True)
class PreviewParse:
    parser_contract_version: str
    header: tuple[str, ...]
    mappings: tuple[dict[str, object], ...]
    rows: tuple[RowResult, ...]
    state: str
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    conflict_count: int

    @property
    def total_count(self) -> int:
        return len(self.rows)


def template_bytes(upload_kind: str) -> bytes:
    spec = UPLOAD_SPECS.get(upload_kind)
    if spec is None:
        raise CsvInputError("UPLOAD_KIND_INVALID", "Choose a supported CSV type.")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(TEMPLATES[upload_kind])
    return output.getvalue().encode("utf-8")


def safe_filename(filename: str | None) -> str:
    value = (filename or "upload.csv").replace("\\", "/").split("/")[-1]
    value = "".join(ch for ch in value if ord(ch) >= 32 and ord(ch) != 127).strip()
    if not value or len(value) > 255:
        value = "upload.csv"
    return value


def canonical_mappings(header: list[str], upload_kind: str, mappings: list[dict[str, object]]) -> list[dict[str, object]]:
    spec = UPLOAD_SPECS.get(upload_kind)
    if spec is None:
        raise CsvInputError("UPLOAD_KIND_INVALID", "Choose a supported CSV type.")
    if not header or any(not item for item in header):
        raise CsvInputError("CSV_HEADER_INVALID", "The CSV header row is missing a column name.")
    if any("\ufeff" in item or len(item) > MAX_OTHER_CODEPOINTS or len(item.encode("utf-8")) > MAX_FIELD_BYTES for item in header):
        raise CsvInputError("CSV_HEADER_INVALID", "A CSV header value is malformed or exceeds the approved field length.")
    if len(mappings) != len(header):
        raise CsvInputError("MAPPING_INVALID", "Map every source column exactly once.")

    ordered = sorted(mappings, key=lambda item: int(item["source_column_index"]))
    indexes: set[int] = set()
    targets: set[str] = set()
    for item in ordered:
        index = int(item["source_column_index"])
        header_text = str(item["source_header"])
        target = str(item["target_field"])
        if index < 0 or index >= len(header) or index in indexes:
            raise CsvInputError("MAPPING_INVALID", "The column mapping contains an invalid or repeated source index.")
        if header[index] != header_text:
            raise CsvInputError("MAPPING_INVALID", "The column mapping does not match the uploaded header.")
        if target != "IGNORE" and target not in spec["fields"]:
            raise CsvInputError("MAPPING_INVALID", "A target field is not valid for the selected CSV type.")
        if target != "IGNORE" and target in targets:
            raise CsvInputError("MAPPING_INVALID", "A canonical target field may be mapped only once.")
        indexes.add(index)
        targets.add(target)

    if targets.intersection(spec["required_headers"]) != spec["required_headers"]:
        raise CsvInputError("MAPPING_REQUIRED", "Map every required field before creating a preview.")
    return ordered


def parse_preview(
    path,
    upload_kind: str,
    mappings: list[dict[str, object]],
    existing_payload_hashes: dict[tuple[str, str], str] | None = None,
) -> PreviewParse:
    spec = UPLOAD_SPECS.get(upload_kind)
    if spec is None:
        raise CsvInputError("UPLOAD_KIND_INVALID", "Choose a supported CSV type.")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            try:
                header = next(reader)
            except StopIteration as error:
                raise CsvInputError("CSV_HEADER_INVALID", "The CSV must contain a header row.") from error
            canonical = canonical_mappings(header, upload_kind, mappings)
            rows: list[RowResult] = []
            seen: dict[tuple[str, str], str] = {}
            existing_hashes = existing_payload_hashes or {}
            for row_number, values in enumerate(reader, start=1):
                if row_number > MAX_DATA_ROWS:
                    raise CsvInputError("CSV_ROW_LIMIT_EXCEEDED", "The CSV contains more than 50,000 data records.")
                if any("\ufeff" in value for value in values):
                    raise CsvInputError("CSV_MALFORMED", "A UTF-8 BOM is only permitted at the start of the file.")
                result, identity_key = _validate_row(row_number, values, len(header), upload_kind, canonical)
                if result.row_status == "ACCEPTED" and identity_key is not None and result.row_payload_sha256 is not None:
                    source_identity = (result.source_type or identity_key[0], identity_key[1])
                    existing = seen.get(identity_key)
                    if existing is not None:
                        if existing == result.row_payload_sha256:
                            result = RowResult(
                                row_number, "DUPLICATE_NOOP", result.source_type, result.source_record_id,
                                result.normalized_row_text, result.row_payload_sha256, (), None
                            )
                        else:
                            result = RowResult(
                                row_number, "CONFLICT", result.source_type, result.source_record_id,
                                result.normalized_row_text, result.row_payload_sha256,
                                ("SOURCE_PAYLOAD_CONFLICT",), "This identity has different content in the same file."
                            )
                    else:
                        stored = existing_hashes.get(source_identity)
                        if stored is not None:
                            if stored == result.row_payload_sha256:
                                result = RowResult(
                                    row_number, "DUPLICATE_NOOP", result.source_type, result.source_record_id,
                                    result.normalized_row_text, result.row_payload_sha256, (), None
                                )
                            else:
                                result = RowResult(
                                    row_number, "CONFLICT", result.source_type, result.source_record_id,
                                    result.normalized_row_text, result.row_payload_sha256,
                                    ("SOURCE_PAYLOAD_CONFLICT",), "This identity has different stored content."
                                )
                        seen[identity_key] = result.row_payload_sha256
                rows.append(result)
    except CsvInputError:
        raise
    except (UnicodeDecodeError, csv.Error, OSError) as error:
        raise CsvInputError("CSV_MALFORMED", "The CSV encoding or file structure is invalid.") from error

    if not rows:
        # A header-only file is a valid file-level preview with no eligible rows.
        rows = []
    accepted = sum(row.row_status == "ACCEPTED" for row in rows)
    rejected = sum(row.row_status == "REJECTED" for row in rows)
    duplicates = sum(row.row_status == "DUPLICATE_NOOP" for row in rows)
    conflicts = sum(row.row_status == "CONFLICT" for row in rows)
    return PreviewParse(
        parser_contract_version=spec["version"],
        header=tuple(header),
        mappings=tuple(canonical),
        rows=tuple(rows),
        state="READY" if accepted else "INVALID",
        accepted_count=accepted,
        rejected_count=rejected,
        duplicate_count=duplicates,
        conflict_count=conflicts,
    )


def _validate_row(
    row_number: int,
    values: list[str],
    header_length: int,
    upload_kind: str,
    mappings: list[dict[str, object]],
) -> tuple[RowResult, tuple[str, str] | None]:
    spec = UPLOAD_SPECS[upload_kind]
    source_type = spec["source_type"]
    if len(values) != header_length:
        return _rejected(row_number, source_type, None, ["COLUMN_COUNT_MISMATCH"]), None
    if any(len(value.encode("utf-8")) > MAX_FIELD_BYTES for value in values):
        return _rejected(row_number, source_type, None, ["FIELD_TOO_LONG"]), None

    normalized: dict[str, object] = {}
    for item in mappings:
        target = str(item["target_field"])
        if target == "IGNORE":
            continue
        normalized[target] = values[int(item["source_column_index"])]

    row_identity = normalized.get(spec["identity"])
    source_record_id = None
    if source_type and isinstance(row_identity, str):
        if (
            row_identity
            and row_identity == row_identity.strip()
            and len(row_identity) <= MAX_IDENTIFIER_CODEPOINTS
            and len(row_identity.encode("utf-8")) <= MAX_FIELD_BYTES
        ):
            source_record_id = row_identity
    issues: list[str] = []

    for field in spec["fields"]:
        if field not in normalized:
            continue
        value = normalized[field]
        if not isinstance(value, str):
            continue
        if field not in _IDENTIFIERS and field not in _FEEDBACK_TEXT and len(value) > MAX_OTHER_CODEPOINTS:
            issues.append("FIELD_TOO_LONG")
        if field in _IDENTIFIERS:
            if value == "" and field in {"supplier_id", "batch_id"}:
                normalized[field] = None
                continue
            if not value or not value.strip() or value != value.strip():
                issues.append("INVALID_IDENTIFIER")
                continue
            if len(value) > MAX_IDENTIFIER_CODEPOINTS or len(value.encode("utf-8")) > MAX_FIELD_BYTES:
                issues.append("FIELD_TOO_LONG")
        elif field in _FEEDBACK_TEXT:
            if not value:
                if field in spec["required_values"]:
                    issues.append("EMPTY_REQUIRED_VALUE")
                else:
                    normalized[field] = None
            elif len(value) > MAX_FEEDBACK_CODEPOINTS or len(value.encode("utf-8")) > MAX_FIELD_BYTES:
                issues.append("FIELD_TOO_LONG")
        elif field in {"review_timestamp", "return_timestamp"}:
            try:
                normalized[field] = _normalize_timestamp(value)
            except ValueError:
                issues.append("INVALID_TIMESTAMP")
        elif field in {"rating", "return_quantity"}:
            if value == "":
                normalized[field] = None
                continue
            try:
                if not re.fullmatch(r"[0-9]+", value):
                    raise ValueError
                number = int(value)
                if field == "rating" and not 1 <= number <= 5:
                    raise ValueError
                if field == "return_quantity" and number <= 0:
                    raise ValueError
                normalized[field] = number
            except ValueError:
                issues.append("INVALID_INTEGER")
        elif field in _OPTIONAL_TEXT:
            if len(value) > MAX_OTHER_CODEPOINTS or len(value.encode("utf-8")) > MAX_FIELD_BYTES:
                issues.append("FIELD_TOO_LONG")
            elif value == "":
                normalized[field] = None

    for field in spec["required_values"]:
        if field not in normalized or normalized[field] is None or normalized[field] == "":
            issues.append("EMPTY_REQUIRED_VALUE")
    # Keep reason codes stable and deterministic when multiple fields fail.
    codes = tuple(sorted(set(issues)))
    if codes:
        return _rejected(row_number, source_type, source_record_id, codes), None

    identity_value = normalized.get(spec["identity"])
    if not isinstance(identity_value, str) or not identity_value:
        return _rejected(row_number, source_type, None, ["INVALID_SOURCE_ID"]), None

    canonical_text = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload_hash = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    identity_key = (upload_kind, identity_value)
    return (
        RowResult(row_number, "ACCEPTED", source_type, source_record_id, canonical_text, payload_hash, (), None),
        identity_key,
    )


def _rejected(row_number: int, source_type: str | None, source_record_id: str | None, codes: list[str]) -> RowResult:
    ordered = tuple(sorted(set(codes)))
    detail = _SAFE_DETAILS.get(ordered[0], "The row conflicts with an earlier row in this file.") if ordered else None
    return RowResult(row_number, "REJECTED", source_type, source_record_id, None, None, ordered, detail)


def _normalize_timestamp(value: str) -> str:
    if not _TIMESTAMP.fullmatch(value):
        raise ValueError("invalid timestamp")
    normalized_input = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized_input)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
