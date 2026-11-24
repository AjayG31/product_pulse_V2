"""Durable SQLite worker claims, leases, retries, and recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import logging
import re
import secrets
import sqlite3
import threading
from typing import Callable, Literal, Mapping

from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from productpulse.models import BackgroundJob, BackgroundJobAttempt


LOGGER = logging.getLogger(__name__)

SQLITE_BUSY_RETRIES = 2
WORKER_POLL_SECONDS = 5
WORKER_RECONCILE_SECONDS = 60
WORKER_LEASE_SECONDS = 5 * 60
WORKER_LEASE_RENEWAL_SECONDS = 60
RETRY_DELAYS_SECONDS = (5, 15, 45)
APPROVED_MAX_ATTEMPTS = {
    "CLASSIFICATION": 3,
    "INGESTION": 3,
    "RECONCILIATION": 3,
    "DETECTION": 3,
}


class RetrySafety(StrEnum):
    KNOWN_SAFE_TRANSIENT = "KNOWN_SAFE_TRANSIENT"
    SAFE_REPLAY = "SAFE_REPLAY"
    UNKNOWN = "UNKNOWN"
    PERMANENT = "PERMANENT"


@dataclass(frozen=True)
class JobResult:
    status: Literal["SUCCEEDED", "PARTIAL", "RETRYABLE_FAILURE", "TERMINAL_FAILURE"]
    retry_safety: RetrySafety | None = None
    error_code: str | None = None

    @classmethod
    def succeeded(cls) -> "JobResult":
        return cls("SUCCEEDED")

    @classmethod
    def partial(cls) -> "JobResult":
        return cls("PARTIAL")

    @classmethod
    def retryable(
        cls,
        retry_safety: RetrySafety,
        error_code: str = "KNOWN_TRANSIENT_FAILURE",
    ) -> "JobResult":
        return cls("RETRYABLE_FAILURE", retry_safety, error_code)

    @classmethod
    def failed(
        cls,
        retry_safety: RetrySafety = RetrySafety.PERMANENT,
        error_code: str = "WORKER_FAILURE",
    ) -> "JobResult":
        return cls("TERMINAL_FAILURE", retry_safety, error_code)


@dataclass(frozen=True)
class ClaimedJob:
    background_job_id: str
    job_type: str
    work_key: str
    ingestion_job_id: str | None
    attempt_number: int
    worker_id: str
    lease_token: str


@dataclass(frozen=True)
class HandlerRegistration:
    handle: Callable[[ClaimedJob], JobResult | None]
    safe_retry_after_abandon: bool = False


class StaleLeaseError(RuntimeError):
    """Raised when a worker no longer owns a claimed job."""


class WorkerStateError(RuntimeError):
    """Raised when persisted worker state violates the attempt contract."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("UTC timestamps must include a timezone.")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def retry_delay_seconds(claim_number: int) -> int:
    if claim_number < 1:
        raise ValueError("Claim number must be positive.")
    return RETRY_DELAYS_SECONDS[min(claim_number - 1, len(RETRY_DELAYS_SECONDS) - 1)]


def _is_sqlite_busy(error: OperationalError) -> bool:
    code = getattr(error.orig, "sqlite_errorcode", None)
    if code is not None:
        return (code & 0xFF) == sqlite3.SQLITE_BUSY
    message = str(error.orig).strip().lower()
    return message in {"database is locked", "database is busy", "sqlite_busy"}


def _run_write_unit(engine: Engine, operation: Callable[[Session], object]) -> object:
    """Run one idempotent write unit, retrying only SQLite BUSY after rollback."""

    for retry_number in range(SQLITE_BUSY_RETRIES + 1):
        with Session(engine, expire_on_commit=False) as session:
            try:
                session.execute(text("BEGIN IMMEDIATE"))
                result = operation(session)
                session.commit()
                return result
            except OperationalError as error:
                session.rollback()
                if not _is_sqlite_busy(error) or retry_number >= SQLITE_BUSY_RETRIES:
                    raise
            except Exception:
                session.rollback()
                raise
    raise RuntimeError("SQLite write retry loop ended unexpectedly.")


def _safe_error_code(error_code: str | None) -> str:
    if error_code and re.fullmatch(r"[A-Z0-9_]{1,80}", error_code):
        return error_code
    return "WORKER_FAILURE"


