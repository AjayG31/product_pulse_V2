import csv
import hashlib
import io
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from productpulse.database import create_database_engine
from productpulse.historical_results import canonical_result_snapshot, persist_historical_result
from productpulse.linkage_reconciliation import reconciliation_registration
from productpulse.main import create_app
from productpulse.models import (
    AuditEvent,
    BackgroundJob,
    Base,
    Batch,
    Classification,
    ClassificationLabel,
    CsvUpload,
    DetectionResult,
    DetectionRuleVersion,
    DefectCluster,
    Feedback,
    IngestionConflict,
    IngestionJob,
    FeedbackLinkageEvent,
    LogicalDefect,
    Product,
    Supplier,
    TaxonomyCategory,
    TaxonomyVersion,
    UploadPreview,
    User,
)
from productpulse.security.identity import normalize_email
from productpulse.security.passwords import hash_password
from productpulse.security.sessions import utc_text
from productpulse.settings import Settings
from productpulse.worker_runtime import WorkerRuntime


PASSWORD = "Correct horse battery staple 2026"


def _app(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    now = utc_text()
    with Session(engine) as db:
        for user_id, email, role in (
            ("usr_admin_pp015", "admin@example.test", "ADMIN"),
            ("usr_business_pp015", "business@example.test", "BUSINESS_USER"),
        ):
            display, normalized = normalize_email(email)
            db.add(User(
                user_id=user_id,
                email=display,
                email_normalized=normalized,
                password_hash=hash_password(PASSWORD),
                role=role,
                status="ACTIVE",
                must_change_password=False,
                created_at=now,
                updated_at=now,
                deactivated_at=None,
            ))
        db.add(Product(product_id="p-1", name="Product One", category=None, created_at=now, updated_at=now))
        db.add(Supplier(supplier_id="s-1", name="Supplier One", created_at=now, updated_at=now))
        db.flush()
        db.add(Batch(batch_id="b-1", product_id="p-1", supplier_id="s-1", created_at=now, updated_at=now))
        db.add(Feedback(
            feedback_id="fdb-1",
            source_type="REVIEW",
            source_record_id="review-1",
            product_id="p-1",
            supplier_id=None,
            batch_id=None,
            reported_supplier_id="s-reported",
            reported_batch_id="b-reported",
            linkage_status="LINKAGE_PENDING",
            event_time_utc="2026-11-20T09:10:11.000Z",
            feedback_text="synthetic feedback",
            rating=2,
            source_label=None,
            return_quantity=None,
            return_category=None,
            payload_sha256="a" * 64,
            record_origin="SYNTHETIC_SEED",
            ingestion_job_id=None,
            origin_preview_id=None,
            origin_row_number=None,
            origin_manifest_ref="synthetic://pp015-review-1",
            ingested_at=now,
        ))
        db.commit()
    app = create_app(settings)
    app.state.database_engine = engine
    return app, engine


def _login(client: TestClient, email: str) -> str:
    prelogin = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": prelogin, "Origin": "https://testserver"},
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _linkage_body(**changes):
    body = {
        "expected_linkage_status": "LINKAGE_PENDING",
        "expected_supplier_id": None,
        "expected_batch_id": None,
        "supplier_id": "s-1",
        "batch_id": "b-1",
        "reason": "Verified against exact reference IDs.",
    }
    body.update(changes)
    return body


def _upload_reference(client: TestClient, csrf: str, kind: str, header: list[str], rows: list[list[str]]) -> dict[str, object]:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    mappings = [
        {"source_column_index": index, "source_header": name, "target_field": name}
        for index, name in enumerate(header)
    ]
    response = client.post(
        "/admin/ingestion/previews",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"reference-preview-{uuid.uuid4().hex}"},
        files={
            "upload_kind": (None, kind),
            "column_mappings": (None, json.dumps(mappings), "application/json"),
            "file": (f"{kind.lower()}.csv", output.getvalue().encode("utf-8"), "text/csv"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_linkage_is_exact_audited_idempotent_and_historical_only(tmp_path):
    app, engine = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            invalid_csrf = client.put(
                "/admin/feedback/fdb-1/linkage",
                headers={"X-CSRF-Token": "invalid", "Idempotency-Key": "linkage-pp015-invalid-csrf"},
                json=_linkage_body(),
            )
            assert invalid_csrf.status_code == 403
            response = client.put(
                "/admin/feedback/fdb-1/linkage",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "linkage-pp015-1"},
                json=_linkage_body(),
            )
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["linkage_status"] == "LINKED"
            assert result["supplier_id"] == "s-1" and result["batch_id"] == "b-1"

            replay = client.put(
                "/admin/feedback/fdb-1/linkage",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "linkage-pp015-1"},
                json=_linkage_body(),
            )
            assert replay.status_code == 200 and replay.json() == result
            key_conflict = client.put(
                "/admin/feedback/fdb-1/linkage",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "linkage-pp015-1"},
                json=_linkage_body(reason="different request"),
            )
            assert key_conflict.status_code == 409

            stale = client.put(
                "/admin/feedback/fdb-1/linkage",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "linkage-pp015-stale"},
                json=_linkage_body(),
            )
            assert stale.status_code == 409 and stale.json()["code"] == "LINKAGE_STATE_CONFLICT"
            mismatched = client.put(
                "/admin/feedback/fdb-1/linkage",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "linkage-pp015-bad-batch"},
                json=_linkage_body(expected_linkage_status="LINKED", expected_supplier_id="s-1", expected_batch_id="b-1", batch_id="not-this-product"),
            )
            assert mismatched.status_code == 422

            with TestClient(app, base_url="https://testserver") as business:
                _login(business, "business@example.test")
                denied = business.put(
                    "/admin/feedback/fdb-1/linkage",
                    headers={"Idempotency-Key": "business-linkage"},
                    json=_linkage_body(expected_linkage_status="LINKED", expected_supplier_id="s-1", expected_batch_id="b-1"),
                )
                assert denied.status_code == 403

        with Session(engine) as db:
            feedback = db.get(Feedback, "fdb-1")
            assert feedback is not None
            assert (feedback.supplier_id, feedback.batch_id, feedback.linkage_status) == ("s-1", "b-1", "LINKED")
            assert (feedback.source_type, feedback.source_record_id, feedback.event_time_utc, feedback.feedback_text) == (
                "REVIEW", "review-1", "2026-11-20T09:10:11.000Z", "synthetic feedback"
            )
            assert (feedback.reported_supplier_id, feedback.reported_batch_id) == ("s-reported", "b-reported")
            assert db.scalar(select(func.count()).select_from(FeedbackLinkageEvent)) == 1
            assert db.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.job_type == "RECONCILIATION")) == 1
            job = db.scalar(select(BackgroundJob).where(BackgroundJob.job_type == "RECONCILIATION"))
            assert job is not None and job.max_attempts == 3 and job.taxonomy_version_id is None

        runtime = WorkerRuntime(engine, handlers={"RECONCILIATION": reconciliation_registration(engine)})
        assert runtime.run_once()
        with Session(engine) as db:
            job = db.scalar(select(BackgroundJob).where(BackgroundJob.job_type == "RECONCILIATION"))
            assert job is not None and job.status == "COMPLETED" and job.attempt_count == 1
            recompute_audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "HISTORICAL_AGGREGATE_RECOMPUTED"))
            assert recompute_audit is not None
            aggregate = json.loads(recompute_audit.after_state_text)
            assert aggregate["taxonomy_version_id"] is None
            assert aggregate["coverage_state"] == "UNKNOWN"
            assert aggregate["evaluation_mode"] == "HISTORICAL_RECOMPUTE"
            assert aggregate["incident_application_state"] == "NOT_APPLICABLE"
            assert db.scalar(select(func.count()).select_from(DetectionResult)) == 0
    finally:
        engine.dispose()


