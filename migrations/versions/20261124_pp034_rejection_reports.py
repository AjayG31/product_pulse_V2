"""Add protected rejection-report artifact metadata."""

from alembic import op
import sqlalchemy as sa


revision = "pp034_rejection_reports_001"
down_revision = "pp018_worker_runtime_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rejection_report_artifacts",
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("preview_id", sa.String(length=36), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("generated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_rejection_report_artifacts_size"),
        sa.CheckConstraint("length(file_sha256) = 64", name="ck_rejection_report_artifacts_hash_length"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["preview_id"], ["upload_previews.preview_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("artifact_id"),
        sa.UniqueConstraint("preview_id", name="uq_rejection_report_artifacts_preview"),
    )
def downgrade() -> None:
    connection = op.get_bind()
    report_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM rejection_report_artifacts")
    ).scalar_one()
    if report_count:
        raise RuntimeError("Cannot downgrade while rejection report artifacts exist")
    op.drop_table("rejection_report_artifacts")
