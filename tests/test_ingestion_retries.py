import json
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from productpulse.database import create_database_engine
import productpulse.ingestion_jobs_api as ingestion_jobs_api
from productpulse.main import create_app
from productpulse.models import (
    AuditEvent,
    BackgroundJob,
    BackgroundJobAttempt,
    Base,
    Feedback,
    IngestionJob,
    User,
)
from productpulse.security.identity import normalize_email
from productpulse.security.passwords import hash_password
from productpulse.security.sessions import utc_text
from productpulse.settings import Settings


PASSWORD = "Correct horse battery staple 2026"
SAFE_REPLAY_SUMMARY = "Replay-safe work did not complete and may be attempted again."
UNKNOWN_OUTCOME_SUMMARY = "The job outcome could not be verified; automatic replay was not scheduled."
ABANDONED_OUTCOME_SUMMARY = "The worker lease expired without a persisted result."
REVIEW_MAPPINGS = [
    {"source_column_index": 0, "source_header": "review_id", "target_field": "review_id"},
    {"source_column_index": 1, "source_header": "product_id", "target_field": "product_id"},
    {"source_column_index": 2, "source_header": "supplier_id", "target_field": "supplier_id"},
    {"source_column_index": 3, "source_header": "batch_id", "target_field": "batch_id"},
    {"source_column_index": 4, "source_header": "review_timestamp", "target_field": "review_timestamp"},
    {"source_column_index": 5, "source_header": "review_text", "target_field": "review_text"},
]


def _make_user(engine, email: str, role: str) -> None:
    display, normalized = normalize_email(email)
    with Session(engine) as db:
        db.add(User(
            user_id=f"usr_{role.lower()}_{normalized.split('@')[0]}",
            email=display,
            email_normalized=normalized,
            password_hash=hash_password(PASSWORD),
            role=role,
            status="ACTIVE",
            must_change_password=False,
            created_at=utc_text(),
            updated_at=utc_text(),
            deactivated_at=None,
        ))
        db.commit()


def _fixture_app(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    _make_user(engine, "admin@example.test", "ADMIN")
    _make_user(engine, "business@example.test", "BUSINESS_USER")
    app = create_app(settings)
    app.state.database_engine = engine
    return app, engine


def _sign_in(client: TestClient, email: str) -> str:
    prelogin_csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": prelogin_csrf, "Origin": "https://testserver"},
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def _upload_parts():
    content = (
        "review_id,product_id,supplier_id,batch_id,review_timestamp,review_text\r\n"
        "review-1,product-1,supplier-1,batch-1,2026-01-01T00:00:00Z,Screen cracked\r\n"
    ).encode()
    return {
        "upload_kind": (None, "REVIEWS"),
        "column_mappings": (None, json.dumps(REVIEW_MAPPINGS), "application/json"),
        "file": ("reviews.csv", content, "text/csv"),
    }


def _create_ingestion_job(client: TestClient, csrf: str) -> dict:
    preview = client.post(
        "/admin/ingestion/previews",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"preview-{uuid.uuid4().hex}"},
        files=_upload_parts(),
    )
    assert preview.status_code == 201, preview.text
    preview_body = preview.json()
    confirmed = client.post(
        f"/admin/ingestion/previews/{preview_body['preview_id']}/confirm",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"confirm-{uuid.uuid4().hex}"},
        json={
            "verified_sha256": preview_body["verified_sha256"],
            "processing_mode": "INCREMENTAL_RESPONSES",
        },
    )
    assert confirmed.status_code == 202, confirmed.text
    return confirmed.json()


def _seed_terminal_run(
    engine,
    job_id: str,
    *,
    summary: str = SAFE_REPLAY_SUMMARY,
    outcome: str = "TERMINAL_FAILURE",
    attempt_count: int = 3,
    max_attempts: int = 3,
) -> BackgroundJob:
    now = utc_text()
    run_id = f"bgj_{uuid.uuid4().hex}"
    run = BackgroundJob(
        background_job_id=run_id,
        job_type="INGESTION",
        work_key=f"ingestion:{job_id}",
        ingestion_job_id=job_id,
        status="FAILED",
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        scheduled_at=now,
        next_attempt_at=None,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        provider_input_file_id=None,
        provider_batch_id=None,
        last_error_code="INGESTION_REPLAY_SAFE" if summary == SAFE_REPLAY_SUMMARY else "WORKER_FAILURE",
        last_error_summary="internal raw feedback must never be returned",
        created_at=now,
        started_at=now,
        completed_at=now,
    )
    with Session(engine) as db:
        job = db.get(IngestionJob, job_id)
        assert job is not None
        job.status = "FAILED"
        job.started_at = now
        job.completed_at = now
        job.last_error_code = run.last_error_code
        db.add(run)
        for number in range(1, attempt_count + 1):
            is_final = number == attempt_count
            attempt_outcome = outcome if is_final else "RETRYABLE_FAILURE"
            db.add(BackgroundJobAttempt(
                background_job_id=run_id,
                attempt_number=number,
                worker_id=f"worker_{number}",
                claimed_at=now,
                finished_at=now,
                outcome=attempt_outcome,
                error_code=run.last_error_code,
                safe_error_summary=summary,
                next_attempt_at=None if is_final or attempt_outcome != "RETRYABLE_FAILURE" else now,
            ))
        db.commit()
    return run_id


