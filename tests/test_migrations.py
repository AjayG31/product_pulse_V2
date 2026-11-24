from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from productpulse.settings import Settings


def test_schema_version_migration_creates_identity_tables(tmp_path, monkeypatch):
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert config.get_main_option("script_location") == "migrations"
    assert script.get_heads() == ["pp015_reconciliation_001"]
    monkeypatch.setenv("PRODUCTPULSE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", "731")
    from productpulse.database import create_database_engine

    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=731)
    command.upgrade(config, "pp014_confirmation_001")
    prior_engine = create_database_engine(settings)
    try:
        with prior_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO background_jobs "
                    "(background_job_id, job_type, work_key, status, attempt_count, max_attempts, scheduled_at, created_at) "
                    "VALUES (:id, 'CLASSIFICATION', :work_key, 'QUEUED', 0, 3, :at, :at)"
                ),
                {"id": "existing-classification", "work_key": "classification:existing", "at": "2026-11-24T00:00:00.000Z"},
            )
    finally:
        prior_engine.dispose()

    command.upgrade(config, "head")
    engine = create_database_engine(settings)
    try:
        inspector = inspect(engine)
        assert {
            "users", "sessions", "audit_events", "csv_uploads", "upload_previews",
            "upload_preview_rows", "products", "suppliers", "batches", "feedback", "ingestion_jobs", "background_jobs",
            "background_job_attempts", "rejection_report_artifacts", "ingestion_conflicts",
            "feedback_linkage_events", "taxonomy_versions", "taxonomy_categories", "taxonomy_issue_codes",
            "logical_defects", "classifications", "classification_labels", "detection_rule_versions",
            "defect_clusters", "detection_results",
            "alembic_version",
        }.issubset(inspector.get_table_names())
        assert inspector.get_unique_constraints("users")[0]["column_names"] == ["email_normalized"]
        preview_checks = {item["name"] for item in inspector.get_check_constraints("upload_previews")}
        row_checks = {item["name"] for item in inspector.get_check_constraints("upload_preview_rows")}
        assert "ck_upload_previews_count_total" in preview_checks
        assert {"ck_upload_preview_rows_snapshot", "ck_upload_preview_rows_source_identity"}.issubset(row_checks)
        upload_indexes = {item["name"] for item in inspector.get_indexes("csv_uploads")}
        assert "ix_csv_uploads_uploaded_by_at" in upload_indexes
        report_checks = {item["name"] for item in inspector.get_check_constraints("rejection_report_artifacts")}
        assert {
            "ck_rejection_report_artifacts_size",
            "ck_rejection_report_artifacts_hash_length",
        }.issubset(report_checks)
        report_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("rejection_report_artifacts")}
        assert ("preview_id",) in report_unique
        background_checks = {item["name"] for item in inspector.get_check_constraints("background_jobs")}
        assert {
            "ck_background_jobs_max_attempts",
            "ck_background_jobs_approved_budget",
            "ck_background_jobs_status_timestamps",
        }.issubset(background_checks)
        background_columns = {item["name"]: item for item in inspector.get_columns("background_jobs")}
        assert background_columns["max_attempts"]["nullable"] is True
        assert background_columns["taxonomy_version_id"]["nullable"] is True
        attempt_checks = {item["name"] for item in inspector.get_check_constraints("background_job_attempts")}
        assert {
            "ck_background_job_attempts_outcome",
            "ck_background_job_attempts_finished_state",
            "ck_background_job_attempts_next_attempt",
        }.issubset(attempt_checks)
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT status || ':' || attempt_count || ':' || max_attempts "
                    "FROM background_jobs WHERE background_job_id = 'existing-classification'"
                )
            ).scalar_one() == "QUEUED:0:3"
            assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        background_indexes = {item["name"] for item in inspector.get_indexes("background_jobs")}
        assert {"ix_background_jobs_status_schedule", "ix_background_jobs_lease_expires", "uq_background_jobs_provider_input", "uq_background_jobs_id_taxonomy"}.issubset(background_indexes)
        with engine.connect() as connection:
            triggers = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))}
            assert {
                "trg_background_jobs_taxonomy_insert", "trg_background_jobs_taxonomy_update",
                "trg_feedback_linkage_events_no_update", "trg_feedback_linkage_events_no_delete",
                "trg_detection_rule_versions_immutable_config", "trg_detection_results_no_update",
                "trg_detection_results_no_delete",
            }.issubset(triggers)
    finally:
        engine.dispose()


def test_pp018_downgrade_refuses_to_drop_an_unbudgeted_job(tmp_path, monkeypatch):
    config = Config("alembic.ini")
    monkeypatch.setenv("PRODUCTPULSE_DATA_DIR", str(tmp_path / "downgrade-data"))
    monkeypatch.setenv("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", "5000")
    command.upgrade(config, "head")

    from productpulse.database import create_database_engine

    engine = create_database_engine(Settings(data_dir=tmp_path / "downgrade-data", sqlite_busy_timeout_ms=5000))
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO background_jobs "
                    "(background_job_id, job_type, work_key, status, attempt_count, max_attempts, scheduled_at, created_at) "
                    "VALUES ('unbudgeted-batch', 'BATCH_POLL', 'batch:unbudgeted', 'QUEUED', 0, NULL, "
                    "'2026-11-24T00:00:00.000Z', '2026-11-24T00:00:00.000Z')"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="Cannot downgrade while unbudgeted background jobs exist"):
        command.downgrade(config, "pp014_confirmation_001")


