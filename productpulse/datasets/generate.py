"""Generate a reproducible, development-only ProductPulse source corpus."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


GENERATOR_VERSION = "1.0.0"
SEED = 20261122
RECORDS_PER_SOURCE = 5_000
BASE_EVENT_TIME = datetime(2025, 1, 1, tzinfo=UTC)
EVENT_DAYS = 35
FAMILIES = ("zippers", "stitching", "sizing/fit", "material", "finish", "packaging")
SOURCES = ("web", "app", "marketplace")

REVIEW_FIELDS = (
    "review_id",
    "product_id",
    "supplier_id",
    "batch_id",
    "review_timestamp",
    "review_text",
    "rating",
    "source",
)
RETURN_FIELDS = (
    "return_id",
    "product_id",
    "supplier_id",
    "batch_id",
    "return_timestamp",
    "return_reason",
    "return_quantity",
    "return_category",
)

_FAMILY_TEXT = {
    "zippers": (
        "The front zipper catches and split open after several wears.",
        "The jacket zipper separates near the bottom when I close it.",
    ),
    "stitching": (
        "The side seam stitching came loose after the first wash.",
        "Several stitches are missing near the sleeve seam.",
    ),
    "sizing/fit": (
        "The size guide matched, but the sleeves are much shorter than expected.",
        "The waistband is unusually tight compared with the listed measurements.",
    ),
    "material": (
        "The fabric developed a hole after one gentle wash.",
        "The lining tore where it joins the main fabric.",
    ),
    "finish": (
        "The coating peeled from the buttons after normal use.",
        "The hem finish frayed before the garment was washed.",
    ),
    "packaging": (
        "The package arrived crushed and the garment was marked inside.",
        "The item was missing its protective wrap and had a damaged corner.",
    ),
}
_REVIEW_TEXT = (
    "The cotton shirt is comfortable and arrived as expected.",
    "The jacket feels light and the seams look intact.",
    "The garment washed well and the color stayed consistent.",
    "The item matched the product description and fit as expected.",
)
_RETURN_REASONS = (
    "Changed purchase preference; the item itself is intact.",
    "The color was different from what I wanted; no product issue noted.",
    "The gift was no longer needed; the item is unused.",
)


def _utc_text(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _record_truth(index: int, source_type: str) -> dict[str, Any]:
    slot = index % 20
    scenario_group = index // 100
    family = FAMILIES[slot] if slot < len(FAMILIES) else None

    if family is not None:
        truth_kind = "PLANTED_DEFECT"
        scenario_id = f"DEV-SCN-{scenario_group:03d}-F{slot + 1:02d}"
        event_day = 28 + scenario_group % 7
    elif slot < 8:
        truth_kind, scenario_id, event_day = "NON_DEFECT", None, index % EVENT_DAYS
    elif slot == 8:
        truth_kind, scenario_id, event_day = "AMBIGUOUS", None, index % EVENT_DAYS
    elif slot == 9:
        truth_kind, scenario_id, event_day = "LATE_ARRIVAL", None, index % EVENT_DAYS
    elif slot == 10:
        truth_kind, scenario_id, event_day = "DATA_QUALITY_FAILURE", None, index % EVENT_DAYS
    else:
        truth_kind, scenario_id, event_day = "NORMAL", None, index % EVENT_DAYS

    event_time: datetime | None = BASE_EVENT_TIME + timedelta(
        days=event_day,
        hours=(index * 3 + SEED) % 24,
        minutes=(index * 11 + SEED) % 60,
        seconds=index % 60,
    )

    quality_fixture = None
    if truth_kind == "DATA_QUALITY_FAILURE":
        quality_fixture = "MISSING_TEXT" if (index // 20) % 2 == 0 else "INVALID_EVENT_TIME"
        if quality_fixture == "INVALID_EVENT_TIME":
            event_time = None

    linkage_complete = not (
        truth_kind not in {"PLANTED_DEFECT", "DATA_QUALITY_FAILURE"} and index % 97 == 0
    )
    late_arrival = truth_kind == "LATE_ARRIVAL"
    ingested_at = (
        event_time + (timedelta(days=3) if late_arrival else timedelta(minutes=15))
        if event_time is not None
        else None
    )

    if source_type == "REVIEW":
        record_id = f"REV-{index + 1:06d}"
    else:
        record_id = f"RET-{index + 1:06d}"

    return {
        "source_type": source_type,
        "source_record_id": record_id,
        "truth_kind": truth_kind,
        "defect_family_concept": family,
        "scenario_id": scenario_id,
        "event_time_utc": _utc_text(event_time) or None,
        "ingested_at_utc": _utc_text(ingested_at) or None,
        "late_arrival": late_arrival,
        "linkage_complete": linkage_complete,
        "quality_fixture": quality_fixture,
        "source_text_origin": "synthetic_template_v1",
    }


def _product_links(index: int, truth: dict[str, Any]) -> tuple[str, str, str]:
    family = truth["defect_family_concept"]
    if family is not None:
        family_index = FAMILIES.index(family)
        product_index = family_index
    else:
        product_index = index % len(FAMILIES)

    product_id = f"P{1001 + product_index}"
    if not truth["linkage_complete"]:
        return product_id, "", ""

    supplier_id = f"SUP{1 + (product_index % 3):02d}"
    batch_id = f"B{101 + ((index // 100) % 10):03d}"
    return product_id, supplier_id, batch_id


def _review_text(truth: dict[str, Any], index: int) -> str:
    kind = truth["truth_kind"]
    family = truth["defect_family_concept"]
    if family is not None:
        options = _FAMILY_TEXT[family]
        return options[(index + SEED) % len(options)]
    if kind == "NON_DEFECT":
        return "The fit and finish match the listing; I have no product issue to report."
    if kind == "AMBIGUOUS":
        return "The seam looks uneven in this light, though it may be the fabric texture."
    if kind == "LATE_ARRIVAL":
        return "The cardigan arrived later than expected; the garment itself is intact."
    if kind == "DATA_QUALITY_FAILURE":
        return "Synthetic review with an intentionally malformed source field."
    return _REVIEW_TEXT[(index + SEED) % len(_REVIEW_TEXT)]


def _return_reason(truth: dict[str, Any], index: int) -> str:
    family = truth["defect_family_concept"]
    kind = truth["truth_kind"]
    if family is not None:
        options = _FAMILY_TEXT[family]
        return f"Returning the item because {options[(index + SEED) % len(options)].lower()}"
    if kind == "NON_DEFECT":
        return _RETURN_REASONS[(index + SEED) % len(_RETURN_REASONS)]
    if kind == "AMBIGUOUS":
        return "The item may be slightly uneven, but I am not certain it is defective."
    if kind == "LATE_ARRIVAL":
        return "The parcel arrived after the planned date; the item is intact."
    if kind == "DATA_QUALITY_FAILURE":
        return "Synthetic return with an intentionally malformed source field."
    return "The item was returned unused; no product issue was reported."


def _write_sources(output_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    truth_rows: list[dict[str, Any]] = []
    truth_kind_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    quality_counts: Counter[str] = Counter()
    linkage_pending_count = 0
    observed_dates: dict[str, set[str]] = {"REVIEW": set(), "RETURN": set()}

    file_definitions = (
        ("REVIEW", "reviews.csv", REVIEW_FIELDS),
        ("RETURN", "returns.csv", RETURN_FIELDS),
    )
    for source_type, filename, fields in file_definitions:
        with (output_dir / filename).open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for index in range(RECORDS_PER_SOURCE):
                truth = _record_truth(index, source_type)
                product_id, supplier_id, batch_id = _product_links(index, truth)
                event_text = truth["event_time_utc"] or "not-a-timestamp"
                quality_fixture = truth["quality_fixture"]

                if source_type == "REVIEW":
                    text = _review_text(truth, index)
                    if quality_fixture == "MISSING_TEXT":
                        text = ""
                    row = {
                        "review_id": truth["source_record_id"],
                        "product_id": product_id,
                        "supplier_id": supplier_id,
                        "batch_id": batch_id,
                        "review_timestamp": event_text,
                        "review_text": text,
                        "rating": str(1 + ((index + SEED) % 5)),
                        "source": SOURCES[(index + SEED) % len(SOURCES)],
                    }
                else:
                    reason = _return_reason(truth, index)
                    if quality_fixture == "MISSING_TEXT":
                        reason = ""
                    row = {
                        "return_id": truth["source_record_id"],
                        "product_id": product_id,
                        "supplier_id": supplier_id,
                        "batch_id": batch_id,
                        "return_timestamp": event_text,
                        "return_reason": reason,
                        "return_quantity": "0" if quality_fixture else str(1 + (index % 3)),
                        "return_category": "",
                    }

                writer.writerow(row)
                truth_rows.append(truth)
                truth_kind_counts[truth["truth_kind"]] += 1
                if truth["defect_family_concept"] is not None:
                    family_counts[truth["defect_family_concept"]] += 1
                if quality_fixture:
                    quality_counts[quality_fixture] += 1
                if not truth["linkage_complete"]:
                    linkage_pending_count += 1
                event_time = truth["event_time_utc"]
                if event_time:
                    observed_dates[source_type].add(event_time[:10])

    summary = {
        "record_count": len(truth_rows),
        "source_counts": {"REVIEW": RECORDS_PER_SOURCE, "RETURN": RECORDS_PER_SOURCE},
        "truth_kind_counts": dict(sorted(truth_kind_counts.items())),
        "defect_family_concept_counts": dict(sorted(family_counts.items())),
        "quality_fixture_counts": dict(sorted(quality_counts.items())),
        "linkage_pending_fixture_count": linkage_pending_count,
        "valid_utc_event_dates_by_source": {
            source_type: len(dates) for source_type, dates in sorted(observed_dates.items())
        },
    }
    return truth_rows, summary


def _write_truth(output_dir: Path, truth_rows: list[dict[str, Any]]) -> None:
    path = output_dir / "fixture_truth.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in truth_rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            file.write("\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_dataset(output_dir: Path) -> dict[str, Any]:
    """Write the fixed 10,000-record development corpus and its separate truth manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    truth_rows, summary = _write_sources(output_dir)
    _write_truth(output_dir, truth_rows)

    event_end = BASE_EVENT_TIME + timedelta(days=EVENT_DAYS)
    coverage_truth = []
    for source_type, feed_name in (("REVIEW", "synthetic-review-feed"), ("RETURN", "synthetic-return-feed")):
        coverage_truth.append(
            {
                "source_type": source_type,
                "source_feed_id": feed_name,
                "scope": "one synthetic retailer source feed; generated fixture truth only",
                "event_time_start_utc": _utc_text(BASE_EVENT_TIME),
                "event_time_end_exclusive_utc": _utc_text(event_end),
                "declared_coverage_truth": "COMPLETE_FOR_FIXTURE",
                "valid_utc_event_dates_observed": summary["valid_utc_event_dates_by_source"][source_type],
                "policy_note": "Not a DAI-06 sufficiency or detection-eligibility decision.",
            }
        )

    source_files = ("reviews.csv", "returns.csv", "fixture_truth.jsonl")
    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "generator": "productpulse.datasets.generate",
        "generator_version": GENERATOR_VERSION,
        "deterministic_seed": SEED,
        "dataset_scope": "development-only synthetic source data",
        "source_text_provenance": "deterministic built-in templates; no customer or public-source text",
        "record_count": summary["record_count"],
        "source_counts": summary["source_counts"],
        "event_time_start_utc": _utc_text(BASE_EVENT_TIME),
        "event_time_end_exclusive_utc": _utc_text(event_end),
        "event_time_days": EVENT_DAYS,
        "truth_summary": {
            "fixture_truth_kind_counts": summary["truth_kind_counts"],
            "defect_family_concept_counts": summary["defect_family_concept_counts"],
            "quality_fixture_counts": summary["quality_fixture_counts"],
            "linkage_pending_fixture_count": summary["linkage_pending_fixture_count"],
        },
        "coverage_truth": coverage_truth,
        "classification_taxonomy": {
            "status": "not_assigned",
            "note": "The initial taxonomy seed remains unapproved per PP-005 and AI_SPEC v1.0; PRD family concepts here are scenario truth, not classifier labels or codes.",
        },
        "holdout": {
            "final_holdout_locked": False,
            "membership": None,
            "note": "This artifact is development data only; no final evaluation holdout is created or locked.",
        },
        "files": {
            name: {"sha256": _sha256(output_dir / name)} for name in source_files
        },
    }
    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(manifest, file, ensure_ascii=False, sort_keys=True, indent=2)
        file.write("\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/dev"))
    arguments = parser.parse_args()
    manifest = generate_dataset(arguments.output)
    print(
        f"Generated {manifest['record_count']} development records "
        f"across {manifest['event_time_days']} UTC days; final holdout locked: "
        f"{manifest['holdout']['final_holdout_locked']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