def test_admin_lists_and_reads_status_with_server_derived_retry_eligibility_and_safe_fields(tmp_path):
    app, engine = _fixture_app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            job = _create_ingestion_job(client, csrf)
            job_id = job["job_id"]

            listed = client.get("/admin/ingestion/jobs?status=QUEUED&page=1&page_size=10")
            assert listed.status_code == 200
            assert listed.json()["page"]["total_items"] == 1
            assert listed.json()["items"][0]["retry_eligibility"] == {
                "eligible": False,
                "reason_code": "NO_RETRYABLE_WORK",
            }

            _seed_terminal_run(engine, job_id)
            detail = client.get(f"/admin/ingestion/jobs/{job_id}")
            assert detail.status_code == 200
            payload = detail.json()
            assert payload["status"] == "FAILED"
            assert payload["retry_eligibility"] == {"eligible": True, "reason_code": "ELIGIBLE"}
            assert payload["last_error_code"] == "INGESTION_REPLAY_SAFE"
            assert "internal raw feedback" not in detail.text
            failed_page = client.get("/admin/ingestion/jobs?status=FAILED")
            assert failed_page.status_code == 200
            assert failed_page.json()["items"][0]["job_id"] == job_id
            assert client.get("/admin/ingestion/jobs?upload_kind=REVIEWS").json()["page"]["total_items"] == 1
    finally:
        engine.dispose()


def test_retry_creates_one_audited_run_and_idempotent_replay_preserves_import_data(tmp_path):
    app, engine = _fixture_app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            job = _create_ingestion_job(client, csrf)
            job_id = job["job_id"]
            with Session(engine) as db:
                before_feedback = [
                    (row.feedback_id, row.source_type, row.source_record_id, row.payload_sha256)
                    for row in db.scalars(select(Feedback)).all()
                ]
                original_mode = db.get(IngestionJob, job_id).processing_mode
            prior_run_id = _seed_terminal_run(engine, job_id)

            headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "admin-recovery-001"}
            retried = client.post(f"/admin/ingestion/jobs/{job_id}/retry", headers=headers)
            assert retried.status_code == 202, retried.text
            body = retried.json()
            run = body["run"]
            assert run["background_job_id"] != prior_run_id
            assert run["ingestion_job_id"] == job_id
            assert run["job_type"] == "INGESTION"
            assert run["status"] == "QUEUED"
            assert run["attempt_count"] == 0
            assert run["max_attempts"] == 3
            assert body["ingestion_job"]["processing_mode"] == original_mode
            assert body["ingestion_job"]["idempotency_key"] == job["idempotency_key"]
            assert body["ingestion_job"]["preview_id"] == job["preview_id"]
            assert body["ingestion_job"]["retry_eligibility"] == {"eligible": False, "reason_code": "WORK_IN_PROGRESS"}

            replay = client.post(f"/admin/ingestion/jobs/{job_id}/retry", headers=headers)
            assert replay.status_code == 202
            assert replay.json()["run"]["background_job_id"] == run["background_job_id"]
            changed_key = client.post(
                f"/admin/ingestion/jobs/{job_id}/retry",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "admin-recovery-002"},
            )
            assert changed_key.status_code == 409
            assert changed_key.json()["retry_eligibility"] == {
                "eligible": False,
                "reason_code": "WORK_IN_PROGRESS",
            }

            with Session(engine) as db:
                all_runs = db.scalars(select(BackgroundJob).where(BackgroundJob.job_type == "INGESTION")).all()
                events = db.scalars(select(AuditEvent).where(
                    AuditEvent.action == "INGESTION_RECOVERY",
                    AuditEvent.resource_id == job_id,
                )).all()
                after_feedback = [
                    (row.feedback_id, row.source_type, row.source_record_id, row.payload_sha256)
                    for row in db.scalars(select(Feedback)).all()
                ]
                assert len(all_runs) == 2
                assert len(events) == 1
                assert events[0].actor_user_id == "usr_admin_admin"
                assert json.loads(events[0].after_state_text)["idempotency_key"] == "admin-recovery-001"
                assert json.loads(events[0].after_state_text)["run_id"] == run["background_job_id"]
                assert after_feedback == before_feedback
                assert db.get(BackgroundJob, prior_run_id).status == "FAILED"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("summary", "outcome", "attempt_count", "max_attempts", "expected"),
    [
        ("The worker could not complete this job.", "TERMINAL_FAILURE", 3, 3, "PERMANENT_FAILURE"),
        (UNKNOWN_OUTCOME_SUMMARY, "TERMINAL_FAILURE", 3, 3, "OUTCOME_UNKNOWN"),
        (ABANDONED_OUTCOME_SUMMARY, "ABANDONED", 3, 3, "OUTCOME_UNKNOWN"),
        (SAFE_REPLAY_SUMMARY, "TERMINAL_FAILURE", 2, 3, "RETRY_POLICY_BLOCKED"),
    ],
)
def test_recovery_fails_closed_for_permanent_unknown_abandoned_and_inconsistent_runs(
    tmp_path, summary, outcome, attempt_count, max_attempts, expected
):
    app, engine = _fixture_app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            job = _create_ingestion_job(client, csrf)
            _seed_terminal_run(
                engine,
                job["job_id"],
                summary=summary,
                outcome=outcome,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            )
            response = client.post(
                f"/admin/ingestion/jobs/{job['job_id']}/retry",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "denied-recovery-001"},
            )
            assert response.status_code == 409
            assert response.json()["code"] == "retry_not_eligible"
            assert response.json()["retry_eligibility"] == {"eligible": False, "reason_code": expected}
            with Session(engine) as db:
                assert db.scalar(select(func.count()).select_from(BackgroundJob).where(
                    BackgroundJob.job_type == "INGESTION",
                    BackgroundJob.ingestion_job_id == job["job_id"],
                )) == 1
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action == "INGESTION_RECOVERY",
                )) == 0
    finally:
        engine.dispose()