def test_pp018_downgrade_restores_the_prior_budget_schema(tmp_path, monkeypatch):
    config = Config("alembic.ini")
    data_dir = tmp_path / "reversible-data"
    monkeypatch.setenv("PRODUCTPULSE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", "5000")
    command.upgrade(config, "head")
    command.downgrade(config, "pp014_confirmation_001")

    from productpulse.database import create_database_engine

    engine = create_database_engine(Settings(data_dir=data_dir, sqlite_busy_timeout_ms=5000))
    try:
        inspector = inspect(engine)
        assert "background_job_attempts" not in inspector.get_table_names()
        assert "rejection_report_artifacts" not in inspector.get_table_names()
        background_columns = {item["name"]: item for item in inspector.get_columns("background_jobs")}
        assert background_columns["max_attempts"]["nullable"] is False
        background_checks = {item["name"] for item in inspector.get_check_constraints("background_jobs")}
        assert "ck_background_jobs_approved_budget" not in background_checks
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()


def test_pp015_refuses_to_guess_taxonomy_for_existing_detection_work(tmp_path, monkeypatch):
    config = Config("alembic.ini")
    data_dir = tmp_path / "unversioned-detection"
    monkeypatch.setenv("PRODUCTPULSE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", "5000")
    command.upgrade(config, "pp034_rejection_reports_001")

    from productpulse.database import create_database_engine

    engine = create_database_engine(Settings(data_dir=data_dir, sqlite_busy_timeout_ms=5000))
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO background_jobs "
                "(background_job_id, job_type, work_key, status, attempt_count, max_attempts, scheduled_at, created_at) "
                "VALUES ('legacy-detection', 'DETECTION', 'legacy-detection-work', 'QUEUED', 0, 3, "
                "'2026-11-24T00:00:00.000Z', '2026-11-24T00:00:00.000Z')"
            ))
        with pytest.raises(RuntimeError, match="unversioned DETECTION jobs"):
            command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "pp034_rejection_reports_001"
            assert connection.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='taxonomy_versions'")).scalar_one() == 0
    finally:
        engine.dispose()


def test_pp015_enforces_explicit_immutable_detection_context(tmp_path, monkeypatch):
    config = Config("alembic.ini")
    data_dir = tmp_path / "taxonomy-context"
    monkeypatch.setenv("PRODUCTPULSE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", "5000")
    command.upgrade(config, "head")

    from productpulse.database import create_database_engine

    engine = create_database_engine(Settings(data_dir=data_dir, sqlite_busy_timeout_ms=5000))
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (user_id, email, email_normalized, password_hash, role, status, must_change_password, created_at, updated_at) "
                "VALUES ('usr-taxonomy-test', 'taxonomy@example.test', 'taxonomy@example.test', 'test-hash', 'ADMIN', 'ACTIVE', 0, "
                "'2026-11-24T00:00:00.000Z', '2026-11-24T00:00:00.000Z')"
            ))
            for taxonomy_id, label in (("tax-a", "taxonomy-a"), ("tax-b", "taxonomy-b")):
                connection.execute(text(
                    "INSERT INTO taxonomy_versions (taxonomy_version_id, version_label, state, created_by, created_at) "
                    "VALUES (:id, :label, 'DRAFT', 'usr-taxonomy-test', '2026-11-24T00:00:00.000Z')"
                ), {"id": taxonomy_id, "label": label})
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO background_jobs "
                    "(background_job_id, job_type, work_key, status, attempt_count, max_attempts, scheduled_at, created_at) "
                    "VALUES ('missing-taxonomy', 'DETECTION', 'missing-taxonomy-work', 'QUEUED', 0, 3, "
                    "'2026-11-24T00:00:00.000Z', '2026-11-24T00:00:00.000Z')"
                ))
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO background_jobs "
                "(background_job_id, job_type, taxonomy_version_id, work_key, status, attempt_count, max_attempts, scheduled_at, created_at) "
                "VALUES ('versioned-detection', 'DETECTION', 'tax-a', 'versioned-detection-work', 'QUEUED', 0, 3, "
                "'2026-11-24T00:00:00.000Z', '2026-11-24T00:00:00.000Z')"
            ))
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("UPDATE background_jobs SET taxonomy_version_id = 'tax-b' WHERE background_job_id = 'versioned-detection'"))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT taxonomy_version_id FROM background_jobs WHERE background_job_id = 'versioned-detection'")).scalar_one() == "tax-a"
    finally:
        engine.dispose()