def _safe_error_summary(result: JobResult) -> str:
    if result.retry_safety is RetrySafety.KNOWN_SAFE_TRANSIENT:
        return "A known safe transient failure occurred while processing this job."
    if result.retry_safety is RetrySafety.SAFE_REPLAY:
        return "Replay-safe work did not complete and may be attempted again."
    if result.retry_safety is RetrySafety.UNKNOWN:
        return "The job outcome could not be verified; automatic replay was not scheduled."
    return "The worker could not complete this job."


def _may_retry(job: BackgroundJob, result: JobResult) -> bool:
    if result.status != "RETRYABLE_FAILURE":
        return False
    if job.max_attempts is None or job.attempt_count >= job.max_attempts:
        return False
    if job.job_type == "INGESTION":
        return result.retry_safety is RetrySafety.SAFE_REPLAY
    if job.job_type in {"CLASSIFICATION", "RECONCILIATION", "DETECTION"}:
        return result.retry_safety is RetrySafety.KNOWN_SAFE_TRANSIENT
    return False


def claim_one(
    engine: Engine,
    *,
    worker_id: str,
    eligible_job_types: set[str] | frozenset[str],
    now: datetime | None = None,
) -> ClaimedJob | None:
    """Atomically claim one registered, budgeted job and create its attempt."""

    eligible_types = frozenset(eligible_job_types).intersection(APPROVED_MAX_ATTEMPTS)
    if not eligible_types:
        return None
    if not worker_id or len(worker_id) > 128:
        raise ValueError("Worker identity is invalid.")
    current_dt = now or utc_now()
    current = format_utc(current_dt)
    lease_expires_at = format_utc(current_dt + timedelta(seconds=WORKER_LEASE_SECONDS))
    token = secrets.token_urlsafe(32)

    def claim(session: Session) -> ClaimedJob | None:
        due = or_(
            and_(BackgroundJob.status == "QUEUED", BackgroundJob.scheduled_at <= current),
            and_(
                BackgroundJob.status == "RETRY_WAIT",
                BackgroundJob.next_attempt_at.is_not(None),
                BackgroundJob.next_attempt_at <= current,
            ),
        )
        job = session.scalar(
            select(BackgroundJob)
            .where(
                BackgroundJob.job_type.in_(eligible_types),
                BackgroundJob.job_type != "BATCH_POLL",
                BackgroundJob.max_attempts.is_not(None),
                BackgroundJob.max_attempts == 3,
                BackgroundJob.attempt_count < BackgroundJob.max_attempts,
                due,
            )
            .order_by(BackgroundJob.scheduled_at, BackgroundJob.created_at, BackgroundJob.background_job_id)
            .limit(1)
        )
        if job is None:
            return None

        attempt_number = job.attempt_count + 1
        job.status = "RUNNING"
        job.attempt_count = attempt_number
        job.worker_id = worker_id
        job.lease_token = token
        job.lease_expires_at = lease_expires_at
        job.next_attempt_at = None
        job.started_at = job.started_at or current
        session.add(
            BackgroundJobAttempt(
                background_job_id=job.background_job_id,
                attempt_number=attempt_number,
                worker_id=worker_id,
                claimed_at=current,
                finished_at=None,
                outcome="IN_PROGRESS",
                error_code=None,
                safe_error_summary=None,
                next_attempt_at=None,
            )
        )
        session.flush()
        return ClaimedJob(
            background_job_id=job.background_job_id,
            job_type=job.job_type,
            work_key=job.work_key,
            ingestion_job_id=job.ingestion_job_id,
            attempt_number=attempt_number,
            worker_id=worker_id,
            lease_token=token,
        )

    return _run_write_unit(engine, claim)  # type: ignore[return-value]


def renew_lease(
    engine: Engine,
    claimed: ClaimedJob,
    *,
    now: datetime | None = None,
) -> bool:
    current_dt = now or utc_now()
    current = format_utc(current_dt)
    expires = format_utc(current_dt + timedelta(seconds=WORKER_LEASE_SECONDS))

    def renew(session: Session) -> bool:
        result = session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.background_job_id == claimed.background_job_id,
                BackgroundJob.status == "RUNNING",
                BackgroundJob.worker_id == claimed.worker_id,
                BackgroundJob.lease_token == claimed.lease_token,
                BackgroundJob.lease_expires_at > current,
            )
            .values(lease_expires_at=expires)
        )
        return result.rowcount == 1

    return bool(_run_write_unit(engine, renew))


