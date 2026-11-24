import csv
import hashlib
import io
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from productpulse.database import create_database_engine
from productpulse.ingestion.artifacts import ArtifactIntegrityError, ArtifactStore
from productpulse.ingestion import parser
from productpulse.ingestion.parser import CsvInputError, parse_preview
from productpulse.main import create_app
from productpulse.models import (
    Base,
    CsvUpload,
    Feedback,
    IngestionJob,
    Product,
    RejectionReportArtifact,
    UploadPreview,
    UploadPreviewRow,
    User,
)
from productpulse.security.identity import normalize_email
from productpulse.security.passwords import hash_password
from productpulse.security.sessions import utc_text
from productpulse.settings import Settings


PASSWORD = "Correct horse battery staple 2026"
REVIEWS_HEADER = [
    "review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text", "internal_note", "extra"
]
REVIEWS_MAPPINGS = [
    {"source_column_index": 0, "source_header": "review_id", "target_field": "review_id"},
    {"source_column_index": 1, "source_header": "product_id", "target_field": "product_id"},
    {"source_column_index": 2, "source_header": "supplier_id", "target_field": "supplier_id"},
    {"source_column_index": 3, "source_header": "batch_id", "target_field": "batch_id"},
    {"source_column_index": 4, "source_header": "review_timestamp", "target_field": "review_timestamp"},
    {"source_column_index": 5, "source_header": "review_text", "target_field": "review_text"},
    {"source_column_index": 6, "source_header": "internal_note", "target_field": "IGNORE"},
    {"source_column_index": 7, "source_header": "extra", "target_field": "IGNORE"},
]


