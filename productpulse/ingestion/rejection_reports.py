from __future__ import annotations

import csv
from dataclasses import dataclass
import io
from collections.abc import Iterable, Iterator, Sequence


REPORT_COLUMNS = (
    "row_number",
    "outcome",
    "source_type",
    "source_record_id",
    "reason_code",
    "safe_explanation",
)


@dataclass(frozen=True)
class RejectionReportRow:
    row_number: int
    row_status: str
    source_type: str | None
    source_record_id: str | None
    rejection_codes: Sequence[str]
    rejection_detail: str | None


def _formula_safe(value: str | None) -> str:
    if value is None:
        return ""
    probe = value.lstrip(" \t\r\n\v\f\x00\ufeff")
    if probe.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv_line(values: Sequence[str | int]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\r\n").writerow(values)
    return output.getvalue().encode("utf-8")


def rejection_report_chunks(rows: Iterable[RejectionReportRow]) -> Iterator[bytes]:
    """Yield bounded formula-safe UTF-8 CSV chunks without raw feedback."""
    yield _csv_line(REPORT_COLUMNS)
    for row in rows:
        if row.row_status not in {"REJECTED", "CONFLICT"}:
            continue
        yield _csv_line(
            (
                row.row_number,
                row.row_status,
                _formula_safe(row.source_type),
                _formula_safe(row.source_record_id),
                _formula_safe(";".join(row.rejection_codes)),
                _formula_safe(row.rejection_detail),
            )
        )
