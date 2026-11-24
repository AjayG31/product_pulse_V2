from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from productpulse.database import create_database_engine
from productpulse.models import BackgroundJob, BackgroundJobAttempt, Base, TaxonomyVersion, User
from productpulse.settings import Settings
from productpulse.worker_runtime import (
    APPROVED_MAX_ATTEMPTS,
    RETRY_DELAYS_SECONDS,
    WORKER_LEASE_RENEWAL_SECONDS,
    WORKER_LEASE_SECONDS,
    WORKER_POLL_SECONDS,
    WORKER_RECONCILE_SECONDS,
    JobResult,
    RetrySafety,
    claim_one,
    finish_attempt,
    format_utc,
    retry_delay_seconds,
)


NOW = datetime(2026, 11, 24, 13, 0, tzinfo=UTC)


def _engine(path):
    engine = create_database_engine(Settings(data_dir=path, sqlite_busy_timeout_ms=5000))
    Base.metadata.create_all(engine)
    return engine


def _add_job(engine, job_id, job_type, max_attempts=3):
    with Session(engine) as session:
        taxonomy_version_id = None
        if job_type == "DETECTION":
            admin = session.get(User, "usr-worker-budget")
            if admin is None:
                session.add(User(
                    user_id="usr-worker-budget",
                    email="worker-budget@example.test",
                    email_normalized="worker-budget@example.test",
                    password_hash="test-only",
                    role="ADMIN",
                    status="ACTIVE",
                    must_change_password=False,
                    created_at=format_utc(NOW),
                    updated_at=format_utc(NOW),
                    deactivated_at=None,
                ))
                session.flush()
            taxonomy_version_id = f"tax-{job_id}"
            session.add(TaxonomyVersion(
                taxonomy_version_id=taxonomy_version_id,
                version_label=f"test-{job_id}",
                state="DRAFT",
                created_by="usr-worker-budget",
                created_at=format_utc(NOW),
            ))
            session.flush()
        session.add(
            BackgroundJob(
                background_job_id=job_id,
                job_type=job_type,
                taxonomy_version_id=taxonomy_version_id,
                work_key=f"{job_type.lower()}:{job_id}",
                status="QUEUED",
                attempt_count=0,
                max_attempts=max_attempts,
                scheduled_at=format_utc(NOW),
                created_at=format_utc(NOW),
            )
        )
        session.commit()


def _claim(engine, job_type, now, worker="worker"):
    return claim_one(engine, worker_id=worker, eligible_job_types={job_type}, now=now)


def test_approved_budgets_and_retry_delay_sequence_are_unchanged(tmp_path):
    assert WORKER_LEASE_SECONDS == 300
    assert WORKER_LEASE_RENEWAL_SECONDS == 60
    assert WORKER_POLL_SECONDS == 5
    assert WORKER_RECONCILE_SECONDS == 60
    assert APPROVED_MAX_ATTEMPTS == {
        "CLASSIFICATION": 3,
        "INGESTION": 3,
        "RECONCILIATION": 3,
        "DETECTION": 3,
    }
    assert RETRY_DELAYS_SECONDS == (5, 15, 45)
    assert [retry_delay_seconds(number) for number in range(1, 5)] == [5, 15, 45, 45]

    engine = _engine(tmp_path / "classification-budget")
    try:
        _add_job(engine, "classification-budget", "CLASSIFICATION")
        first = _claim(engine, "CLASSIFICATION", NOW)
        assert first is not None
        assert finish_attempt(
            engine,
            first,
            JobResult.retryable(RetrySafety.KNOWN_SAFE_TRANSIENT),
            now=NOW,
        ) == "RETRY_WAIT"

        second_at = NOW + timedelta(seconds=5)
        second = _claim(engine, "CLASSIFICATION", second_at)
        assert second is not None and second.attempt_number == 2
        assert finish_attempt(
            engine,
            second,
            JobResult.retryable(RetrySafety.KNOWN_SAFE_TRANSIENT),
            now=second_at,
        ) == "RETRY_WAIT"

        third_at = second_at + timedelta(seconds=15)
        third = _claim(engine, "CLASSIFICATION", third_at)
        assert third is not None and third.attempt_number == 3
        assert finish_attempt(
            engine,
            third,
            JobResult.retryable(RetrySafety.KNOWN_SAFE_TRANSIENT),
            now=third_at,
        ) == "FAILED"

        with Session(engine) as session:
            job = session.get(BackgroundJob, "classification-budget")
            attempts = list(
                session.scalars(
                    select(BackgroundJobAttempt)
                    .where(BackgroundJobAttempt.background_job_id == "classification-budget")
                    .order_by(BackgroundJobAttempt.attempt_number)
                )
            )
            assert job.max_attempts == 3
            assert job.attempt_count == 3
            assert job.next_attempt_at is None
            assert [item.outcome for item in attempts] == [
                "RETRYABLE_FAILURE",
                "RETRYABLE_FAILURE",
                "TERMINAL_FAILURE",
            ]
            assert attempts[0].next_attempt_at == format_utc(NOW + timedelta(seconds=5))
            assert attempts[1].next_attempt_at == format_utc(second_at + timedelta(seconds=15))
            assert attempts[2].next_attempt_at is None
    finally:
        engine.dispose()


