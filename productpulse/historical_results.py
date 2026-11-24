"""Fail-closed persistence for explicitly versioned historical results."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from productpulse.api_common import ApiError
from productpulse.models import BackgroundJob, DefectCluster, DetectionResult, DetectionRuleVersion, TaxonomyVersion
from productpulse.security.sessions import utc_text


def _contains_source_text(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in {"feedback_text", "source_text", "raw_feedback", "evidence_excerpt"}:
                return True
            if _contains_source_text(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_source_text(child) for child in value)
    return False


def canonical_result_snapshot(
    *,
    taxonomy_version_id: str,
    rule_version: str,
    coverage_policy_version: str,
    snapshot_inputs: dict[str, object],
) -> tuple[str, str]:
    """Return canonical immutable fingerprint inputs and SHA-256 result key."""

    if not taxonomy_version_id or not rule_version or not coverage_policy_version:
        raise ValueError("historical result versions must be explicit")
    supplied_version = snapshot_inputs.get("taxonomy_version_id")
    if supplied_version is not None and supplied_version != taxonomy_version_id:
        raise ValueError("snapshot taxonomy version does not match the selected context")
    if _contains_source_text(snapshot_inputs):
        raise ValueError("result snapshots cannot contain source text")
    payload = {
        **snapshot_inputs,
        "taxonomy_version_id": taxonomy_version_id,
        "rule_version": rule_version,
        "coverage_policy_version": coverage_policy_version,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def persist_historical_result(
    db: Session,
    *,
    taxonomy_version_id: str,
    rule_version: str,
    background_job_id: str,
    cluster_id: str,
    coverage_policy_version: str,
    evaluated_at: str,
    observed_start_utc: str,
    observed_end_utc: str,
    baseline_start_utc: str,
    baseline_end_utc: str,
    observed_count: int,
    baseline_28d_count: int,
    observed_classification_assessed_count: int,
    observed_classification_complete_count: int,
    baseline_classification_assessed_count: int,
    baseline_classification_complete_count: int,
    snapshot_inputs: dict[str, object],
) -> DetectionResult:
    """Persist only historical, UNKNOWN-coverage results; current detection stays gated."""

    taxonomy = db.get(TaxonomyVersion, taxonomy_version_id)
    rule = db.get(DetectionRuleVersion, rule_version)
    job = db.get(BackgroundJob, background_job_id)
    cluster = db.get(DefectCluster, cluster_id)
    if taxonomy is None:
        raise ApiError(422, "TAXONOMY_VERSION_INVALID", "Choose an existing taxonomy version.", "Validation failed")
    if rule is None or rule.taxonomy_version_id != taxonomy_version_id:
        raise ApiError(409, "DETECTION_CONTEXT_MISMATCH", "The rule does not match the explicit taxonomy context.", "Conflict")
    if (
        job is None
        or job.job_type != "DETECTION"
        or job.taxonomy_version_id != taxonomy_version_id
        or job.status != "RUNNING"
        or job.max_attempts != 3
    ):
        raise ApiError(409, "DETECTION_JOB_CONTEXT_MISMATCH", "The durable job does not match the explicit taxonomy context.", "Conflict")
    if cluster is None:
        raise ApiError(404, "DEFECT_CLUSTER_NOT_FOUND", "The saved aggregate context was not found.", "Not found")
    if min(
        observed_count,
        baseline_28d_count,
        observed_classification_assessed_count,
        observed_classification_complete_count,
        baseline_classification_assessed_count,
        baseline_classification_complete_count,
    ) < 0:
        raise ApiError(422, "DETECTION_COUNTS_INVALID", "Historical aggregate counts are invalid.", "Validation failed")
    if (
        observed_classification_complete_count > observed_classification_assessed_count
        or baseline_classification_complete_count > baseline_classification_assessed_count
    ):
        raise ApiError(422, "DETECTION_COUNTS_INVALID", "Historical classification counts are invalid.", "Validation failed")
    if not (observed_start_utc < observed_end_utc and baseline_start_utc < baseline_end_utc):
        raise ApiError(422, "DETECTION_WINDOW_INVALID", "The saved aggregate windows are invalid.", "Validation failed")

    snapshot_text, result_key = canonical_result_snapshot(
        taxonomy_version_id=taxonomy_version_id,
        rule_version=rule_version,
        coverage_policy_version=coverage_policy_version,
        snapshot_inputs={
            **snapshot_inputs,
            "cluster_id": cluster_id,
            "observed_window": {"start_utc": observed_start_utc, "end_utc": observed_end_utc},
            "baseline_window": {"start_utc": baseline_start_utc, "end_utc": baseline_end_utc},
            "observed_count": observed_count,
            "baseline_28d_count": baseline_28d_count,
            "observed_classification_assessed_count": observed_classification_assessed_count,
            "observed_classification_complete_count": observed_classification_complete_count,
            "baseline_classification_assessed_count": baseline_classification_assessed_count,
            "baseline_classification_complete_count": baseline_classification_complete_count,
        },
    )
    result = DetectionResult(
        detection_result_id=f"det_{uuid.uuid4().hex}",
        result_key=result_key,
        result_input_snapshot_text=snapshot_text,
        cluster_id=cluster_id,
        taxonomy_version_id=taxonomy_version_id,
        background_job_id=background_job_id,
        rule_version=rule_version,
        coverage_policy_version=coverage_policy_version,
        evaluation_mode="HISTORICAL_RECOMPUTE",
        evaluated_at=evaluated_at,
        observed_start_utc=observed_start_utc,
        observed_end_utc=observed_end_utc,
        baseline_start_utc=baseline_start_utc,
        baseline_end_utc=baseline_end_utc,
        observed_count=observed_count,
        baseline_28d_count=baseline_28d_count,
        normalized_baseline_7d=None,
        observed_to_baseline_ratio=None,
        coverage_state="INSUFFICIENT",
        baseline_source_coverage_state="UNKNOWN",
        observed_classification_coverage_state="UNKNOWN",
        observed_classification_assessed_count=observed_classification_assessed_count,
        observed_classification_complete_count=observed_classification_complete_count,
        baseline_classification_coverage_state="UNKNOWN",
        baseline_classification_assessed_count=baseline_classification_assessed_count,
        baseline_classification_complete_count=baseline_classification_complete_count,
        decision_state="INSUFFICIENT_COVERAGE",
        severity=None,
        incident_application_state="NOT_APPLICABLE",
        created_at=utc_text(datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))),
    )
    db.add(result)
    db.flush()
    return result
