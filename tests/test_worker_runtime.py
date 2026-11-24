from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from productpulse.database import create_database_engine
from productpulse.db_session import get_engine
from productpulse.main import create_app
from productpulse.models import BackgroundJob, BackgroundJobAttempt, Base
from productpulse.settings import Settings
from productpulse.worker_runtime import (
    ClaimedJob,
    HandlerRegistration,
    JobResult,
    RetrySafety,
    StaleLeaseError,
    WorkerRuntime,
    WORKER_RECONCILE_SECONDS,
    _run_write_unit,
    claim_one,
    finish_attempt,
    format_utc,
    reconcile_expired_leases,
    renew_lease,
)


NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def _engine(path: Path):
    engine = create_database_engine(Settings(data_dir=path, sqlite_busy_timeout_ms=5000))
    Base.metadata.create_all(engine)
    return engine


def _add_job(
    engine,
    *,
    job_id: str,
    job_type: str = "CLASSIFICATION",
    max_attempts: int | None = 3,
    scheduled_at: datetime = NOW,
) -> None:
    with Session(engine) as session:
        session.add(
            BackgroundJob(
                background_job_id=job_id,
                job_type=job_type,
                work_key=f"{job_type.lower()}:{job_id}",
                ingestion_job_id=None,
                status="QUEUED",
                attempt_count=0,
                max_attempts=max_attempts,
                scheduled_at=format_utc(scheduled_at),
                next_attempt_at=None,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                provider_input_file_id=None,
                provider_batch_id=None,
                last_error_code=None,
                last_error_summary=None,
                created_at=format_utc(scheduled_at),
                started_at=None,
                completed_at=None,
            )
        )
        session.commit()


def test_claim_is_atomic_and_unbudgeted_or_unsupported_work_stays_queued(tmp_path):
    engine = _engine(tmp_path / "worker")
    try:
        _add_job(engine, job_id="class-1")
        _add_job(engine, job_id="batch-1", job_type="BATCH_POLL", max_attempts=None)
        _add_job(engine, job_id="ing-1", job_type="INGESTION")

        claimed = claim_one(
            engine,
            worker_id="worker-a",
            eligible_job_types={"CLASSIFICATION", "BATCH_POLL"},
            now=NOW,
        )

        assert claimed is not None
        assert claimed.background_job_id == "class-1"
        assert claimed.attempt_number == 1
        assert claim_one(
            engine,
            worker_id="worker-b",
            eligible_job_types={"CLASSIFICATION", "BATCH_POLL"},
            now=NOW,
        ) is None

        with Session(engine) as session:
            job = session.get(BackgroundJob, "class-1")
            attempt = session.get(BackgroundJobAttempt, ("class-1", 1))
            assert job.status == "RUNNING"
            assert job.attempt_count == 1
            assert job.worker_id == "worker-a"
            assert job.lease_token == claimed.lease_token
            assert job.lease_expires_at == format_utc(NOW + timedelta(minutes=5))
            assert attempt.outcome == "IN_PROGRESS"
            assert attempt.finished_at is None
            assert attempt.next_attempt_at is None
            assert session.scalar(
                select(BackgroundJob.status).where(BackgroundJob.background_job_id == "batch-1")
            ) == "QUEUED"
            assert session.scalar(
                select(BackgroundJob.status).where(BackgroundJob.background_job_id == "ing-1")
            ) == "QUEUED"
    finally:
        engine.dispose()


def test_two_worker_processes_cannot_claim_the_same_item(tmp_path):
    settings = Settings(data_dir=tmp_path / "shared", sqlite_busy_timeout_ms=5000)
    first_engine = create_database_engine(settings)
    Base.metadata.create_all(first_engine)
    second_engine = create_database_engine(settings)
    try:
        _add_job(first_engine, job_id="class-atomic")
        barrier = threading.Barrier(2)

        def claim(engine, worker_id):
            barrier.wait(timeout=5)
            return claim_one(
                engine,
                worker_id=worker_id,
                eligible_job_types={"CLASSIFICATION"},
                now=NOW,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda args: claim(*args),
                    [(first_engine, "worker-one"), (second_engine, "worker-two")],
                )
            )

        claimed = [item for item in results if item is not None]
        assert len(claimed) == 1
        with Session(first_engine) as session:
            assert session.scalar(
                select(func.count()).select_from(BackgroundJobAttempt)
            ) == 1
    finally:
        first_engine.dispose()
        second_engine.dispose()