def review_csv(*rows: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(REVIEWS_HEADER)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


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


def _sign_in(client: TestClient, email: str) -> str:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": csrf, "Origin": "https://testserver"},
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def _upload_parts(content: bytes, filename: str = "reviews.csv"):
    return {
        "upload_kind": (None, "REVIEWS"),
        "column_mappings": (None, json.dumps(REVIEWS_MAPPINGS), "application/json"),
        "file": (filename, content, "text/csv"),
    }


def _fixture_app(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    _make_user(engine, "admin@example.test", "ADMIN")
    _make_user(engine, "business@example.test", "BUSINESS_USER")
    app = create_app(settings)
    app.state.database_engine = engine
    return app, engine, settings


def test_admin_can_download_each_approved_template_and_business_user_cannot(tmp_path):
    app, engine, _settings = _fixture_app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            templates = {
                "REVIEWS": b"review_id,product_id,supplier_id,batch_id,review_timestamp,review_text,rating,source\r\n",
                "RETURNS": b"return_id,product_id,supplier_id,batch_id,return_timestamp,return_reason,return_quantity,return_category\r\n",
                "PRODUCT_REFERENCE": b"product_id,name,category\r\n",
                "SUPPLIER_REFERENCE": b"supplier_id,name\r\n",
                "BATCH_REFERENCE": b"batch_id,product_id,supplier_id\r\n",
            }
            for kind, expected in templates.items():
                response = client.get(f"/admin/ingestion/templates/{kind}")
                assert response.status_code == 200
                assert response.content == expected
                assert response.headers["content-type"].startswith("text/csv")
                assert response.headers["x-content-sha256"] == hashlib.sha256(expected).hexdigest()
                assert response.headers["cache-control"] == "no-store"

        with TestClient(app, base_url="https://testserver") as client:
            _sign_in(client, "business@example.test")
            for kind in templates:
                assert client.get(f"/admin/ingestion/templates/{kind}").status_code == 403
    finally:
        engine.dispose()


def test_admin_preview_persists_safe_row_outcomes_and_is_idempotent(tmp_path):
    app, engine, settings = _fixture_app(tmp_path)
    content = review_csv(
        ["r1", "p1", "", "", "2026-11-20T09:10:11Z", "great quality", "private note", "x"],
        ["r1", "p1", "", "", "2026-11-20T09:10:11Z", "great quality", "private note", "x"],
        ["r1", "p1", "", "", "2026-11-20T09:10:11Z", "changed quality", "private note", "x"],
        ["r2", "p2", "", "", "not-a-time", "customer details should not be returned", "private note", "x"],
    )
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "preview-001"}
            response = client.post("/admin/ingestion/previews", headers=headers, files=_upload_parts(content))
            assert response.status_code == 201, response.text
            preview = response.json()
            assert preview["state"] == "READY"
            assert preview["parser_contract_version"] == "reviews-v1"
            assert preview["verified_sha256"] == hashlib.sha256(content).hexdigest()
            assert preview["counts"] == {
                "total_rows": 4,
                "accepted_rows": 1,
                "rejected_rows": 1,
                "duplicate_noop_rows": 1,
                "conflict_rows": 1,
            }
            assert "private note" not in response.text
            assert "customer details" not in response.text
            assert preview["rejection_report"] == {
                "available": True,
                "href": f"/admin/ingestion/previews/{preview['preview_id']}/rejection-report",
                "content_type": "text/csv",
            }

            rows = client.get(f"/admin/ingestion/previews/{preview['preview_id']}/rows?page_size=100")
            assert rows.status_code == 200
            assert [item["row_status"] for item in rows.json()["items"]] == [
                "ACCEPTED", "DUPLICATE_NOOP", "CONFLICT", "REJECTED"
            ]
            assert "great quality" not in rows.text
            assert rows.json()["items"][3]["rejection_codes"] == ["INVALID_TIMESTAMP"]

            report = client.get(preview["rejection_report"]["href"])
            assert report.status_code == 200
            assert report.headers["content-type"].startswith("text/csv; charset=utf-8")
            assert report.headers["content-disposition"] == 'attachment; filename="rejection-report.csv"'
            assert report.headers["x-content-sha256"] == hashlib.sha256(report.content).hexdigest()
            assert report.headers["etag"] == f'"{hashlib.sha256(report.content).hexdigest()}"'
            report_rows = list(csv.DictReader(io.StringIO(report.text)))
            assert [row["outcome"] for row in report_rows] == ["CONFLICT", "REJECTED"]
            assert "DUPLICATE_NOOP" not in report.text
            assert "customer details" not in report.text
            assert "private note" not in report.text
            assert "great quality" not in report.text

            detail = client.get(f"/admin/ingestion/previews/{preview['preview_id']}")
            assert detail.status_code == 200 and detail.json() == preview

            replay = client.post("/admin/ingestion/previews", headers=headers, files=_upload_parts(content))
            assert replay.status_code == 200
            assert replay.json() == preview

            changed = client.post(
                "/admin/ingestion/previews",
                headers=headers,
                files=_upload_parts(review_csv(["r9", "p9", "", "", "2026-11-20T09:10:11Z", "new", "x", "y"])),
            )
            assert changed.status_code == 409
            assert changed.json()["code"] == "IDEMPOTENCY_CONFLICT"

        with Session(engine) as db:
            assert len(db.scalars(select(CsvUpload)).all()) == 1
            assert len(db.scalars(select(UploadPreview)).all()) == 1
            assert len(db.scalars(select(UploadPreviewRow)).all()) == 4
            upload_artifact_id = db.scalar(select(CsvUpload.artifact_id))
            reports = db.scalars(select(RejectionReportArtifact)).all()
            assert len(reports) == 1
            report_metadata = (reports[0].artifact_id, reports[0].file_sha256, reports[0].file_size_bytes)
        artifacts = list((settings.data_dir / "artifacts").glob("art_*.csv"))
        assert len(artifacts) == 2
        assert all(path.name.startswith("art_") and path.name.endswith(".csv") for path in artifacts)
        uploaded_artifact = next(path for path in artifacts if path.stem == upload_artifact_id)
        assert hashlib.sha256(uploaded_artifact.read_bytes()).hexdigest() == hashlib.sha256(content).hexdigest()
        report_artifact = next(path for path in artifacts if path.stem == report_metadata[0])
        assert hashlib.sha256(report_artifact.read_bytes()).hexdigest() == report_metadata[1]
        assert report_artifact.stat().st_size == report_metadata[2]
    finally:
        engine.dispose()


def test_auth_and_csrf_are_checked_before_multipart_storage(tmp_path):
    app, engine, settings = _fixture_app(tmp_path)
    try:
        body = _upload_parts(review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11Z", "text", "x", "y"]))
        with TestClient(app, base_url="https://testserver") as client:
            unauthorized = client.post("/admin/ingestion/previews", files=body)
            assert unauthorized.status_code == 401

        with TestClient(app, base_url="https://testserver") as client:
            _sign_in(client, "business@example.test")
            denied = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": "invalid", "Idempotency-Key": "denied-001"},
                files=body,
            )
            assert denied.status_code == 403

        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            invalid_csrf = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": "invalid", "Idempotency-Key": "csrf-001"},
                files=body,
            )
            assert invalid_csrf.status_code == 403

        assert list((settings.data_dir / "artifacts").glob("*")) == []
        with Session(engine) as db:
            assert db.scalar(select(CsvUpload.upload_id)) is None
            assert db.scalar(select(UploadPreview.preview_id)) is None
    finally:
        engine.dispose()


