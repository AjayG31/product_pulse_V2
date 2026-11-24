import csv
import hashlib
import io
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from productpulse import conflicts_api
from productpulse.database import create_database_engine
from productpulse.main import create_app
from productpulse.models import (
    AuditEvent,
    Base,
    Batch,
    Feedback,
    IngestionConflict,
    Product,
    Supplier,
    UploadPreviewRow,
    User,
)
from productpulse.security.identity import normalize_email
from productpulse.security.passwords import hash_password
from productpulse.security.sessions import utc_text
from productpulse.settings import Settings


PASSWORD = "Correct horse battery staple 2026"


def _app(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    now = utc_text()
    with Session(engine) as db:
        for user_id, email, role in (
            ("usr_admin_conflict", "admin@example.test", "ADMIN"),
            ("usr_business_conflict", "business@example.test", "BUSINESS_USER"),
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
        for product_id, name in (("p-1", "Product One"), ("p-2", "Product Two")):
            db.add(Product(product_id=product_id, name=name, category=None, created_at=now, updated_at=now))
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
            feedback_text="original synthetic feedback",
            rating=2,
            source_label=None,
            return_quantity=None,
            return_category=None,
            payload_sha256="a" * 64,
            record_origin="SYNTHETIC_SEED",
            ingestion_job_id=None,
            origin_preview_id=None,
            origin_row_number=None,
            origin_manifest_ref="synthetic://pp036-review-1",
            ingested_at=now,
        ))
        db.commit()
    app = create_app(settings)
    app.state.database_engine = engine
    return app, engine


