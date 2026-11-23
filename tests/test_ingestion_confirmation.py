import csv
import io
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from productpulse.database import create_database_engine
from productpulse.main import create_app
from productpulse.models import (
    Batch,
    BackgroundJob,
    Base,
    CsvUpload,
    Feedback,
    IngestionJob,
    Product,
    Supplier,
    UploadPreview,
    User,
)
from productpulse.security.identity import normalize_email
from productpulse.security.passwords import hash_password
from productpulse.security.sessions import utc_text
from productpulse.settings import Settings


PASSWORD = "Correct horse battery staple 2026"
HEADER = ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text", "rating", "source"]
MAPPINGS = [
    {"source_column_index": index, "source_header": name, "target_field": name}
    for index, name in enumerate(HEADER)
]


def _csv(rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _row(record_id: str, product_id: str, supplier_id: str = "", batch_id: str = "", text_value: str = "synthetic feedback"):
    return [record_id, product_id, supplier_id, batch_id, "2026-11-20T09:10:11Z", text_value, "", ""]


def _app(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for user_id, email, role in (
            ("usr_admin_confirm", "admin@example.test", "ADMIN"),
            ("usr_business_confirm", "business@example.test", "BUSINESS_USER"),
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
                created_at=utc_text(),
                updated_at=utc_text(),
                deactivated_at=None,
            ))
        db.commit()
    app = create_app(settings)
    app.state.database_engine = engine
    return app, engine, settings


def _login(client: TestClient, email: str = "admin@example.test") -> str:
    token = client.get("/auth/csrf").json()["csrf_token"]
    login = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": token, "Origin": "https://testserver"},
        json={"email": email, "password": PASSWORD},
    )
    assert login.status_code == 200
    return login.json()["csrf_token"]


def _create_preview_with_csrf(client: TestClient, csrf: str, rows: list[list[str]]) -> dict[str, object]:
    content = _csv(rows)
    response = client.post(
        "/admin/ingestion/previews",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"preview-{uuid.uuid4().hex}"},
        files={
            "upload_kind": (None, "REVIEWS"),
            "column_mappings": (None, json.dumps(MAPPINGS), "application/json"),
            "file": ("reviews.csv", content, "text/csv"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm(client: TestClient, csrf: str, preview: dict[str, object], key: str, mode: str = "HISTORICAL_BATCH"):
    return client.post(
        f"/admin/ingestion/previews/{preview['preview_id']}/confirm",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
        json={"verified_sha256": preview["verified_sha256"], "processing_mode": mode},
    )


def test_feedback_confirmation_is_hash_bound_explicit_and_idempotent(tmp_path):
    app, engine, _settings = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client)
            preview = _create_preview_with_csrf(client, csrf, [_row("r1", "p1"), _row("r2", "p2")])

            missing_mode = client.post(
                f"/admin/ingestion/previews/{preview['preview_id']}/confirm",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "confirm-missing-mode"},
                json={"verified_sha256": preview["verified_sha256"]},
            )
            assert missing_mode.status_code == 422
            null_mode = client.post(
                f"/admin/ingestion/previews/{preview['preview_id']}/confirm",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "confirm-null-mode"},
                json={"verified_sha256": preview["verified_sha256"], "processing_mode": None},
            )
            assert null_mode.status_code == 422
            mismatch = client.post(
                f"/admin/ingestion/previews/{preview['preview_id']}/confirm",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "confirm-wrong-hash"},
                json={"verified_sha256": "0" * 64, "processing_mode": "HISTORICAL_BATCH"},
            )
            assert mismatch.status_code == 409

            confirmed = _confirm(client, csrf, preview, "confirm-001")
            assert confirmed.status_code == 202, confirmed.text
            job = confirmed.json()
            assert job["status"] == "QUEUED"
            assert job["processing_mode"] == "HISTORICAL_BATCH"
            assert job["counts"] == {
                "total_rows": 2,
                "accepted_rows": 2,
                "rejected_rows": 0,
                "duplicate_noop_rows": 0,
                "conflict_rows": 0,
                "persisted_feedback": 2,
            }
            assert job["retry_eligibility"] == {"eligible": False, "reason_code": "NOT_FAILED"}
            replay = _confirm(client, csrf, preview, "confirm-001")
            assert replay.status_code == 202 and replay.json() == job
            same_mode_new_key = _confirm(client, csrf, preview, "confirm-002")
            assert same_mode_new_key.status_code == 202 and same_mode_new_key.json() == job
            changed_mode = _confirm(client, csrf, preview, "confirm-003", mode="INCREMENTAL_RESPONSES")
            assert changed_mode.status_code == 409
            assert changed_mode.json()["code"] == "PROCESSING_MODE_CONFLICT"
            preview_state = client.get(f"/admin/ingestion/previews/{preview['preview_id']}").json()
            assert preview_state["state"] == "CONFIRMED"

        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(IngestionJob)) == 1
            assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 1
            assert db.scalar(select(func.count()).select_from(Feedback)) == 2
            assert db.scalar(select(func.count()).select_from(Product)) == 2
            records = db.scalars(select(Feedback).order_by(Feedback.source_record_id)).all()
            assert [item.feedback_text for item in records] == ["synthetic feedback", "synthetic feedback"]
            assert all(item.linkage_status == "LINKAGE_PENDING" and item.product_id in {"p1", "p2"} for item in records)
            assert all(item.record_origin == "CSV_UPLOAD" for item in records)
            queue_item = db.scalar(select(BackgroundJob))
            assert queue_item is not None
            assert queue_item.background_job_id.startswith("bgj_")
            assert queue_item.job_type == "CLASSIFICATION"
            assert queue_item.work_key == f"classification:{job['job_id']}"
            assert queue_item.ingestion_job_id == job["job_id"]
            assert queue_item.status == "QUEUED"
            assert queue_item.attempt_count == 0 and queue_item.max_attempts == 3
            assert queue_item.provider_input_file_id is None and queue_item.provider_batch_id is None
    finally:
        engine.dispose()