def finish_attempt(
    engine: Engine,
    claimed: ClaimedJob,
    result: JobResult,
    *,
    now: datetime | None = None,
) -> str:
    """Persist a result only while the job's current lease token still matches."""

    current = format_utc(now or utc_now())
    status = result.status
    error_code = _safe_error_code(result.error_code)
    safe_summary = _safe_error_summary(result)

    def finish(session: Session) -> str:
        job = session.get(BackgroundJob, claimed.background_job_id)
        if (
            job is None
            or job.status != "RUNNING"
            or job.worker_id != claimed.worker_id
            or job.lease_token != claimed.lease_token
            or job.attempt_count != claimed.attempt_number
            or job.lease_expires_at is None
            or job.lease_expires_at <= current
        ):
            raise StaleLeaseError("The worker no longer owns this job.")
        attempt = session.get(
            BackgroundJobAttempt,
            (claimed.background_job_id, claimed.attempt_number),
        )
        if attempt is None or attempt.outcome != "IN_PROGRESS":
            raise WorkerStateError("The current job attempt is not in progress.")

        schedule_retry = _may_retry(job, result)
        if schedule_retry:
            next_attempt = format_utc(
                (now or utc_now()) + timedelta(seconds=retry_delay_seconds(claimed.attempt_number))
            )
            attempt.outcome = "RETRYABLE_FAILURE"
            attempt.finished_at = current
            attempt.error_code = error_code
            attempt.safe_error_summary = safe_summary
            attempt.next_attempt_at = next_attempt
            job.status = "RETRY_WAIT"
            job.next_attempt_at = next_attempt
            job.completed_at = None
        else:
            attempt.outcome = "SUCCEEDED" if status in {"SUCCEEDED", "PARTIAL"} else "TERMINAL_FAILURE"
            attempt.finished_at = current
            attempt.error_code = None if status in {"SUCCEEDED", "PARTIAL"} else error_code
            attempt.safe_error_summary = None if status in {"SUCCEEDED", "PARTIAL"} else safe_summary
            attempt.next_attempt_at = None
            job.status = "PARTIAL" if status == "PARTIAL" else "COMPLETED" if status == "SUCCEEDED" else "FAILED"
            job.completed_at = current
            job.next_attempt_at = None

        if status not in {"SUCCEEDED", "PARTIAL"}:
            job.last_error_code = error_code
            job.last_error_summary = safe_summary
        else:
            job.last_error_code = None
            job.last_error_summary = None
        job.worker_id = None
        job.lease_token = None
        job.lease_expires_at = None
        return job.status

    return str(_run_write_unit(engine, finish))


def reconcile_expired_leases(
    engine: Engine,
    *,
    now: datetime | None = None,
    safe_retry_job_types: set[str] | frozenset[str] = frozenset(),
) -> int:
    """Finalize expired claims and replay only explicitly safe job types."""

    current_dt = now or utc_now()
    current = format_utc(current_dt)
    safe_types = frozenset(safe_retry_job_types).intersection(APPROVED_MAX_ATTEMPTS)

    def reconcile(session: Session) -> int:
        expired_jobs = list(
            session.scalars(
                select(BackgroundJob)
                .where(
                    BackgroundJob.status == "RUNNING",
                    BackgroundJob.lease_expires_at.is_not(None),
                    BackgroundJob.lease_expires_at <= current,
                )
                .order_by(BackgroundJob.lease_expires_at, BackgroundJob.background_job_id)
            )
        )
        for job in expired_jobs:
            attempt = session.get(BackgroundJobAttempt, (job.background_job_id, job.attempt_count))
            if attempt is None or attempt.outcome != "IN_PROGRESS":
                raise WorkerStateError("Expired job has no active persisted attempt.")
            attempt.outcome = "ABANDONED"
            attempt.finished_at = current
            attempt.error_code = "WORKER_LEASE_EXPIRED"
            attempt.safe_error_summary = "The worker lease expired without a persisted result."
            attempt.next_attempt_at = None
            job.last_error_code = "WORKER_LEASE_EXPIRED"
            job.last_error_summary = attempt.safe_error_summary

            should_replay = (
                job.job_type in safe_types
                and job.max_attempts is not None
                and job.max_attempts == APPROVED_MAX_ATTEMPTS.get(job.job_type)
                and job.attempt_count < job.max_attempts
            )
            if should_replay:
                job.status = "RETRY_WAIT"
                job.next_attempt_at = format_utc(
                    current_dt + timedelta(seconds=retry_delay_seconds(job.attempt_count))
                )
                job.completed_at = None
            else:
                job.status = "FAILED"
                job.next_attempt_at = None
                job.completed_at = current
            job.worker_id = None
            job.lease_token = None
            job.lease_expires_at = None
        return len(expired_jobs)

    return int(_run_write_unit(engine, reconcile))