def _login(client: TestClient, email: str) -> str:
    token = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": token, "Origin": "https://testserver"},
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _upload(client: TestClient, csrf: str, kind: str, headers: list[str], rows: list[list[str]]) -> dict:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    mappings = [
        {"source_column_index": index, "source_header": header, "target_field": header}
        for index, header in enumerate(headers)
    ]
    response = client.post(
        "/admin/ingestion/previews",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"pp036-preview-{uuid.uuid4().hex}"},
        files={
            "upload_kind": (None, kind),
            "column_mappings": (None, json.dumps(mappings), "application/json"),
            "file": (f"{kind.lower()}.csv", output.getvalue().encode("utf-8"), "text/csv"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reference_hash(mapping: dict[str, object]) -> str:
    canonical = json.dumps(mapping, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_admin_source_conflict_is_safe_audited_and_idempotent(tmp_path):
    app, engine = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            preview = _upload(
                client,
                csrf,
                "REVIEWS",
                ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"],
                [["review-1", "p-1", "", "", "2026-11-20T09:10:11Z", "incoming customer text must stay private"]],
            )
            listed = client.get("/admin/reconciliation/conflicts?conflict_kind=SOURCE_PAYLOAD&page_size=10")
            assert listed.status_code == 200, listed.text
            assert listed.headers["Cache-Control"] == "no-store"
            assert listed.json()["page"]["total_items"] == 1
            conflict = listed.json()["items"][0]
            assert conflict["preview_id"] == preview["preview_id"]
            conflict_id = conflict["conflict_id"]

            detail = client.get(f"/admin/reconciliation/conflicts/{conflict_id}")
            assert detail.status_code == 200
            assert detail.headers["Cache-Control"] == "no-store"
            assert "incoming customer text must stay private" not in detail.text
            assert "normalized_row_text" not in detail.text

            with TestClient(app, base_url="https://testserver") as anonymous:
                assert anonymous.get("/admin/reconciliation/conflicts").status_code == 401
                assert anonymous.get(f"/admin/reconciliation/conflicts/{conflict_id}").status_code == 401
                assert anonymous.post(
                    f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                    headers={"Idempotency-Key": "anonymous-cannot-resolve"},
                    json={"decision": "KEEP_EXISTING", "resolution_note": "Denied"},
                ).status_code == 401
            with TestClient(app, base_url="https://testserver") as business:
                business_csrf = _login(business, "business@example.test")
                assert business.get("/admin/reconciliation/conflicts").status_code == 403
                assert business.get(f"/admin/reconciliation/conflicts/{conflict_id}").status_code == 403
                denied = business.post(
                    f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                    headers={"X-CSRF-Token": business_csrf, "Idempotency-Key": "business-cannot-resolve"},
                    json={"decision": "KEEP_EXISTING", "resolution_note": "Denied"},
                )
                assert denied.status_code == 403
            missing_csrf = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"Idempotency-Key": "admin-csrf-required"},
                json={"decision": "KEEP_EXISTING", "resolution_note": "Must include CSRF"},
            )
            assert missing_csrf.status_code == 403

            apply_incoming = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "source-apply-forbidden"},
                json={"decision": "APPLY_INCOMING_REFERENCE", "resolution_note": "Forbidden for source text"},
            )
            assert apply_incoming.status_code == 422
            resolved = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "source-keep-1"},
                json={"decision": "KEEP_EXISTING", "resolution_note": "Keep the existing source payload."},
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["state"] == "RESOLVED"
            replay = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "source-keep-1"},
                json={"decision": "KEEP_EXISTING", "resolution_note": "Keep the existing source payload."},
            )
            assert replay.status_code == 200 and replay.json() == resolved.json()
            changed_replay = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "source-keep-1"},
                json={"decision": "DISMISS", "resolution_note": "Changed request"},
            )
            assert changed_replay.status_code == 409

            with Session(engine) as db:
                now = utc_text()
                db.add(Feedback(
                    feedback_id="fdb-2",
                    source_type="REVIEW",
                    source_record_id="review-2",
                    product_id="p-1",
                    supplier_id=None,
                    batch_id=None,
                    reported_supplier_id=None,
                    reported_batch_id=None,
                    linkage_status="LINKAGE_PENDING",
                    event_time_utc="2026-11-21T09:10:11.000Z",
                    feedback_text="second original synthetic feedback",
                    rating=3,
                    source_label=None,
                    return_quantity=None,
                    return_category=None,
                    payload_sha256="b" * 64,
                    record_origin="SYNTHETIC_SEED",
                    ingestion_job_id=None,
                    origin_preview_id=None,
                    origin_row_number=None,
                    origin_manifest_ref="synthetic://pp036-review-2",
                    ingested_at=now,
                ))
                db.commit()
            second_preview = _upload(
                client,
                csrf,
                "REVIEWS",
                ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"],
                [["review-2", "p-1", "", "", "2026-11-21T09:10:11Z", "second incoming source text"]],
            )
            source_conflicts = client.get("/admin/reconciliation/conflicts?conflict_kind=SOURCE_PAYLOAD").json()["items"]
            second_conflict_id = next(item["conflict_id"] for item in source_conflicts if item["preview_id"] == second_preview["preview_id"])
            dismissed = client.post(
                f"/admin/reconciliation/conflicts/{second_conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "source-dismiss-1"},
                json={"decision": "DISMISS", "resolution_note": "Dismiss this changed source payload."},
            )
            assert dismissed.status_code == 200 and dismissed.json()["state"] == "DISMISSED"

        with Session(engine) as db:
            source = db.get(Feedback, "fdb-1")
            assert source is not None
            assert (source.feedback_text, source.event_time_utc, source.payload_sha256, source.source_record_id) == (
                "original synthetic feedback", "2026-11-20T09:10:11.000Z", "a" * 64, "review-1"
            )
            second_source = db.get(Feedback, "fdb-2")
            assert second_source is not None and (second_source.feedback_text, second_source.payload_sha256) == (
                "second original synthetic feedback", "b" * 64
            )
            saved = db.get(IngestionConflict, conflict_id)
            assert saved is not None and saved.resolved_by == "usr_admin_conflict"
            assert saved.resolution_note == "Keep the existing source payload."
            audits = db.scalars(select(AuditEvent).where(
                AuditEvent.action == "INGESTION_CONFLICT_RESOLVED",
                AuditEvent.resource_id == conflict_id,
            )).all()
            assert len(audits) == 1 and audits[0].actor_user_id == "usr_admin_conflict"
            for audit in audits:
                assert "incoming customer text must stay private" not in (audit.before_state_text or "")
                assert "incoming customer text must stay private" not in (audit.after_state_text or "")
            second_conflict = db.get(IngestionConflict, second_conflict_id)
            assert second_conflict is not None and second_conflict.state == "DISMISSED"
            assert db.scalar(select(func.count()).select_from(IngestionConflict).where(IngestionConflict.state == "PENDING")) == 0
    finally:
        engine.dispose()