def test_business_user_csrf_artifact_tamper_and_stale_preview_fail_closed(tmp_path):
    app, engine, settings = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            admin_csrf = _login(client)
            first = _create_preview_with_csrf(client, admin_csrf, [_row("r1", "p1")])
            stale = _create_preview_with_csrf(client, admin_csrf, [_row("r1", "p1")])

            with TestClient(app, base_url="https://testserver") as business:
                _login(business, "business@example.test")
                denied = business.post(
                    f"/admin/ingestion/previews/{first['preview_id']}/confirm",
                    headers={"Idempotency-Key": "business-confirm-001"},
                    json={"verified_sha256": first["verified_sha256"], "processing_mode": "HISTORICAL_BATCH"},
                )
                assert denied.status_code == 403
            invalid_csrf = client.post(
                f"/admin/ingestion/previews/{first['preview_id']}/confirm",
                headers={"X-CSRF-Token": "invalid", "Idempotency-Key": "invalid-csrf-001"},
                json={"verified_sha256": first["verified_sha256"], "processing_mode": "HISTORICAL_BATCH"},
            )
            assert invalid_csrf.status_code == 403
            _confirm(client, admin_csrf, first, "confirm-first").raise_for_status()
            stale_confirmation = _confirm(client, admin_csrf, stale, "confirm-stale")
            assert stale_confirmation.status_code == 409
            assert stale_confirmation.json()["code"] == "PREVIEW_STALE"

            tampered = _create_preview_with_csrf(client, admin_csrf, [_row("r2", "p2")])
            artifact = next((settings.data_dir / "artifacts").glob("*.csv"))
            # Locate the artifact linked to the tampered preview and change its bytes after preview creation.
            with Session(engine) as db:
                upload_id = db.get(UploadPreview, tampered["preview_id"]).upload_id
                artifact_id = db.get(CsvUpload, upload_id).artifact_id
            artifact = settings.data_dir / "artifacts" / f"{artifact_id}.csv"
            artifact.write_bytes(artifact.read_bytes() + b"tamper")
            integrity_error = _confirm(client, admin_csrf, tampered, "confirm-tampered")
            assert integrity_error.status_code == 503
            assert integrity_error.json()["code"] == "ARTIFACT_INTEGRITY_ERROR"

        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(IngestionJob)) == 1
            assert db.scalar(select(func.count()).select_from(Feedback)) == 1
    finally:
        engine.dispose()


def test_import_resolves_only_known_supplier_and_matching_batch(tmp_path):
    app, engine, _settings = _app(tmp_path)
    with Session(engine) as db:
        now = utc_text()
        db.add(Product(product_id="p-linked", name=None, category=None, created_at=now, updated_at=now))
        db.add(Supplier(supplier_id="s-known", name=None, created_at=now, updated_at=now))
        db.flush()
        db.add(Batch(batch_id="b-known", product_id="p-linked", supplier_id="s-known", created_at=now, updated_at=now))
        db.commit()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client)
            preview = _create_preview_with_csrf(client, csrf, [
                _row("r-linked", "p-linked", "s-known", "b-known"),
                _row("r-pending", "p-pending", "s-missing", "b-missing"),
            ])
            result = _confirm(client, csrf, preview, "confirm-linkage-001")
            assert result.status_code == 202
        with Session(engine) as db:
            records = {row.source_record_id: row for row in db.scalars(select(Feedback)).all()}
            assert records["r-linked"].linkage_status == "LINKED"
            assert (records["r-linked"].supplier_id, records["r-linked"].batch_id) == ("s-known", "b-known")
            assert records["r-pending"].linkage_status == "LINKAGE_PENDING"
            assert records["r-pending"].supplier_id is None and records["r-pending"].batch_id is None
            assert (records["r-pending"].reported_supplier_id, records["r-pending"].reported_batch_id) == ("s-missing", "b-missing")
            assert db.get(Supplier, "s-missing") is None
            assert db.get(Batch, "b-missing") is None
    finally:
        engine.dispose()