def test_api_and_worker_engines_share_the_configured_sqlite_file(tmp_path):
    settings = Settings(data_dir=tmp_path / "shared", sqlite_busy_timeout_ms=5000)
    api_app = create_app(settings)
    api_engine = get_engine(SimpleNamespace(app=api_app))
    worker_engine = create_database_engine(settings)
    Base.metadata.create_all(api_engine)
    try:
        _add_job(api_engine, job_id="shared-job")
        claimed = claim_one(
            worker_engine,
            worker_id="separate-process",
            eligible_job_types={"CLASSIFICATION"},
            now=NOW,
        )
        assert claimed is not None
        with Session(api_engine) as session:
            assert session.get(BackgroundJob, "shared-job").status == "RUNNING"
        assert settings.database_path.exists()
    finally:
        api_engine.dispose()
        worker_engine.dispose()


def test_lease_renewal_and_stale_owner_result_write_rejection(tmp_path):
    engine = _engine(tmp_path / "lease")
    try:
        _add_job(engine, job_id="lease-job")
        claimed = claim_one(
            engine,
            worker_id="worker-a",
            eligible_job_types={"CLASSIFICATION"},
            now=NOW,
        )
        assert claimed is not None
        renewed_at = NOW + timedelta(seconds=60)
        assert renew_lease(engine, claimed, now=renewed_at) is True

        with Session(engine) as session:
            job = session.get(BackgroundJob, "lease-job")
            assert job.lease_expires_at == format_utc(renewed_at + timedelta(minutes=5))

        stale_claim = ClaimedJob(
            background_job_id=claimed.background_job_id,
            job_type=claimed.job_type,
            work_key=claimed.work_key,
            ingestion_job_id=claimed.ingestion_job_id,
            attempt_number=claimed.attempt_number,
            worker_id=claimed.worker_id,
            lease_token="stale-owner-token",
        )
        with pytest.raises(StaleLeaseError):
            finish_attempt(engine, stale_claim, JobResult.succeeded(), now=renewed_at)

        assert finish_attempt(engine, claimed, JobResult.succeeded(), now=renewed_at) == "COMPLETED"
        assert renew_lease(engine, claimed, now=renewed_at + timedelta(seconds=1)) is False
        with Session(engine) as session:
            job = session.get(BackgroundJob, "lease-job")
            attempt = session.get(BackgroundJobAttempt, ("lease-job", 1))
            assert job.status == "COMPLETED"
            assert job.worker_id is None and job.lease_token is None and job.lease_expires_at is None
            assert attempt.outcome == "SUCCEEDED"
            assert attempt.finished_at == format_utc(renewed_at)
    finally:
        engine.dispose()


def test_expired_safe_reconciliation_job_recovers_after_worker_restart(tmp_path):
    settings = Settings(data_dir=tmp_path / "restart", sqlite_busy_timeout_ms=5000)
    first_engine = create_database_engine(settings)
    Base.metadata.create_all(first_engine)
    _add_job(first_engine, job_id="reconcile-1", job_type="RECONCILIATION")
    claimed = claim_one(
        first_engine,
        worker_id="old-worker",
        eligible_job_types={"RECONCILIATION"},
        now=NOW,
    )
    assert claimed is not None
    first_engine.dispose()

    restarted_engine = create_database_engine(settings)
    try:
        expired_at = NOW + timedelta(minutes=5)
        assert reconcile_expired_leases(
            restarted_engine,
            now=expired_at,
            safe_retry_job_types={"RECONCILIATION"},
        ) == 1

        with Session(restarted_engine) as session:
            job = session.get(BackgroundJob, "reconcile-1")
            old_attempt = session.get(BackgroundJobAttempt, ("reconcile-1", 1))
            assert job.status == "RETRY_WAIT"
            assert job.next_attempt_at == format_utc(expired_at + timedelta(seconds=5))
            assert old_attempt.outcome == "ABANDONED"
            assert old_attempt.next_attempt_at is None

        recovered = claim_one(
            restarted_engine,
            worker_id="new-worker",
            eligible_job_types={"RECONCILIATION"},
            now=expired_at + timedelta(seconds=5),
        )
        assert recovered is not None
        assert recovered.background_job_id == claimed.background_job_id
        assert recovered.attempt_number == 2
    finally:
        restarted_engine.dispose()