def test_ingestion_retry_requires_an_explicit_safe_replay_result(tmp_path):
    engine = _engine(tmp_path / "ingestion-safety")
    try:
        _add_job(engine, "ingestion-unsafe", "INGESTION")
        unsafe = _claim(engine, "INGESTION", NOW)
        assert unsafe is not None
        assert finish_attempt(
            engine,
            unsafe,
            JobResult.retryable(RetrySafety.KNOWN_SAFE_TRANSIENT),
            now=NOW,
        ) == "FAILED"

        _add_job(engine, "ingestion-safe", "INGESTION")
        safe = _claim(engine, "INGESTION", NOW, worker="worker-safe")
        assert safe is not None
        assert finish_attempt(
            engine,
            safe,
            JobResult.retryable(RetrySafety.SAFE_REPLAY, "INGESTION_REPLAY_SAFE"),
            now=NOW,
        ) == "RETRY_WAIT"
        with Session(engine) as session:
            job = session.get(BackgroundJob, "ingestion-safe")
            attempt = session.get(BackgroundJobAttempt, ("ingestion-safe", 1))
            assert job.max_attempts == 3
            assert job.next_attempt_at == format_utc(NOW + timedelta(seconds=5))
            assert attempt.outcome == "RETRYABLE_FAILURE"
    finally:
        engine.dispose()


def test_reconciliation_and_historical_detection_retry_known_safe_transients_only(tmp_path):
    engine = _engine(tmp_path / "safe-transients")
    try:
        for job_type in ("RECONCILIATION", "DETECTION"):
            job_id = f"{job_type.lower()}-transient"
            _add_job(engine, job_id, job_type)
            claim = _claim(engine, job_type, NOW, worker=f"worker-{job_type.lower()}")
            assert claim is not None
            assert finish_attempt(
                engine,
                claim,
                JobResult.retryable(RetrySafety.KNOWN_SAFE_TRANSIENT),
                now=NOW,
            ) == "RETRY_WAIT"

        _add_job(engine, "reconciliation-unknown", "RECONCILIATION")
        unknown = _claim(engine, "RECONCILIATION", NOW, worker="worker-unknown")
        assert unknown is not None
        assert finish_attempt(
            engine,
            unknown,
            JobResult.retryable(RetrySafety.UNKNOWN, "OUTCOME_UNKNOWN"),
            now=NOW,
        ) == "FAILED"
    finally:
        engine.dispose()


def test_batch_poll_and_unapproved_budgets_are_never_claimed(tmp_path):
    engine = _engine(tmp_path / "unclaimable")
    try:
        _add_job(engine, "batch-null", "BATCH_POLL", max_attempts=None)
        assert _claim(engine, "BATCH_POLL", NOW, worker="worker-batch") is None
        with Session(engine) as session:
            assert session.get(BackgroundJob, "batch-null").status == "QUEUED"
        try:
            _add_job(engine, "batch-budgeted", "BATCH_POLL", max_attempts=3)
        except IntegrityError:
            pass
        else:
            raise AssertionError("BATCH_POLL must not be assigned an attempt budget.")
        try:
            _add_job(engine, "wrong-budget", "CLASSIFICATION", max_attempts=4)
        except IntegrityError:
            pass
        else:
            raise AssertionError("CLASSIFICATION must retain the approved three-claim budget.")
    finally:
        engine.dispose()
