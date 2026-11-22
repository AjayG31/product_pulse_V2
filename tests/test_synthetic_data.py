import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from productpulse.datasets.generate import FAMILIES, generate_dataset


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def _read_truth(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def test_generator_is_byte_reproducible(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_dataset(first)
    generate_dataset(second)

    for name in ("reviews.csv", "returns.csv", "fixture_truth.jsonl", "manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_corpus_has_prd_source_fields_and_10000_records_across_35_days(tmp_path):
    output = tmp_path / "corpus"
    manifest = generate_dataset(output)
    review_fields, reviews = _read_csv(output / "reviews.csv")
    return_fields, returns = _read_csv(output / "returns.csv")

    assert review_fields == [
        "review_id", "product_id", "supplier_id", "batch_id", "review_timestamp",
        "review_text", "rating", "source",
    ]
    assert return_fields == [
        "return_id", "product_id", "supplier_id", "batch_id", "return_timestamp",
        "return_reason", "return_quantity", "return_category",
    ]
    assert len(reviews) == 5_000
    assert len(returns) == 5_000
    assert manifest["record_count"] == 10_000
    assert manifest["source_counts"] == {"REVIEW": 5_000, "RETURN": 5_000}
    review_ids = [row["review_id"] for row in reviews]
    return_ids = [row["return_id"] for row in returns]
    assert len(set(review_ids)) == len(review_ids)
    assert len(set(return_ids)) == len(return_ids)
    assert review_ids[0] == "REV-000001" and review_ids[-1] == "REV-005000"
    assert return_ids[0] == "RET-000001" and return_ids[-1] == "RET-005000"

    review_days = {
        datetime.fromisoformat(row["review_timestamp"].replace("Z", "+00:00")).date().isoformat()
        for row in reviews
        if row["review_timestamp"] != "not-a-timestamp"
    }
    return_days = {
        datetime.fromisoformat(row["return_timestamp"].replace("Z", "+00:00")).date().isoformat()
        for row in returns
        if row["return_timestamp"] != "not-a-timestamp"
    }
    assert len(review_days) == 35
    assert len(return_days) == 35
    assert manifest["event_time_days"] == 35


def test_manifest_records_fixture_coverage_without_approving_calibration(tmp_path):
    output = tmp_path / "corpus"
    manifest = generate_dataset(output)

    assert len(manifest["coverage_truth"]) == 2
    for coverage in manifest["coverage_truth"]:
        assert coverage["declared_coverage_truth"] == "COMPLETE_FOR_FIXTURE"
        assert coverage["event_time_start_utc"] == "2025-01-01T00:00:00Z"
        assert coverage["event_time_end_exclusive_utc"] == "2025-02-05T00:00:00Z"
        assert coverage["valid_utc_event_dates_observed"] == 35
        assert "Not a DAI-06 sufficiency" in coverage["policy_note"]


def test_truth_is_separate_and_pending_taxonomy_and_holdout_are_not_activated(tmp_path):
    output = tmp_path / "corpus"
    manifest = generate_dataset(output)
    review_fields, _ = _read_csv(output / "reviews.csv")
    return_fields, _ = _read_csv(output / "returns.csv")
    truth = _read_truth(output / "fixture_truth.jsonl")

    assert not any("truth" in name or "scenario" in name or "taxonomy" in name for name in review_fields)
    assert not any("truth" in name or "scenario" in name or "taxonomy" in name for name in return_fields)
    assert len(truth) == 10_000
    assert manifest["holdout"]["final_holdout_locked"] is False
    assert manifest["holdout"]["membership"] is None
    assert manifest["classification_taxonomy"]["status"] == "not_assigned"
    assert all("category_code" not in row for row in truth)

    kinds = Counter(str(row["truth_kind"]) for row in truth)
    assert {"NORMAL", "PLANTED_DEFECT", "NON_DEFECT", "AMBIGUOUS", "LATE_ARRIVAL", "DATA_QUALITY_FAILURE"} <= set(kinds)
    families = {str(row["defect_family_concept"]) for row in truth if row["defect_family_concept"]}
    assert families == set(FAMILIES)
    assert all("DEV-SCN-" in str(row["scenario_id"]) for row in truth if row["truth_kind"] == "PLANTED_DEFECT")
    late_rows = [row for row in truth if row["late_arrival"] is True]
    assert late_rows
    for row in late_rows:
        event_time = datetime.fromisoformat(str(row["event_time_utc"]).replace("Z", "+00:00"))
        ingested_at = datetime.fromisoformat(str(row["ingested_at_utc"]).replace("Z", "+00:00"))
        assert ingested_at - event_time == timedelta(days=3)


def test_quality_and_unresolved_link_fixtures_are_truth_only_metadata(tmp_path):
    output = tmp_path / "corpus"
    generate_dataset(output)
    _, reviews = _read_csv(output / "reviews.csv")
    _, returns = _read_csv(output / "returns.csv")
    source_rows = {
        row["review_id"]: row for row in reviews
    } | {
        row["return_id"]: row for row in returns
    }
    truth = _read_truth(output / "fixture_truth.jsonl")

    quality_rows = [row for row in truth if row["quality_fixture"]]
    assert {row["quality_fixture"] for row in quality_rows} == {"MISSING_TEXT", "INVALID_EVENT_TIME"}
    for row in quality_rows:
        source = source_rows[str(row["source_record_id"])]
        if row["quality_fixture"] == "INVALID_EVENT_TIME":
            timestamp_field = "review_timestamp" if row["source_type"] == "REVIEW" else "return_timestamp"
            assert source[timestamp_field] == "not-a-timestamp"
        else:
            text_field = "review_text" if row["source_type"] == "REVIEW" else "return_reason"
            assert source[text_field] == ""

    unresolved = [row for row in truth if row["linkage_complete"] is False]
    assert unresolved
    for row in unresolved:
        source = source_rows[str(row["source_record_id"])]
        assert source["supplier_id"] == ""
        assert source["batch_id"] == ""


def test_manifest_hashes_match_generated_files_and_text_is_synthetic(tmp_path):
    output = tmp_path / "corpus"
    manifest = generate_dataset(output)

    for filename, expected in manifest["files"].items():
        digest = hashlib.sha256((output / filename).read_bytes()).hexdigest()
        assert digest == expected["sha256"]

    _, reviews = _read_csv(output / "reviews.csv")
    _, returns = _read_csv(output / "returns.csv")
    assert all("@" not in row["review_text"] for row in reviews)
    assert all("@" not in row["return_reason"] for row in returns)