def test_501_row_import_uses_bounded_chunks_and_commits_all_rows_once(tmp_path):
    app, engine, _settings = _app(tmp_path)
    now = utc_text()
    with Session(engine) as db:
        db.add_all([
            Product(product_id=f"p{index:05}", name=None, category=None, created_at=now, updated_at=now)
            for index in range(501)
        ])
        db.add_all([
            Supplier(supplier_id=f"s{index:05}", name=None, created_at=now, updated_at=now)
            for index in range(501)
        ])
        db.flush()
        db.add_all([
            Batch(batch_id=f"b{index:05}", product_id=f"p{index:05}", supplier_id=f"s{index:05}", created_at=now, updated_at=now)
            for index in range(501)
        ])
        db.commit()
    rows = [_row(f"r{index:05}", f"p{index:05}", f"s{index:05}", f"b{index:05}") for index in range(501)]
    lookup_parameter_counts: dict[str, list[int]] = {"suppliers": [], "batches": []}

    def record_lookup_parameters(_connection, _cursor, statement, parameters, _context, _executemany):
        normalized = statement.upper()
        for table_name in lookup_parameter_counts:
            if f"FROM {table_name.upper()}" in normalized:
                lookup_parameter_counts[table_name].append(len(parameters))

    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client)
            preview = _create_preview_with_csrf(client, csrf, rows)
            assert preview["counts"]["accepted_rows"] == 501
            event.listen(engine, "before_cursor_execute", record_lookup_parameters)
            try:
                result = _confirm(client, csrf, preview, "confirm-chunks-001")
                assert result.status_code == 202, result.text
                assert result.json()["counts"]["persisted_feedback"] == 501
            finally:
                event.remove(engine, "before_cursor_execute", record_lookup_parameters)
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Feedback)) == 501
            assert db.scalar(select(func.count()).select_from(IngestionJob)) == 1
            queue_item = db.scalar(select(BackgroundJob))
            assert queue_item is not None and queue_item.status == "QUEUED" and queue_item.max_attempts == 3
            assert db.scalar(select(func.count()).select_from(Feedback).where(Feedback.linkage_status == "LINKED")) == 501
        assert sorted(lookup_parameter_counts["suppliers"]) == [1, 250, 250]
        assert sorted(lookup_parameter_counts["batches"]) == [3, 750, 750]
    finally:
        engine.dispose()


def test_failure_in_second_import_chunk_rolls_back_job_products_and_first_chunk(tmp_path):
    app, engine, _settings = _app(tmp_path)
    rows = [_row(f"r{index:05}", f"p{index:05}") for index in range(501)]
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client)
            preview = _create_preview_with_csrf(client, csrf, rows)
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE TRIGGER fail_second_feedback_chunk BEFORE INSERT ON feedback "
                    "WHEN NEW.source_record_id = 'r00500' "
                    "BEGIN SELECT RAISE(ABORT, 'injected second chunk failure'); END"
                ))
            result = _confirm(client, csrf, preview, "confirm-failure-001")
            assert result.status_code == 503
            assert result.json()["code"] == "INGESTION_CONFIRM_FAILED"
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Feedback)) == 0
            assert db.scalar(select(func.count()).select_from(IngestionJob)) == 0
            assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0
            assert db.scalar(select(func.count()).select_from(Product)) == 0
            saved_preview = db.get(UploadPreview, preview["preview_id"])
            assert saved_preview is not None and saved_preview.state == "READY"
    finally:
        engine.dispose()


def test_preview_confirmation_failure_rolls_back_already_created_queue_item(tmp_path):
    app, engine, _settings = _app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _login(client)
            preview = _create_preview_with_csrf(client, csrf, [_row("r1", "p1")])
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE TRIGGER fail_preview_confirmation BEFORE UPDATE OF state ON upload_previews "
                    "WHEN NEW.state = 'CONFIRMED' "
                    "BEGIN SELECT RAISE(ABORT, 'injected preview confirmation failure'); END"
                ))
            result = _confirm(client, csrf, preview, "confirm-preview-failure-001")
            assert result.status_code == 503
            assert result.json()["code"] == "INGESTION_CONFIRM_FAILED"
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Feedback)) == 0
            assert db.scalar(select(func.count()).select_from(IngestionJob)) == 0
            assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0
            assert db.scalar(select(func.count()).select_from(Product)) == 0
            saved_preview = db.get(UploadPreview, preview["preview_id"])
            assert saved_preview is not None and saved_preview.state == "READY"
    finally:
        engine.dispose()