def test_upload_rejects_unsupported_extension_bad_utf8_and_streamed_oversize(tmp_path, monkeypatch):
    app, engine, settings = _fixture_app(tmp_path)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "invalid-001"}
            wrong_extension = client.post(
                "/admin/ingestion/previews", headers=headers, files=_upload_parts(b"data", "reviews.txt")
            )
            assert wrong_extension.status_code == 415
            bad_utf8 = client.post(
                "/admin/ingestion/previews",
                headers={**headers, "Idempotency-Key": "invalid-002"},
                files=_upload_parts(b"\xff,not,utf8\r\n"),
            )
            assert bad_utf8.status_code == 422

            monkeypatch.setattr("productpulse.ingestion_api.MAX_FILE_BYTES", 64)
            too_large = client.post(
                "/admin/ingestion/previews",
                headers={**headers, "Idempotency-Key": "invalid-003"},
                files=_upload_parts(b"x" * 65),
            )
            assert too_large.status_code == 413
        with Session(engine) as db:
            assert db.scalar(select(CsvUpload.upload_id)) is None
            assert db.scalar(select(UploadPreview.preview_id)) is None
        assert list((settings.data_dir / "artifacts").glob("*")) == []
    finally:
        engine.dispose()


def test_file_part_limit_is_inclusive_and_counts_file_bytes_while_streaming(tmp_path, monkeypatch):
    app, engine, _settings = _fixture_app(tmp_path)
    content = b"product_id\r\np1"
    assert len(content) == 14
    parts = {
        "upload_kind": (None, "PRODUCT_REFERENCE"),
        "column_mappings": (None, json.dumps([
            {"source_column_index": 0, "source_header": "product_id", "target_field": "product_id"}
        ]), "application/json"),
        "file": ("products.csv", content, "text/csv"),
    }
    try:
        monkeypatch.setattr("productpulse.ingestion_api.MAX_FILE_BYTES", len(content))
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            allowed = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "at-limit-001"},
                files=parts,
            )
            assert allowed.status_code == 201
            assert allowed.json()["file_size_bytes"] == len(content)
            monkeypatch.setattr("productpulse.ingestion_api.MAX_FILE_BYTES", len(content) - 1)
            over = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "over-limit-001"},
                files=parts,
            )
            assert over.status_code == 413
    finally:
        engine.dispose()


