import csv
import hashlib
import io
import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from productpulse.database import create_database_engine
from productpulse.ingestion.artifacts import ArtifactStore
from productpulse.main import create_app
from productpulse.models import Base, Feedback, RejectionReportArtifact, User
from productpulse.security.identity import normalize_email
from productpulse.security.passwords import hash_password
from productpulse.security.sessions import utc_text
from productpulse.settings import Settings


PASSWORD = "Correct horse battery staple 2026"
HEADERS = ["=review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"]
MAPPINGS = [
    {"source_column_index": index, "source_header": header, "target_field": target}
    for index, (header, target) in enumerate(zip(
        HEADERS,
        ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"],
        strict=True,
    ))
]


def _csv_bytes() -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(HEADERS)
    writer.writerows(
        [
            ["=2+2", "p1", "", "", "2026-11-20T09:10:11Z", "=HYPERLINK(\"https://example.test\",\"feedback\")"],
            ["=2+2", "p1", "", "", "2026-11-20T09:10:11Z", "changed feedback must stay private"],
            ["+3+4", "p1", "", "", "not-a-time", "@SUM(1,1)"],
            ["@SUM(2,2)", "p1", "", "", "not-a-time", "-1+1"],
        ]
    )
    return output.getvalue().encode("utf-8")


def _make_user(engine, email: str, role: str) -> None:
    display, normalized = normalize_email(email)
    with Session(engine) as db:
        db.add(
            User(
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
            )
        )
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


def test_report_is_formula_safe_authorized_and_keeps_source_data_unmodified(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    _make_user(engine, "admin@example.test", "ADMIN")
    _make_user(engine, "business@example.test", "BUSINESS_USER")
    app = create_app(settings)
    app.state.database_engine = engine
    content = _csv_bytes()
    try:
        with TestClient(app, base_url="https://testserver") as admin:
            csrf = _sign_in(admin, "admin@example.test")
            preview_response = admin.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "formula-report-001"},
                files={
                    "upload_kind": (None, "REVIEWS"),
                    "column_mappings": (None, json.dumps(MAPPINGS), "application/json"),
                    "file": ("formula.csv", content, "text/csv"),
                },
            )
            assert preview_response.status_code == 201, preview_response.text
            preview = preview_response.json()
            link = preview["rejection_report"]
            assert link["available"] is True
            assert link["content_type"] == "text/csv"
            assert "=review_id" not in link["href"]

            report = admin.get(link["href"])
            assert report.status_code == 200
            assert report.headers["x-content-sha256"] == hashlib.sha256(report.content).hexdigest()
            rows = list(csv.DictReader(io.StringIO(report.text)))
            assert [row["outcome"] for row in rows] == ["CONFLICT", "REJECTED", "REJECTED"]
            assert list(rows[0]) == [
                "row_number", "outcome", "source_type", "source_record_id", "reason_code", "safe_explanation"
            ]
            assert [row["source_record_id"] for row in rows] == ["'=2+2", "'+3+4", "'@SUM(2,2)"]
            assert all(row["source_record_id"].startswith("'") for row in rows)
            assert "INVALID_TIMESTAMP" in report.text
            assert "=review_id" not in report.text
            assert "HYPERLINK" not in report.text
            assert "changed feedback must stay private" not in report.text
            assert "@SUM(1,1)" not in report.text
            assert "-1+1" not in report.text
            assert "DUPLICATE_NOOP" not in report.text

            metadata = admin.get(f"/admin/ingestion/previews/{preview['preview_id']}")
            assert metadata.status_code == 200
            assert metadata.json()["rejection_report"] == link

        with TestClient(app, base_url="https://testserver") as business:
            _sign_in(business, "business@example.test")
            denied = business.get(link["href"])
            assert denied.status_code == 403
            assert b"HYPERLINK" not in denied.content
            assert b"changed feedback" not in denied.content

        with Session(engine) as db:
            assert db.scalars(select(Feedback)).all() == []
            report_metadata = db.scalar(select(RejectionReportArtifact))
            assert report_metadata is not None
            artifact_id = report_metadata.artifact_id
            digest = report_metadata.file_sha256
            size = report_metadata.file_size_bytes
        report_path = ArtifactStore(settings)._path_for_id(artifact_id)
        assert hashlib.sha256(report_path.read_bytes()).hexdigest() == digest
        assert report_path.stat().st_size == size
    finally:
        engine.dispose()


def test_preview_without_rejected_or_conflicting_rows_has_no_report(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    _make_user(engine, "admin@example.test", "ADMIN")
    app = create_app(settings)
    app.state.database_engine = engine
    clean_headers = ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"]
    mappings = [
        {"source_column_index": index, "source_header": header, "target_field": target}
        for index, (header, target) in enumerate(zip(
            clean_headers,
            ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"],
            strict=True,
        ))
    ]
    clean = b"review_id,product_id,supplier_id,batch_id,review_timestamp,review_text\r\nr1,p1,,,2026-11-20T09:10:11Z,good\r\n"
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            response = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "clean-preview-001"},
                files={
                    "upload_kind": (None, "REVIEWS"),
                    "column_mappings": (None, json.dumps(mappings), "application/json"),
                    "file": ("clean.csv", clean, "text/csv"),
                },
            )
            assert response.status_code == 201, response.text
            preview = response.json()
            assert preview["rejection_report"] == {"available": False}
            assert client.get(f"/admin/ingestion/previews/{preview['preview_id']}/rejection-report").status_code == 404
        with Session(engine) as db:
            assert db.scalar(select(RejectionReportArtifact)) is None
    finally:
        engine.dispose()


def test_report_download_fails_closed_when_protected_artifact_hash_changes(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    _make_user(engine, "admin@example.test", "ADMIN")
    app = create_app(settings)
    app.state.database_engine = engine
    content = _csv_bytes()
    try:
        with TestClient(app, base_url="https://testserver") as client:
            csrf = _sign_in(client, "admin@example.test")
            response = client.post(
                "/admin/ingestion/previews",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "tamper-report-001"},
                files={
                    "upload_kind": (None, "REVIEWS"),
                    "column_mappings": (None, json.dumps(MAPPINGS), "application/json"),
                    "file": ("formula.csv", content, "text/csv"),
                },
            )
            assert response.status_code == 201, response.text
            link = response.json()["rejection_report"]
            metadata = client.get(f"/admin/ingestion/previews/{response.json()['preview_id']}").json()
            assert metadata["rejection_report"] == link
            with Session(engine) as db:
                artifact_id = db.scalar(select(RejectionReportArtifact.artifact_id))
            report_path = ArtifactStore(settings)._path_for_id(artifact_id)
            report_path.write_bytes(report_path.read_bytes() + b"tampered")
            failed = client.get(link["href"])
            assert failed.status_code == 503
            assert failed.json()["code"] == "REJECTION_REPORT_UNAVAILABLE"
            assert "tampered" not in failed.text
    finally:
        engine.dispose()