def test_linkage_requires_exact_existing_supplier_and_batch(tmp_path):
    app, engine = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            response = client.put(
                "/admin/feedback/fdb-1/linkage",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "linkage-invalid-exact"},
                json=_linkage_body(supplier_id="s-missing"),
            )
            assert response.status_code == 422
            assert response.json()["code"] == "LINKAGE_REFERENCE_INVALID"
        with Session(engine) as db:
            assert db.get(Feedback, "fdb-1").linkage_status == "LINKAGE_PENDING"
            assert db.scalar(select(func.count()).select_from(FeedbackLinkageEvent)) == 0
            assert db.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.job_type == "RECONCILIATION")) == 0
    finally:
        engine.dispose()


def test_reference_imports_fill_only_missing_fields_and_preserve_conflicts(tmp_path):
    app, engine = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            preview = _upload_reference(
                client,
                csrf,
                "PRODUCT_REFERENCE",
                ["product_id", "name", "category"],
                [["p-1", "Different Product", "Kitchen"], ["p-2", "Product Two", "Kitchen"]],
            )
            assert preview["counts"] == {
                "total_rows": 2,
                "accepted_rows": 1,
                "rejected_rows": 0,
                "duplicate_noop_rows": 0,
                "conflict_rows": 1,
            }
            rows = client.get(f"/admin/ingestion/previews/{preview['preview_id']}/rows")
            assert rows.status_code == 200
            assert [row["row_status"] for row in rows.json()["items"]] == ["CONFLICT", "ACCEPTED"]
            confirmed = client.post(
                f"/admin/ingestion/previews/{preview['preview_id']}/confirm",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "confirm-product-reference"},
                json={"verified_sha256": preview["verified_sha256"]},
            )
            assert confirmed.status_code == 202, confirmed.text
            assert confirmed.json()["status"] == "COMPLETED"
            replay = client.post(
                f"/admin/ingestion/previews/{preview['preview_id']}/confirm",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "confirm-product-reference"},
                json={"verified_sha256": preview["verified_sha256"]},
            )
            assert replay.status_code == 202 and replay.json() == confirmed.json()

            supplier_preview = _upload_reference(
                client, csrf, "SUPPLIER_REFERENCE", ["supplier_id", "name"], [["s-2", "Supplier Two"]]
            )
            supplier_confirmed = client.post(
                f"/admin/ingestion/previews/{supplier_preview['preview_id']}/confirm",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "confirm-supplier-reference"},
                json={"verified_sha256": supplier_preview["verified_sha256"]},
            )
            assert supplier_confirmed.status_code == 202

            batch_preview = _upload_reference(
                client, csrf, "BATCH_REFERENCE", ["batch_id", "product_id", "supplier_id"], [["b-2", "p-1", "s-2"]]
            )
            batch_confirmed = client.post(
                f"/admin/ingestion/previews/{batch_preview['preview_id']}/confirm",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "confirm-batch-reference"},
                json={"verified_sha256": batch_preview["verified_sha256"]},
            )
            assert batch_confirmed.status_code == 202, batch_confirmed.text
        with Session(engine) as db:
            original = db.get(Product, "p-1")
            imported = db.get(Product, "p-2")
            assert original is not None and (original.name, original.category) == ("Product One", None)
            assert imported is not None and (imported.name, imported.category) == ("Product Two", "Kitchen")
            assert db.get(Supplier, "s-2").name == "Supplier Two"
            assert db.get(Batch, "b-2") is not None
            conflict = db.scalar(select(IngestionConflict).where(IngestionConflict.conflict_kind == "REFERENCE_MAPPING"))
            assert conflict is not None
            assert conflict.state == "PENDING" and conflict.mapping_key == "PRODUCT_REFERENCE:p-1"
            assert conflict.existing_value_hash and conflict.incoming_value_hash
            reference_jobs = db.scalars(select(IngestionJob).where(IngestionJob.processing_mode.is_(None))).all()
            assert len(reference_jobs) == 3 and all(job.status == "COMPLETED" for job in reference_jobs)
            assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0
    finally:
        engine.dispose()


