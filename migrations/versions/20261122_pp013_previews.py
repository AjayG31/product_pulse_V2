"""Create protected CSV upload and immutable preview tables."""

from alembic import op
import sqlalchemy as sa


revision = "pp013_previews_001"
down_revision = "pp012_auth_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "csv_uploads",
        sa.Column("upload_id", sa.String(length=36), primary_key=True),
        sa.Column("upload_kind", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_at", sa.String(length=24), nullable=False),
        sa.CheckConstraint(
            "upload_kind IN ('REVIEWS', 'RETURNS', 'PRODUCT_REFERENCE', 'SUPPLIER_REFERENCE', 'BATCH_REFERENCE')",
            name="ck_csv_uploads_kind",
        ),
        sa.CheckConstraint("file_size_bytes BETWEEN 1 AND 20000000", name="ck_csv_uploads_size"),
        sa.CheckConstraint("length(file_sha256) = 64", name="ck_csv_uploads_hash_length"),
        sa.UniqueConstraint("artifact_id", name="uq_csv_uploads_artifact_id"),
    )
    op.create_index("ix_csv_uploads_uploaded_by_at", "csv_uploads", ["uploaded_by", "uploaded_at"])

    op.create_table(
        "upload_previews",
        sa.Column("preview_id", sa.String(length=36), primary_key=True),
        sa.Column("preview_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("preview_request_sha256", sa.String(length=64), nullable=False),
        sa.Column("upload_id", sa.String(length=36), sa.ForeignKey("csv_uploads.upload_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("verified_sha256", sa.String(length=64), nullable=False),
        sa.Column("parser_contract_version", sa.String(length=40), nullable=False),
        sa.Column("column_mappings_text", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("total_row_count", sa.Integer(), nullable=False),
        sa.Column("accepted_row_count", sa.Integer(), nullable=False),
        sa.Column("rejected_row_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_row_count", sa.Integer(), nullable=False),
        sa.Column("conflict_row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("confirmed_by", sa.String(length=36), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("confirmed_at", sa.String(length=24), nullable=True),
        sa.CheckConstraint("state IN ('READY', 'INVALID', 'CONFIRMED', 'EXPIRED')", name="ck_upload_previews_state"),
        sa.CheckConstraint("total_row_count BETWEEN 0 AND 50000", name="ck_upload_previews_total_rows"),
        sa.CheckConstraint("accepted_row_count >= 0", name="ck_upload_previews_accepted_rows"),
        sa.CheckConstraint("rejected_row_count >= 0", name="ck_upload_previews_rejected_rows"),
        sa.CheckConstraint("duplicate_row_count >= 0", name="ck_upload_previews_duplicate_rows"),
        sa.CheckConstraint("conflict_row_count >= 0", name="ck_upload_previews_conflict_rows"),
        sa.CheckConstraint(
            "total_row_count = accepted_row_count + rejected_row_count + duplicate_row_count + conflict_row_count",
            name="ck_upload_previews_count_total",
        ),
        sa.CheckConstraint(
            "(state = 'CONFIRMED' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL) OR "
            "(state <> 'CONFIRMED' AND confirmed_by IS NULL AND confirmed_at IS NULL)",
            name="ck_upload_previews_confirmation",
        ),
        sa.UniqueConstraint("preview_idempotency_key", name="uq_upload_previews_idempotency_key"),
    )
    op.create_index("ix_upload_previews_upload_created", "upload_previews", ["upload_id", "created_at"])

    op.create_table(
        "upload_preview_rows",
        sa.Column("preview_id", sa.String(length=36), sa.ForeignKey("upload_previews.preview_id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("row_number", sa.Integer(), primary_key=True),
        sa.Column("row_status", sa.String(length=24), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=True),
        sa.Column("source_record_id", sa.String(length=256), nullable=True),
        sa.Column("normalized_row_text", sa.Text(), nullable=True),
        sa.Column("row_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("rejection_codes_text", sa.Text(), nullable=True),
        sa.Column("rejection_detail", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.CheckConstraint(
            "row_status IN ('ACCEPTED', 'REJECTED', 'DUPLICATE_NOOP', 'CONFLICT')",
            name="ck_upload_preview_rows_status",
        ),
        sa.CheckConstraint("row_number BETWEEN 1 AND 50000", name="ck_upload_preview_rows_number"),
        sa.CheckConstraint("source_type IS NULL OR source_type IN ('REVIEW', 'RETURN')", name="ck_upload_preview_rows_source_type"),
        sa.CheckConstraint(
            "(row_status IN ('ACCEPTED', 'DUPLICATE_NOOP', 'CONFLICT') AND normalized_row_text IS NOT NULL) OR "
            "(row_status = 'REJECTED' AND normalized_row_text IS NULL)",
            name="ck_upload_preview_rows_snapshot",
        ),
        sa.CheckConstraint(
            "row_status = 'REJECTED' OR source_type IS NULL OR source_record_id IS NOT NULL",
            name="ck_upload_preview_rows_source_identity",
        ),
    )
    op.create_index("ix_upload_preview_rows_status", "upload_preview_rows", ["preview_id", "row_status", "row_number"])


def downgrade() -> None:
    op.drop_index("ix_upload_preview_rows_status", table_name="upload_preview_rows")
    op.drop_table("upload_preview_rows")
    op.drop_index("ix_upload_previews_upload_created", table_name="upload_previews")
    op.drop_table("upload_previews")
    op.drop_index("ix_csv_uploads_uploaded_by_at", table_name="csv_uploads")
    op.drop_table("csv_uploads")
