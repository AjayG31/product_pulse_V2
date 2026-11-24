"""Idempotent, evidence-only source aggregate recomputation handler."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from productpulse.api_common import safe_audit
from productpulse.models import AuditEvent, BackgroundJob, Feedback, FeedbackLinkageEvent
from productpulse.worker_runtime import (
    ClaimedJob,
    HandlerRegistration,
    JobResult,
    RetrySafety,
)


def _source_snapshot(rows: list[Feedback]) -> tuple[str, dict[str, int | None]]:
    source_facts = [
        {
            "feedback_id": row.feedback_id,
            "payload_sha256": row.payload_sha256,
            "source_type": row.source_type,
            "event_time_utc": row.event_time_utc,
            "linkage_status": row.linkage_status,
            "supplier_id": row.supplier_id,
            "batch_id": row.batch_id,
            "return_quantity": row.return_quantity,
        }
        for row in rows
    ]
    encoded = json.dumps(source_facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    linked = [row for row in rows if row.linkage_status == "LINKED"]
    pending = [row for row in rows if row.linkage_status == "LINKAGE_PENDING"]
    returns = [row for row in linked if row.source_type == "RETURN"]
    pending_returns = [row for row in pending if row.source_type == "RETURN"]
    linked_units = [row.return_quantity for row in returns if row.return_quantity is not None]
    pending_units = [row.return_quantity for row in pending_returns if row.return_quantity is not None]
    return hashlib.sha256(encoded).hexdigest(), {
        "feedback_records": len(rows),
        "linked_feedback_records": len(linked),
        "linkage_pending_feedback_records": len(pending),
        "linked_return_records": len(returns),
        "linked_returned_units": sum(linked_units) if linked_units else (0 if not returns else None),
        "linkage_pending_return_records": len(pending_returns),
        "linkage_pending_returned_units": sum(pending_units) if pending_units else (0 if not pending_returns else None),
    }


def build_reconciliation_handler(engine: Engine):
    def handle(claimed: ClaimedJob) -> JobResult:
        try:
            with Session(engine, expire_on_commit=False) as db:
                db.execute(text("BEGIN IMMEDIATE"))
                job = db.get(BackgroundJob, claimed.background_job_id)
                event = db.scalar(select(FeedbackLinkageEvent).where(
                    FeedbackLinkageEvent.recompute_job_id == claimed.background_job_id
                ))
                if (
                    job is None
                    or job.job_type != "RECONCILIATION"
                    or job.status != "RUNNING"
                    or job.worker_id != claimed.worker_id
                    or job.lease_token != claimed.lease_token
                    or event is None
                ):
                    db.rollback()
                    return JobResult.failed(RetrySafety.PERMANENT, "RECONCILIATION_SOURCE_MISSING")
                prior = db.scalar(select(AuditEvent).where(
                    AuditEvent.action == "HISTORICAL_AGGREGATE_RECOMPUTED",
                    AuditEvent.resource_type == "RECONCILIATION_JOB",
                    AuditEvent.resource_id == claimed.background_job_id,
                ))
                if prior is not None:
                    db.commit()
                    return JobResult.succeeded()
                feedback = db.get(Feedback, event.feedback_id)
                if feedback is None:
                    db.rollback()
                    return JobResult.failed(RetrySafety.PERMANENT, "RECONCILIATION_SOURCE_MISSING")
                rows = db.scalars(
                    select(Feedback).where(Feedback.product_id == feedback.product_id).order_by(Feedback.feedback_id)
                ).all()
                source_fingerprint, counts = _source_snapshot(rows)
                safe_audit(
                    db,
                    action="HISTORICAL_AGGREGATE_RECOMPUTED",
                    resource_type="RECONCILIATION_JOB",
                    resource_id=claimed.background_job_id,
                    actor_user_id=None,
                    after={
                        "feedback_linkage_event_id": event.linkage_event_id,
                        "product_id": feedback.product_id,
                        "taxonomy_version_id": None,
                        "coverage_state": "UNKNOWN",
                        "evaluation_mode": "HISTORICAL_RECOMPUTE",
                        "incident_application_state": "NOT_APPLICABLE",
                        "source_fingerprint": source_fingerprint,
                        **counts,
                    },
                )
                db.commit()
                return JobResult.succeeded()
        except OperationalError as error:
            code = getattr(error.orig, "sqlite_errorcode", None)
            if code is not None and (code & 0xFF) == sqlite3.SQLITE_BUSY:
                return JobResult.retryable(RetrySafety.KNOWN_SAFE_TRANSIENT, "SQLITE_BUSY")
            return JobResult.failed(RetrySafety.UNKNOWN, "RECOMPUTE_OUTCOME_UNKNOWN")
        except Exception:
            return JobResult.failed(RetrySafety.UNKNOWN, "RECOMPUTE_OUTCOME_UNKNOWN")

    return handle


def reconciliation_registration(engine: Engine) -> HandlerRegistration:
    return HandlerRegistration(handle=build_reconciliation_handler(engine), safe_retry_after_abandon=True)