def test_product_aggregates_are_scoped_to_explicit_taxonomy_and_attempt_authority(tmp_path):
    app, engine = _app(tmp_path)
    now = "2026-11-24T10:00:00.000Z"
    with Session(engine) as db:
        source_feedback = db.get(Feedback, "fdb-1")
        assert source_feedback is not None
        source_feedback.supplier_id = "s-1"
        source_feedback.batch_id = "b-1"
        source_feedback.linkage_status = "LINKED"
        db.add(TaxonomyVersion(taxonomy_version_id="tax-v1", version_label="test-v1", state="DRAFT", created_by="usr_admin_pp015", created_at=now))
        db.add(TaxonomyVersion(taxonomy_version_id="tax-v2", version_label="test-v2", state="DRAFT", created_by="usr_admin_pp015", created_at=now))
        db.flush()
        db.add_all([
            TaxonomyCategory(taxonomy_version_id="tax-v1", category_code="DEFECT", display_name="Defect", category_kind="DEFECT"),
            TaxonomyCategory(taxonomy_version_id="tax-v1", category_code="NO_DEFECT", display_name="No defect", category_kind="NO_DEFECT"),
            TaxonomyCategory(taxonomy_version_id="tax-v2", category_code="DEFECT", display_name="Defect", category_kind="DEFECT"),
        ])
        db.add(LogicalDefect(logical_defect_id="ld-1", meaning_description="Synthetic test defect", created_by="usr_admin_pp015", created_at=now))
        db.flush()
        pending = Feedback(
            feedback_id="fdb-pending", source_type="RETURN", source_record_id="return-pending", product_id="p-1",
            supplier_id=None, batch_id=None, reported_supplier_id="s-1", reported_batch_id="b-1", linkage_status="LINKAGE_PENDING",
            event_time_utc="2026-11-21T09:00:00.000Z", feedback_text="synthetic return", rating=None, source_label=None,
            return_quantity=2, return_category="quality", payload_sha256="b" * 64, record_origin="SYNTHETIC_SEED",
            ingestion_job_id=None, origin_preview_id=None, origin_row_number=None, origin_manifest_ref="synthetic://return-pending", ingested_at=now,
        )
        db.add(pending)
        for job_id, work_key in (("bgj-class-1", "test-classification-1"), ("bgj-class-2", "test-classification-2")):
            db.add(BackgroundJob(
                background_job_id=job_id, job_type="CLASSIFICATION", work_key=work_key, ingestion_job_id=None,
                status="QUEUED", attempt_count=0, max_attempts=3, scheduled_at=now, next_attempt_at=None,
                worker_id=None, lease_token=None, lease_expires_at=None, provider_input_file_id=None,
                provider_batch_id=None, last_error_code=None, last_error_summary=None, created_at=now,
                started_at=None, completed_at=None,
            ))
        db.flush()
        for classification_id, job_id, has_defect, category in (
            ("class-a", "bgj-class-1", True, "DEFECT"),
            ("class-z", "bgj-class-2", False, "NO_DEFECT"),
        ):
            db.add(Classification(
                classification_id=classification_id, feedback_id="fdb-1", attempt_number=2 if classification_id == "class-a" else 1,
                background_job_id=job_id, taxonomy_version_id="tax-v1", api_path="RESPONSES", model_id=None,
                prompt_version="synthetic", schema_version="synthetic", status="COMPLETED", has_defect=has_defect,
                needs_review=False, severity_hint=None, evidence_excerpt=None, provider_request_id=None, input_tokens=None,
                output_tokens=None, estimated_cost_micro_usd=None, latency_ms=None, error_code=None, created_at=now,
                started_at="2026-11-22T11:00:00.000Z", completed_at="2026-11-22T12:00:00.000Z",
            ))
            db.add(ClassificationLabel(
                classification_id=classification_id, label_role="PRIMARY", taxonomy_version_id="tax-v1",
                category_code=category, specific_issue_code=None,
                logical_defect_id=None, label_order=0,
            ))
        db.add(Classification(
            classification_id="class-review", feedback_id="fdb-1", attempt_number=3,
            background_job_id="bgj-class-1", taxonomy_version_id="tax-v1", api_path="RESPONSES", model_id=None,
            prompt_version="synthetic", schema_version="synthetic", status="NEEDS_REVIEW", has_defect=None,
            needs_review=True, severity_hint=None, evidence_excerpt=None, provider_request_id=None, input_tokens=None,
            output_tokens=None, estimated_cost_micro_usd=None, latency_ms=None, error_code="NEEDS_REVIEW",
            created_at=now, started_at="2026-11-22T11:00:00.000Z", completed_at="2026-11-23T12:00:00.000Z",
        ))
        db.commit()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            _login(client, "business@example.test")
            latest = client.get("/products/p-1?taxonomy_version_id=tax-v1")
            assert latest.status_code == 200, latest.text
            product = latest.json()["product"]
            assert product["taxonomy_version_id"] == "tax-v1"
            assert product["defect_feedback_count"] == 0
            assert product["unclassified_feedback_count"] == 0
            assert product["linkage_pending_feedback_count"] == 1
            assert product["linkage_pending_unclassified_feedback_count"] == 1
            assert product["linkage_pending_return_record_count"] == 1
            assert product["linkage_pending_returned_units"] == 2

            other_version = client.get("/products/p-1?taxonomy_version_id=tax-v2")
            assert other_version.status_code == 200
            other_product = other_version.json()["product"]
            assert other_product["taxonomy_version_id"] == "tax-v2"
            assert other_product["unclassified_feedback_count"] == 1
            assert other_product["defect_feedback_count"] == 0

            missing = client.get("/products/p-1")
            assert missing.status_code == 422
            unknown = client.get("/products/p-1?taxonomy_version_id=tax-no-such-version")
            assert unknown.status_code == 422 and unknown.json()["code"] == "TAXONOMY_VERSION_INVALID"
            page = client.get("/products?taxonomy_version_id=tax-v1")
            assert page.status_code == 200 and page.json()["taxonomy_version_id"] == "tax-v1"
    finally:
        engine.dispose()