def test_preview_compares_existing_source_hashes_without_overwriting_records(tmp_path):
    app, engine, _settings = _fixture_app(tmp_path)
    original = review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11Z", "original", "x", "y"])
    artifact = tmp_path / "original.csv"
    artifact.write_bytes(original)
    source = parse_preview(artifact, "REVIEWS", REVIEWS_MAPPINGS).rows[0]
    now = utc_text()
    stored_preview = "prv_stored_existing"
    stored_job = "ing_stored_existing"
    stored_user = "usr_admin_admin"
    with Session(engine) as db:
        db.add(Product(product_id="p1", name=None, category=None, created_at=now, updated_at=now))
        db.add(CsvUpload(
            upload_id="upl_stored_existing", upload_kind="REVIEWS", original_filename="original.csv",
            artifact_id="art_" + "3" * 32, file_size_bytes=len(original), file_sha256=hashlib.sha256(original).hexdigest(),
            uploaded_by=stored_user, uploaded_at=now,
        ))
        db.add(UploadPreview(
            preview_id=stored_preview, preview_idempotency_key="stored-preview-001", preview_request_sha256="0" * 64,
            upload_id="upl_stored_existing", verified_sha256=hashlib.sha256(original).hexdigest(),
            parser_contract_version="reviews-v1", column_mappings_text=json.dumps(REVIEWS_MAPPINGS),
            state="CONFIRMED", total_row_count=1, accepted_row_count=1, rejected_row_count=0,
            duplicate_row_count=0, conflict_row_count=0, created_at=now, confirmed_by=stored_user, confirmed_at=now,
        ))
        db.flush()
        db.add(UploadPreviewRow(
            preview_id=stored_preview, row_number=1, row_status="ACCEPTED", source_type="REVIEW",
            source_record_id="r1", normalized_row_text=source.normalized_row_text,
            row_payload_sha256=source.row_payload_sha256, rejection_codes_text=None, rejection_detail=None, created_at=now,
        ))
        db.add(IngestionJob(
            job_id=stored_job, preview_id=stored_preview, idempotency_key="stored-confirm-001",
            processing_mode="HISTORICAL_BATCH", status="QUEUED", total_row_count=1, accepted_row_count=1,
            rejected_row_count=0, duplicate_row_count=0, conflict_row_count=0, persisted_feedback_count=1,
            created_at=now, started_at=None, completed_at=None, last_error_code=None,
        ))
        db.flush()
        db.add(Feedback(
            feedback_id="fdb_stored_existing", source_type="REVIEW", source_record_id="r1", product_id="p1",
            supplier_id=None, batch_id=None, reported_supplier_id=None, reported_batch_id=None,
            linkage_status="LINKAGE_PENDING", event_time_utc="2026-11-20T09:10:11.000Z", feedback_text="original",
            rating=None, source_label=None, return_quantity=None, return_category=None,
            payload_sha256=source.row_payload_sha256, record_origin="CSV_UPLOAD", ingestion_job_id=stored_job,
            origin_preview_id=stored_preview, origin_row_number=1, origin_manifest_ref=None, ingested_at=now,
        ))
        db.commit()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            duplicate = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "stored-duplicate-001"},
                files=_upload_parts(original),
            )
            assert duplicate.status_code == 201
            assert duplicate.json()["state"] == "INVALID"
            assert duplicate.json()["counts"]["duplicate_noop_rows"] == 1
            conflict = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "stored-conflict-001"},
                files=_upload_parts(review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11Z", "changed", "x", "y"])),
            )
            assert conflict.status_code == 201
            assert conflict.json()["state"] == "INVALID"
            assert conflict.json()["counts"]["conflict_rows"] == 1
            row = client.get(f"/admin/ingestion/previews/{conflict.json()['preview_id']}/rows").json()["items"][0]
            assert row["row_status"] == "CONFLICT"
            assert row["rejection_codes"] == ["SOURCE_PAYLOAD_CONFLICT"]
        with Session(engine) as db:
            existing = db.scalar(select(Feedback).where(Feedback.source_type == "REVIEW", Feedback.source_record_id == "r1"))
            assert existing is not None and existing.feedback_text == "original"
    finally:
        engine.dispose()


