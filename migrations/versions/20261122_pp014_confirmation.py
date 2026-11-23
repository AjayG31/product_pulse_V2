"""Create the feedback import job and source-record tables."""

from alembic import op
import sqlalchemy as sa


revision = "pp014_confirmation_001"
down_revision = "pp013_previews_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("product_id", sa.String(length=256), primary_key=True),
        sa.Column("name", sa.String(length=1024), nullable=True),
        sa.Column("category", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("updated_at", sa.String(length=24), nullable=False),
    )
    op.create_table(
        "suppliers",
        sa.Column("supplier_id", sa.String(length=256), primary_key=True),
        sa.Column("name", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("updated_at", sa.String(length=24), nullable=False),
    )
    op.create_table(
        "batches",
        sa.Column("batch_id", sa.String(length=256), primary_key=True),
        sa.Column("product_id", sa.String(length=256), sa.ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.String(length=256), sa.ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("updated_at", sa.String(length=24), nullable=False),
        sa.UniqueConstraint("batch_id", "product_id", "supplier_id", name="uq_batches_linkage"),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.String(length=36), primary_key=True),
        sa.Column("preview_id", sa.String(length=36), sa.ForeignKey("upload_previews.preview_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("processing_mode", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"),
        sa.Column("total_row_count", sa.Integer(), nullable=False),
        sa.Column("accepted_row_count", sa.Integer(), nullable=False),
        sa.Column("rejected_row_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("persisted_feedback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.String(length=24), nullable=True),
        sa.Column("completed_at", sa.String(length=24), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.CheckConstraint(
            "processing_mode IS NULL OR processing_mode IN ('HISTORICAL_BATCH', 'INCREMENTAL_RESPONSES')",
            name="ck_ingestion_jobs_mode",
        ),
        sa.CheckConstraint("status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')", name="ck_ingestion_jobs_status"),
        sa.CheckConstraint("total_row_count >= 0", name="ck_ingestion_jobs_total_rows"),
        sa.CheckConstraint("accepted_row_count >= 0", name="ck_ingestion_jobs_accepted_rows"),
        sa.CheckConstraint("rejected_row_count >= 0", name="ck_ingestion_jobs_rejected_rows"),
        sa.CheckConstraint("duplicate_row_count >= 0", name="ck_ingestion_jobs_duplicate_rows"),
        sa.CheckConstraint("conflict_row_count >= 0", name="ck_ingestion_jobs_conflict_rows"),
        sa.CheckConstraint("persisted_feedback_count >= 0", name="ck_ingestion_jobs_persisted_rows"),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'PARTIAL', 'FAILED') AND completed_at IS NOT NULL)",
            name="ck_ingestion_jobs_status_timestamps",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_ingestion_jobs_timestamp_order",
        ),
        sa.UniqueConstraint("preview_id", name="uq_ingestion_jobs_preview_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ingestion_jobs_idempotency_key"),
        sa.UniqueConstraint("preview_id", "job_id", name="uq_ingestion_jobs_preview_job"),
    )
    op.create_index("ix_ingestion_jobs_status_created", "ingestion_jobs", ["status", "created_at"])
    op.create_table(
        "background_jobs",
        sa.Column("background_job_id", sa.String(length=36), primary_key=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("work_key", sa.String(length=256), nullable=False),
        sa.Column("ingestion_job_id", sa.String(length=36), sa.ForeignKey("ingestion_jobs.job_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.String(length=24), nullable=False),
        sa.Column("next_attempt_at", sa.String(length=24), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.String(length=24), nullable=True),
        sa.Column("provider_input_file_id", sa.String(length=256), nullable=True),
        sa.Column("provider_batch_id", sa.String(length=256), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.String(length=24), nullable=True),
        sa.Column("completed_at", sa.String(length=24), nullable=True),
        sa.CheckConstraint(
            "job_type IN ('INGESTION', 'CLASSIFICATION', 'BATCH_POLL', 'DETECTION', 'RECONCILIATION')",
            name="ck_background_jobs_type",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRY_WAIT', 'COMPLETED', 'PARTIAL', 'FAILED')",
            name="ck_background_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_background_jobs_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_background_jobs_max_attempts"),
        sa.CheckConstraint(
            "((status IN ('QUEUED', 'RETRY_WAIT')) AND completed_at IS NULL AND worker_id IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL AND worker_id IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status IN ('COMPLETED', 'PARTIAL', 'FAILED') AND completed_at IS NOT NULL AND worker_id IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_background_jobs_status_timestamps",
        ),
        sa.CheckConstraint("next_attempt_at IS NULL OR status = 'RETRY_WAIT'", name="ck_background_jobs_next_attempt_state"),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_background_jobs_timestamp_order",
        ),
        sa.UniqueConstraint("work_key", name="uq_background_jobs_work_key"),
    )
    op.create_index(
        "ix_background_jobs_status_schedule",
        "background_jobs",
        ["status", "next_attempt_at", "scheduled_at"],
    )
    op.create_index(
        "ix_background_jobs_lease_expires",
        "background_jobs",
        ["lease_expires_at"],
        sqlite_where=sa.text("lease_expires_at IS NOT NULL"),
    )
    op.create_index(
        "uq_background_jobs_provider_input",
        "background_jobs",
        ["provider_input_file_id"],
        unique=True,
        sqlite_where=sa.text("provider_input_file_id IS NOT NULL"),
    )

    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_record_id", sa.String(length=256), nullable=False),
        sa.Column("product_id", sa.String(length=256), sa.ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.String(length=256), sa.ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("batch_id", sa.String(length=256), nullable=True),
        sa.Column("reported_supplier_id", sa.String(length=256), nullable=True),
        sa.Column("reported_batch_id", sa.String(length=256), nullable=True),
        sa.Column("linkage_status", sa.String(length=24), nullable=False),
        sa.Column("event_time_utc", sa.String(length=24), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("source_label", sa.String(length=1024), nullable=True),
        sa.Column("return_quantity", sa.Integer(), nullable=True),
        sa.Column("return_category", sa.String(length=1024), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("record_origin", sa.String(length=24), nullable=False),
        sa.Column("ingestion_job_id", sa.String(length=36), nullable=True),
        sa.Column("origin_preview_id", sa.String(length=36), nullable=True),
        sa.Column("origin_row_number", sa.Integer(), nullable=True),
        sa.Column("origin_manifest_ref", sa.String(length=512), nullable=True),
        sa.Column("ingested_at", sa.String(length=24), nullable=False),
        sa.CheckConstraint("source_type IN ('REVIEW', 'RETURN')", name="ck_feedback_source_type"),
        sa.CheckConstraint("linkage_status IN ('LINKED', 'LINKAGE_PENDING')", name="ck_feedback_linkage_status"),
        sa.CheckConstraint("(linkage_status <> 'LINKED') OR (supplier_id IS NOT NULL AND batch_id IS NOT NULL)", name="ck_feedback_linked_values"),
        sa.CheckConstraint("batch_id IS NULL OR supplier_id IS NOT NULL", name="ck_feedback_batch_supplier"),
        sa.CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
        sa.CheckConstraint("return_quantity IS NULL OR return_quantity > 0", name="ck_feedback_return_quantity"),
        sa.CheckConstraint(
            "(source_type = 'REVIEW' AND return_quantity IS NULL AND return_category IS NULL) OR "
            "(source_type = 'RETURN' AND rating IS NULL AND source_label IS NULL)",
            name="ck_feedback_source_fields",
        ),
        sa.CheckConstraint(
            "(record_origin = 'CSV_UPLOAD' AND ingestion_job_id IS NOT NULL AND origin_preview_id IS NOT NULL "
            "AND origin_row_number IS NOT NULL AND origin_manifest_ref IS NULL) OR "
            "(record_origin = 'SYNTHETIC_SEED' AND ingestion_job_id IS NULL AND origin_preview_id IS NULL "
            "AND origin_row_number IS NULL AND origin_manifest_ref IS NOT NULL)",
            name="ck_feedback_origin_lineage",
        ),
        sa.UniqueConstraint("source_type", "source_record_id", name="uq_feedback_source_identity"),
        sa.UniqueConstraint("origin_preview_id", "origin_row_number", name="uq_feedback_origin_row"),
        sa.ForeignKeyConstraint(
            ["origin_preview_id", "ingestion_job_id"],
            ["ingestion_jobs.preview_id", "ingestion_jobs.job_id"],
            name="fk_feedback_origin_job_preview",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_preview_id", "origin_row_number"],
            ["upload_preview_rows.preview_id", "upload_preview_rows.row_number"],
            name="fk_feedback_origin_preview_row",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "product_id", "supplier_id"],
            ["batches.batch_id", "batches.product_id", "batches.supplier_id"],
            name="fk_feedback_batch_linkage",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_feedback_event_time", "feedback", ["event_time_utc"])
    op.create_index("ix_feedback_product_event_time", "feedback", ["product_id", "event_time_utc"])
    op.create_index("ix_feedback_ingestion_job", "feedback", ["ingestion_job_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_ingestion_job", table_name="feedback")
    op.drop_index("ix_feedback_product_event_time", table_name="feedback")
    op.drop_index("ix_feedback_event_time", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("uq_background_jobs_provider_input", table_name="background_jobs")
    op.drop_index("ix_background_jobs_lease_expires", table_name="background_jobs")
    op.drop_index("ix_background_jobs_status_schedule", table_name="background_jobs")
    op.drop_table("background_jobs")
    op.drop_index("ix_ingestion_jobs_status_created", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_table("batches")
    op.drop_table("suppliers")
    op.drop_table("products")