def test_historical_result_fingerprint_persists_exact_taxonomy_and_fails_closed(tmp_path):
    app, engine = _app(tmp_path)
    now = "2026-11-24T10:00:00.000Z"
    try:
        with Session(engine) as db:
            db.add(TaxonomyVersion(taxonomy_version_id="tax-historical", version_label="test-historical", state="DRAFT", created_by="usr_admin_pp015", created_at=now))
            db.add(LogicalDefect(logical_defect_id="ld-historical", meaning_description="Synthetic historical defect", created_by="usr_admin_pp015", created_at=now))
            db.flush()
            db.add(DefectCluster(
                cluster_id="cluster-historical", product_id="p-1", supplier_id="s-1", batch_id="b-1",
                logical_defect_id="ld-historical", created_at=now,
            ))
            db.add(DetectionRuleVersion(
                rule_version="rule-historical", taxonomy_version_id="tax-historical", state="DRAFT",
                config_text=json.dumps({"taxonomy_version_id": "tax-historical", "mode": "synthetic-context"}),
                created_by="usr_admin_pp015", created_at=now, activated_at=None, retired_at=None,
            ))
            db.add(BackgroundJob(
                background_job_id="bgj-historical", job_type="DETECTION", taxonomy_version_id="tax-historical",
                work_key="historical-context-job", ingestion_job_id=None, status="RUNNING", attempt_count=1,
                max_attempts=3, scheduled_at=now, next_attempt_at=None, worker_id="worker-test",
                lease_token="lease-test", lease_expires_at="2026-11-24T10:05:00.000Z", provider_input_file_id=None,
                provider_batch_id=None, last_error_code=None, last_error_summary=None, created_at=now,
                started_at=now, completed_at=None,
            ))
            db.flush()
            persisted = persist_historical_result(
                db,
                taxonomy_version_id="tax-historical",
                rule_version="rule-historical",
                background_job_id="bgj-historical",
                cluster_id="cluster-historical",
                coverage_policy_version="saved-policy-context",
                evaluated_at=now,
                observed_start_utc="2026-11-23T00:00:00.000Z",
                observed_end_utc=now,
                baseline_start_utc="2026-10-26T00:00:00.000Z",
                baseline_end_utc="2026-11-23T00:00:00.000Z",
                observed_count=2,
                baseline_28d_count=4,
                observed_classification_assessed_count=2,
                observed_classification_complete_count=0,
                baseline_classification_assessed_count=4,
                baseline_classification_complete_count=0,
                snapshot_inputs={"source_feedback_ids": ["fdb-synthetic-a", "fdb-synthetic-b"], "classification_states": ["UNCLASSIFIED"]},
            )
            db.commit()
            assert persisted.taxonomy_version_id == "tax-historical"
            assert hashlib.sha256(persisted.result_input_snapshot_text.encode("utf-8")).hexdigest() == persisted.result_key
            snapshot = json.loads(persisted.result_input_snapshot_text)
            assert snapshot["taxonomy_version_id"] == "tax-historical"
            assert snapshot["coverage_policy_version"] == "saved-policy-context"
            assert persisted.evaluation_mode == "HISTORICAL_RECOMPUTE"
            assert persisted.coverage_state == "INSUFFICIENT"
            assert persisted.baseline_source_coverage_state == "UNKNOWN"
            assert persisted.incident_application_state == "NOT_APPLICABLE"

            version_a = canonical_result_snapshot(
                taxonomy_version_id="tax-a", rule_version="rule", coverage_policy_version="policy",
                snapshot_inputs={"source_feedback_ids": ["fdb-1"]},
            )
            version_b = canonical_result_snapshot(
                taxonomy_version_id="tax-b", rule_version="rule", coverage_policy_version="policy",
                snapshot_inputs={"source_feedback_ids": ["fdb-1"]},
            )
            assert version_a[1] != version_b[1]
            try:
                canonical_result_snapshot(
                    taxonomy_version_id="tax-a", rule_version="rule", coverage_policy_version="policy",
                    snapshot_inputs={"feedback_text": "must not persist"},
                )
            except ValueError as error:
                assert "source text" in str(error)
            else:
                raise AssertionError("source text was accepted in a historical result fingerprint")
    finally:
        engine.dispose()