def test_reference_mapping_apply_is_hash_guarded_atomic_and_audited(tmp_path):
    app, engine = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            preview = _upload(
                client,
                csrf,
                "PRODUCT_REFERENCE",
                ["product_id", "name", "category"],
                [["p-2", "Replacement Product Two", "Kitchen"]],
            )
            conflicts = client.get("/admin/reconciliation/conflicts?conflict_kind=REFERENCE_MAPPING").json()["items"]
            conflict_id = next(item["conflict_id"] for item in conflicts if item["preview_id"] == preview["preview_id"])
            detail = client.get(f"/admin/reconciliation/conflicts/{conflict_id}").json()
            old_mapping = {"product_id": "p-2", "name": "Product Two", "category": None}
            expected_hash = _reference_hash(old_mapping)
            assert detail["existing_value_hash"] == expected_hash

            missing_hash = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reference-no-hash"},
                json={"decision": "APPLY_INCOMING_REFERENCE", "resolution_note": "Missing expected hash"},
            )
            assert missing_hash.status_code == 422

            with Session(engine) as db:
                product = db.get(Product, "p-2")
                assert product is not None
                product.name = "Changed after preview"
                db.commit()
            stale = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reference-stale-hash"},
                json={
                    "decision": "APPLY_INCOMING_REFERENCE",
                    "expected_existing_value_hash": expected_hash,
                    "resolution_note": "Reject stale mapping state",
                },
            )
            assert stale.status_code == 409 and stale.json()["code"] == "STALE_REFERENCE_MAPPING"
            with Session(engine) as db:
                product = db.get(Product, "p-2")
                assert product is not None and product.name == "Changed after preview" and product.category is None
                saved = db.get(IngestionConflict, conflict_id)
                assert saved is not None and saved.state == "PENDING"
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.action == "INGESTION_CONFLICT_RESOLVED", AuditEvent.resource_id == conflict_id
                )) == 0

            preview = _upload(
                client,
                csrf,
                "PRODUCT_REFERENCE",
                ["product_id", "name", "category"],
                [["p-1", "Replacement Product One", "Kitchen"]],
            )
            conflicts = client.get("/admin/reconciliation/conflicts?conflict_kind=REFERENCE_MAPPING").json()["items"]
            conflict_id = next(item["conflict_id"] for item in conflicts if item["preview_id"] == preview["preview_id"])
            detail = client.get(f"/admin/reconciliation/conflicts/{conflict_id}").json()
            old_mapping = {"product_id": "p-1", "name": "Product One", "category": None}
            expected_hash = _reference_hash(old_mapping)
            assert detail["existing_value_hash"] == expected_hash
            body = {
                "decision": "APPLY_INCOMING_REFERENCE",
                "expected_existing_value_hash": expected_hash,
                "resolution_note": "Apply the reviewed product reference.",
            }
            resolved = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reference-apply-1"},
                json=body,
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["state"] == "RESOLVED"
            replay = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reference-apply-1"},
                json=body,
            )
            assert replay.status_code == 200 and replay.json() == resolved.json()
            preview_detail = client.get(f"/admin/ingestion/previews/{preview['preview_id']}/rows")
            assert preview_detail.status_code == 200
            assert preview_detail.json()["items"][0]["row_status"] == "CONFLICT"

        with Session(engine) as db:
            product = db.get(Product, "p-1")
            assert product is not None and (product.name, product.category) == ("Replacement Product One", "Kitchen")
            conflict = db.get(IngestionConflict, conflict_id)
            assert conflict is not None and conflict.state == "RESOLVED" and conflict.resolved_by == "usr_admin_conflict"
            row = db.get(UploadPreviewRow, (preview["preview_id"], 1))
            assert row is not None and row.row_status == "CONFLICT"
            assert hashlib.sha256(row.normalized_row_text.encode("utf-8")).hexdigest() == row.row_payload_sha256
            audit = db.scalar(select(AuditEvent).where(
                AuditEvent.action == "INGESTION_CONFLICT_RESOLVED", AuditEvent.resource_id == conflict_id
            ))
            assert audit is not None and audit.actor_user_id == "usr_admin_conflict"
            before = json.loads(audit.before_state_text)
            after = json.loads(audit.after_state_text)
            assert before["mapping"] == {"product_id": "p-1", "name": "Product One", "category": None}
            assert after["mapping"] == {"product_id": "p-1", "name": "Replacement Product One", "category": "Kitchen"}
            assert after["decision"] == "APPLY_INCOMING_REFERENCE"
            assert after["resolution_note"] == "Apply the reviewed product reference."
            assert after["source_payload_changed"] is False
    finally:
        engine.dispose()