def test_expired_unknown_classification_is_terminal_and_not_replayed(tmp_path):
    engine = _engine(tmp_path / "unknown")
    try:
        _add_job(engine, job_id="class-unknown")
        claimed = claim_one(
            engine,
            worker_id="old-worker",
            eligible_job_types={"CLASSIFICATION"},
            now=NOW,
        )
        assert claimed is not None
        with pytest.raises(StaleLeaseError):
            finish_attempt(
                engine,
                claimed,
                JobResult.succeeded(),
                now=NOW + timedelta(minutes=5),
            )
        assert reconcile_expired_leases(
            engine,
            now=NOW + timedelta(minutes=5),
            safe_retry_job_types=set(),
        ) == 1
        with Session(engine) as session:
            job = session.get(BackgroundJob, "class-unknown")
            attempt = session.get(BackgroundJobAttempt, ("class-unknown", 1))
            assert job.status == "FAILED"
            assert job.last_error_code == "WORKER_LEASE_EXPIRED"
            assert attempt.outcome == "ABANDONED"
            assert attempt.next_attempt_at is None
    finally:
        engine.dispose()


def test_long_handler_renews_its_lease_without_holding_a_write_transaction(tmp_path, monkeypatch):
    engine = _engine(tmp_path / "heartbeat")
    try:
        _add_job(
            engine,
            job_id="long-job",
            job_type="RECONCILIATION",
            scheduled_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        renew_calls = []
        original_renew = renew_lease

        def record_renew(engine_arg, claimed, *, now=None):
            renew_calls.append(now)
            return original_renew(engine_arg, claimed, now=now)

        monkeypatch.setattr("productpulse.worker_runtime.renew_lease", record_renew)

        def slow_idempotent_handler(_claimed):
            time.sleep(0.04)
            with engine.connect() as connection:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                connection.rollback()
            return JobResult.succeeded()

        runtime = WorkerRuntime(
            engine,
            {"RECONCILIATION": HandlerRegistration(slow_idempotent_handler)},
            worker_id="heartbeat-worker",
            lease_renewal_seconds=0.005,
        )
        assert runtime.run_once() is True
        assert renew_calls
        with Session(engine) as session:
            job = session.get(BackgroundJob, "long-job")
            assert job.status == "COMPLETED"
    finally:
        engine.dispose()


def test_sqlite_busy_write_unit_rolls_back_and_retries_at_most_twice(tmp_path):
    engine = _engine(tmp_path / "busy")
    calls = 0

    class BusyError(Exception):
        sqlite_errorcode = sqlite3.SQLITE_BUSY

    def flaky_write(session):
        nonlocal calls
        calls += 1
        session.add(
            BackgroundJob(
                background_job_id="busy-job",
                job_type="RECONCILIATION",
                work_key="reconciliation:busy-job",
                status="QUEUED",
                attempt_count=0,
                max_attempts=3,
                scheduled_at=format_utc(NOW),
                created_at=format_utc(NOW),
            )
        )
        session.flush()
        if calls < 3:
            raise OperationalError("write", {}, BusyError("database is locked"))
        return "committed"

    try:
        assert _run_write_unit(engine, flaky_write) == "committed"
        assert calls == 3
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(BackgroundJob)) == 1
    finally:
        engine.dispose()


def test_only_sqlite_busy_errors_are_retried(tmp_path):
    engine = _engine(tmp_path / "not-busy")
    calls = 0

    def failing_write(_session):
        nonlocal calls
        calls += 1
        raise OperationalError("write", {}, sqlite3.OperationalError("constraint failed"))

    try:
        with pytest.raises(OperationalError):
            _run_write_unit(engine, failing_write)
        assert calls == 1
    finally:
        engine.dispose()


def test_runtime_reconciles_at_startup_and_each_sixty_seconds(tmp_path, monkeypatch):
    engine = _engine(tmp_path / "reconcile-cadence")
    try:
        calls = []

        def record_reconcile(engine_arg, *, now=None, safe_retry_job_types=frozenset()):
            calls.append((now, safe_retry_job_types))
            return 0

        monkeypatch.setattr("productpulse.worker_runtime.reconcile_expired_leases", record_reconcile)
        runtime = WorkerRuntime(engine, clock=lambda: NOW)
        assert runtime.run_once() is False
        assert len(calls) == 1
        assert runtime._reconcile_if_due(NOW + timedelta(seconds=WORKER_RECONCILE_SECONDS - 1)) == 0
        assert len(calls) == 1
        assert runtime._reconcile_if_due(NOW + timedelta(seconds=WORKER_RECONCILE_SECONDS)) == 0
        assert len(calls) == 2
    finally:
        engine.dispose()
