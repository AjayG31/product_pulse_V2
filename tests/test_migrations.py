from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from productpulse.settings import Settings


def test_schema_version_migration_creates_identity_tables(tmp_path, monkeypatch):
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert config.get_main_option("script_location") == "migrations"
    assert script.get_heads() == ["pp014_confirmation_001"]
    monkeypatch.setenv("PRODUCTPULSE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS", "731")
    command.upgrade(config, "head")
    from productpulse.database import create_database_engine

    engine = create_database_engine(Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=731))
    try:
        inspector = inspect(engine)
        assert {
            "users", "sessions", "audit_events", "csv_uploads", "upload_previews",
            "upload_preview_rows", "products", "suppliers", "batches", "feedback", "ingestion_jobs", "background_jobs",
            "alembic_version",
        }.issubset(inspector.get_table_names())
        assert inspector.get_unique_constraints("users")[0]["column_names"] == ["email_normalized"]
        preview_checks = {item["name"] for item in inspector.get_check_constraints("upload_previews")}
        row_checks = {item["name"] for item in inspector.get_check_constraints("upload_preview_rows")}
        assert "ck_upload_previews_count_total" in preview_checks
        assert {"ck_upload_preview_rows_snapshot", "ck_upload_preview_rows_source_identity"}.issubset(row_checks)
        upload_indexes = {item["name"] for item in inspector.get_indexes("csv_uploads")}
        assert "ix_csv_uploads_uploaded_by_at" in upload_indexes
        background_checks = {item["name"] for item in inspector.get_check_constraints("background_jobs")}
        assert {"ck_background_jobs_max_attempts", "ck_background_jobs_status_timestamps"}.issubset(background_checks)
        background_indexes = {item["name"] for item in inspector.get_indexes("background_jobs")}
        assert {"ix_background_jobs_status_schedule", "ix_background_jobs_lease_expires", "uq_background_jobs_provider_input"}.issubset(background_indexes)
    finally:
        engine.dispose()