def test_artifact_reconciliation_preserves_referenced_files_and_rejects_invalid_ids(tmp_path):
    store = ArtifactStore(Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000))
    referenced = "art_" + "1" * 32
    orphan = "art_" + "2" * 32
    store.root.mkdir(parents=True)
    (store.root / f"{referenced}.csv").write_bytes(b"kept")
    (store.root / f"{orphan}.csv").write_bytes(b"orphan")
    (store.root / "unrelated.csv").write_bytes(b"not a ProductPulse artifact")
    assert store.reconcile_unreferenced({referenced}) == 1
    assert (store.root / f"{referenced}.csv").read_bytes() == b"kept"
    assert not (store.root / f"{orphan}.csv").exists()
    assert (store.root / "unrelated.csv").exists()
    assert store.verified_path(referenced, hashlib.sha256(b"kept").hexdigest()).read_bytes() == b"kept"
    with pytest.raises(ArtifactIntegrityError):
        store.verified_path("../../outside", hashlib.sha256(b"kept").hexdigest())


def test_database_insert_failure_removes_published_artifact(tmp_path):
    app, engine, settings = _fixture_app(tmp_path)
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TRIGGER fail_csv_upload_insert BEFORE INSERT ON csv_uploads "
                "BEGIN SELECT RAISE(ABORT, 'injected database failure'); END"
            ))
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            response = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "db-failure-001"},
                files=_upload_parts(review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11Z", "text", "x", "y"])),
            )
            assert response.status_code == 503
        assert list((settings.data_dir / "artifacts").glob("art_*.csv")) == []
        with Session(engine) as db:
            assert db.scalar(select(UploadPreview.preview_id)) is None
    finally:
        engine.dispose()


def test_parser_bom_timestamp_field_lengths_row_cap_and_stored_identity_conflicts(tmp_path, monkeypatch):
    path = tmp_path / "input.csv"
    path.write_bytes(review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11.12+01:00", "text", "", ""]))
    parsed = parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS)
    assert parsed.rows[0].normalized_row_text is not None
    assert '"review_timestamp":"2026-11-20T08:10:11.120Z"' in parsed.rows[0].normalized_row_text
    identical = parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS, {("REVIEW", "r1"): parsed.rows[0].row_payload_sha256})
    assert identical.rows[0].row_status == "DUPLICATE_NOOP"
    changed = parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS, {("REVIEW", "r1"): "0" * 64})
    assert changed.rows[0].row_status == "CONFLICT"

    path.write_bytes(b"\xef\xbb\xbf" + review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11Z", "text", "", ""]))
    assert parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS).rows[0].row_status == "ACCEPTED"
    path.write_bytes(review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11Z", "x" * 16_385, "", ""]))
    assert "FIELD_TOO_LONG" in parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS).rows[0].rejection_codes
    path.write_bytes(review_csv(["r1", "p1", "", "", "2026-11-20T09:10:11Z", "x" * 200_000, "", ""]))
    oversized_field = parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS).rows[0]
    assert oversized_field.row_status == "REJECTED" and "FIELD_TOO_LONG" in oversized_field.rejection_codes
    path.write_bytes(review_csv(["r" * 257, "p1", "", "", "2026-11-20T09:10:11Z", "text", "", ""]))
    invalid_identifier = parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS).rows[0]
    assert invalid_identifier.source_record_id is None
    assert "FIELD_TOO_LONG" in invalid_identifier.rejection_codes
    path.write_bytes(review_csv() + b"\r\n\r\n\r\n")
    monkeypatch.setattr(parser, "MAX_DATA_ROWS", 2)
    try:
        parse_preview(path, "REVIEWS", REVIEWS_MAPPINGS)
    except CsvInputError as error:
        assert error.code == "CSV_ROW_LIMIT_EXCEEDED"
    else:
        raise AssertionError("row limit should reject a file with one row over the configured cap")