def test_conflict_list_filters_and_paginates_stably(tmp_path):
    app, engine = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            _upload(
                client,
                csrf,
                "PRODUCT_REFERENCE",
                ["product_id", "name", "category"],
                [["p-1", "Conflict One", "Kitchen"], ["p-2", "Conflict Two", "Kitchen"]],
            )
            first = client.get(
                "/admin/reconciliation/conflicts?conflict_kind=REFERENCE_MAPPING&state=PENDING&page=1&page_size=1"
            )
            second = client.get(
                "/admin/reconciliation/conflicts?conflict_kind=REFERENCE_MAPPING&state=PENDING&page=2&page_size=1"
            )
            assert first.status_code == second.status_code == 200
            assert first.json()["page"]["total_items"] == 2
            assert first.json()["page"]["page"] == 1 and len(first.json()["items"]) == 1
            assert second.json()["page"]["page"] == 2 and len(second.json()["items"]) == 1
            assert first.json()["items"][0]["conflict_id"] != second.json()["items"][0]["conflict_id"]
            no_matches = client.get("/admin/reconciliation/conflicts?state=RESOLVED")
            assert no_matches.status_code == 200 and no_matches.json()["page"]["total_items"] == 0

            conflict = first.json()["items"][0]
            response = client.post(
                f"/admin/reconciliation/conflicts/{conflict['conflict_id']}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reference-keep-existing"},
                json={"decision": "KEEP_EXISTING", "resolution_note": "Keep the existing reference fields."},
            )
            assert response.status_code == 200 and response.json()["state"] == "RESOLVED"
        with Session(engine) as db:
            assert db.get(Product, "p-1").name == "Product One"
            assert db.get(Product, "p-2").name == "Product Two"
    finally:
        engine.dispose()


def test_conflict_dismissal_preserves_reference_values_and_batch_link_integrity(tmp_path):
    app, engine = _app(tmp_path)
    try:
        with Session(engine) as db:
            feedback = db.get(Feedback, "fdb-1")
            assert feedback is not None
            feedback.supplier_id = "s-1"
            feedback.batch_id = "b-1"
            feedback.linkage_status = "LINKED"
            db.commit()
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            preview = _upload(
                client,
                csrf,
                "BATCH_REFERENCE",
                ["batch_id", "product_id", "supplier_id"],
                [["b-1", "p-2", "s-1"]],
            )
            conflicts = client.get("/admin/reconciliation/conflicts?conflict_kind=REFERENCE_MAPPING").json()["items"]
            conflict_id = next(item["conflict_id"] for item in conflicts if item["preview_id"] == preview["preview_id"])
            detail = client.get(f"/admin/reconciliation/conflicts/{conflict_id}").json()
            blocked = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "batch-mapping-in-use"},
                json={
                    "decision": "APPLY_INCOMING_REFERENCE",
                    "expected_existing_value_hash": detail["existing_value_hash"],
                    "resolution_note": "Cannot break exact feedback linkage",
                },
            )
            assert blocked.status_code == 409 and blocked.json()["code"] == "REFERENCE_MAPPING_IN_USE"
            dismissed = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "batch-mapping-dismiss"},
                json={"decision": "DISMISS", "resolution_note": "Dismiss without changing the batch."},
            )
            assert dismissed.status_code == 200 and dismissed.json()["state"] == "DISMISSED"
        with Session(engine) as db:
            batch = db.get(Batch, "b-1")
            feedback = db.get(Feedback, "fdb-1")
            assert batch is not None and (batch.product_id, batch.supplier_id) == ("p-1", "s-1")
            assert feedback is not None and (feedback.product_id, feedback.batch_id, feedback.supplier_id) == ("p-1", "b-1", "s-1")
    finally:
        engine.dispose()


def test_audit_failure_rolls_back_reference_application_and_resolution(tmp_path, monkeypatch):
    app, engine = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client, "admin@example.test")
            preview = _upload(
                client,
                csrf,
                "PRODUCT_REFERENCE",
                ["product_id", "name", "category"],
                [["p-1", "Must Roll Back", "Kitchen"]],
            )
            conflicts = client.get("/admin/reconciliation/conflicts?conflict_kind=REFERENCE_MAPPING").json()["items"]
            conflict_id = next(item["conflict_id"] for item in conflicts if item["preview_id"] == preview["preview_id"])
            detail = client.get(f"/admin/reconciliation/conflicts/{conflict_id}").json()

            def fail_audit(*_args, **_kwargs):
                raise RuntimeError("synthetic audit failure")

            monkeypatch.setattr(conflicts_api, "safe_audit", fail_audit)
            response = client.post(
                f"/admin/reconciliation/conflicts/{conflict_id}/resolve",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reference-audit-failure"},
                json={
                    "decision": "APPLY_INCOMING_REFERENCE",
                    "expected_existing_value_hash": detail["existing_value_hash"],
                    "resolution_note": "Rollback if the audit cannot be written.",
                },
            )
            assert response.status_code == 503
        with Session(engine) as db:
            product = db.get(Product, "p-1")
            conflict = db.get(IngestionConflict, conflict_id)
            assert product is not None and (product.name, product.category) == ("Product One", None)
            assert conflict is not None and conflict.state == "PENDING" and conflict.resolved_by is None
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == "INGESTION_CONFLICT_RESOLVED", AuditEvent.resource_id == conflict_id
            )) == 0
    finally:
        engine.dispose()