def test_business_user_unauthenticated_and_csrf_denials_have_no_recovery_side_effects(tmp_path):
    app, engine = _fixture_app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            admin_csrf = _sign_in(client, "admin@example.test")
            job = _create_ingestion_job(client, admin_csrf)
            _seed_terminal_run(engine, job["job_id"])
            before = 1

            unauthenticated = TestClient(app, base_url="https://testserver").post(
                f"/admin/ingestion/jobs/{job['job_id']}/retry",
                headers={"Idempotency-Key": "denied-auth-001"},
            )
            assert unauthenticated.status_code == 401

            business_csrf = _sign_in(client, "business@example.test")
            denied = client.post(
                f"/admin/ingestion/jobs/{job['job_id']}/retry",
                headers={"X-CSRF-Token": business_csrf, "Idempotency-Key": "denied-business-001"},
            )
            assert denied.status_code == 403
            assert client.get("/admin/ingestion/jobs").status_code == 403

            admin_csrf = _sign_in(client, "admin@example.test")
            csrf_denied = client.post(
                f"/admin/ingestion/jobs/{job['job_id']}/retry",
                headers={"Idempotency-Key": "denied-csrf-001"},
            )
            assert csrf_denied.status_code == 403

            with Session(engine) as db:
                assert db.scalar(select(func.count()).select_from(BackgroundJob).where(
                    BackgroundJob.job_type == "INGESTION",
                    BackgroundJob.ingestion_job_id == job["job_id"],
                )) == before
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action == "INGESTION_RECOVERY",
                )) == 0
    finally:
        engine.dispose()


def test_recovery_run_and_audit_roll_back_together_on_audit_failure(tmp_path, monkeypatch):
    app, engine = _fixture_app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            job = _create_ingestion_job(client, csrf)
            _seed_terminal_run(engine, job["job_id"])

            original_safe_audit = ingestion_jobs_api.safe_audit

            def fail_after_audit_flush(db, **kwargs):
                original_safe_audit(db, **kwargs)
                db.flush()
                raise RuntimeError("synthetic audit write failure")

            monkeypatch.setattr(ingestion_jobs_api, "safe_audit", fail_after_audit_flush)
            with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as failing_client:
                csrf = _sign_in(failing_client, "admin@example.test")
                failed = failing_client.post(
                    f"/admin/ingestion/jobs/{job['job_id']}/retry",
                    headers={"X-CSRF-Token": csrf, "Idempotency-Key": "atomic-recovery-001"},
                )
            assert failed.status_code == 500

            with Session(engine) as db:
                assert db.scalar(select(func.count()).select_from(BackgroundJob).where(
                    BackgroundJob.job_type == "INGESTION",
                    BackgroundJob.ingestion_job_id == job["job_id"],
                )) == 1
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action == "INGESTION_RECOVERY",
                )) == 0
                assert db.get(IngestionJob, job["job_id"]).status == "FAILED"
    finally:
        engine.dispose()