class WorkerRuntime:
    """One polling worker sharing the API's SQLite engine settings."""

    def __init__(
        self,
        engine: Engine,
        handlers: Mapping[str, HandlerRegistration] | None = None,
        *,
        worker_id: str | None = None,
        clock: Callable[[], datetime] = utc_now,
        poll_seconds: float = WORKER_POLL_SECONDS,
        reconcile_seconds: float = WORKER_RECONCILE_SECONDS,
        lease_renewal_seconds: float = WORKER_LEASE_RENEWAL_SECONDS,
    ) -> None:
        self.engine = engine
        self.handlers = dict(handlers or {})
        self.worker_id = worker_id or f"worker_{secrets.token_hex(16)}"
        self.clock = clock
        self.poll_seconds = poll_seconds
        self.reconcile_seconds = reconcile_seconds
        self.lease_renewal_seconds = lease_renewal_seconds
        self._last_reconcile: datetime | None = None
        self._reconcile_lock = threading.Lock()

    def _reconcile_if_due(self, current: datetime) -> int:
        with self._reconcile_lock:
            if self._last_reconcile is not None and (
                current - self._last_reconcile
            ).total_seconds() < self.reconcile_seconds:
                return 0
            safe_types = {
                job_type
                for job_type, registration in self.handlers.items()
                if registration.safe_retry_after_abandon
            }
            count = reconcile_expired_leases(
                self.engine,
                now=current,
                safe_retry_job_types=safe_types,
            )
            self._last_reconcile = current
            return count

    def _run_claimed(self, claimed: ClaimedJob, registration: HandlerRegistration) -> None:
        stopped = threading.Event()
        lease_lost = threading.Event()

        def maintain_lease() -> None:
            while not stopped.wait(self.lease_renewal_seconds):
                current = self.clock()
                try:
                    renewed = renew_lease(self.engine, claimed, now=current)
                except Exception:
                    lease_lost.set()
                    LOGGER.error("worker_lease_renewal_failed; code=lease_renewal_failed")
                    return
                if not renewed:
                    lease_lost.set()
                    LOGGER.warning(
                        "worker_lease_lost; background_job_id=%s; attempt=%s",
                        claimed.background_job_id,
                        claimed.attempt_number,
                    )
                    return
                try:
                    self._reconcile_if_due(current)
                except Exception:
                    LOGGER.error("worker_reconciliation_failed; code=reconciliation_failed")

        heartbeat = threading.Thread(target=maintain_lease, name="worker-lease-renewal", daemon=True)
        heartbeat.start()
        try:
            result = registration.handle(claimed)
            if result is None:
                result = JobResult.succeeded()
            if not isinstance(result, JobResult):
                result = JobResult.failed(RetrySafety.UNKNOWN, "INVALID_HANDLER_RESULT")
        except Exception:
            # Exception text can contain feedback, provider payloads, or secrets.
            result = JobResult.failed(RetrySafety.UNKNOWN, "WORKER_HANDLER_EXCEPTION")
        finally:
            stopped.set()
            heartbeat.join()

        if lease_lost.is_set():
            return
        try:
            finish_attempt(self.engine, claimed, result, now=self.clock())
        except StaleLeaseError:
            LOGGER.warning(
                "worker_stale_result_rejected; background_job_id=%s; attempt=%s",
                claimed.background_job_id,
                claimed.attempt_number,
            )

    def run_once(self) -> bool:
        current = self.clock()
        self._reconcile_if_due(current)
        claimed = claim_one(
            self.engine,
            worker_id=self.worker_id,
            eligible_job_types=set(self.handlers),
            now=current,
        )
        if claimed is None:
            return False
        self._run_claimed(claimed, self.handlers[claimed.job_type])
        return True

    def run_forever(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                # Keep operational logs safe; persisted summaries are allow-listed too.
                LOGGER.error("worker_cycle_failed; code=worker_cycle_failed")
            stop_event.wait(self.poll_seconds)
