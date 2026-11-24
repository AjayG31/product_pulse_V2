"""Add durable worker attempts and permit explicitly unbudgeted work."""

from alembic import op
import sqlalchemy as sa


revision = "pp018_worker_runtime_001"
down_revision = "pp014_confirmation_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("background_jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_background_jobs_attempt_count", type_="check")
        batch_op.drop_constraint("ck_background_jobs_max_attempts", type_="check")
        batch_op.alter_column(
            "max_attempts",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.create_check_constraint(
            "ck_background_jobs_attempt_count",
            "attempt_count >= 0 AND (max_attempts IS NULL OR attempt_count <= max_attempts)",
        )
        batch_op.create_check_constraint(
            "ck_background_jobs_max_attempts",
            "max_attempts IS NULL OR max_attempts > 0",
        )
        batch_op.create_check_constraint(
            "ck_background_jobs_approved_budget",
            "(job_type = 'BATCH_POLL' AND max_attempts IS NULL) OR "
            "(job_type IN ('INGESTION', 'CLASSIFICATION', 'DETECTION', 'RECONCILIATION') AND max_attempts = 3)",
        )

    op.create_table(
        "background_job_attempts",
        sa.Column("background_job_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("claimed_at", sa.String(length=24), nullable=False),
        sa.Column("finished_at", sa.String(length=24), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("safe_error_summary", sa.String(length=512), nullable=True),
        sa.Column("next_attempt_at", sa.String(length=24), nullable=True),
        sa.CheckConstraint("attempt_number > 0", name="ck_background_job_attempts_number"),
        sa.CheckConstraint(
            "outcome IN ('IN_PROGRESS', 'SUCCEEDED', 'RETRYABLE_FAILURE', 'TERMINAL_FAILURE', 'ABANDONED')",
            name="ck_background_job_attempts_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'IN_PROGRESS' AND finished_at IS NULL AND next_attempt_at IS NULL) OR "
            "(outcome <> 'IN_PROGRESS' AND finished_at IS NOT NULL)",
            name="ck_background_job_attempts_finished_state",
        ),
        sa.CheckConstraint(
            "(outcome = 'RETRYABLE_FAILURE' AND next_attempt_at IS NOT NULL) OR "
            "(outcome <> 'RETRYABLE_FAILURE' AND next_attempt_at IS NULL)",
            name="ck_background_job_attempts_next_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["background_job_id"],
            ["background_jobs.background_job_id"],
            name="fk_background_job_attempts_job",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("background_job_id", "attempt_number"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    unbudgeted_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM background_jobs WHERE max_attempts IS NULL")
    ).scalar_one()
    if unbudgeted_count:
        raise RuntimeError("Cannot downgrade while unbudgeted background jobs exist.")

    op.drop_table("background_job_attempts")
    with op.batch_alter_table("background_jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_background_jobs_attempt_count", type_="check")
        batch_op.drop_constraint("ck_background_jobs_max_attempts", type_="check")
        batch_op.drop_constraint("ck_background_jobs_approved_budget", type_="check")
        batch_op.alter_column(
            "max_attempts",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_background_jobs_attempt_count",
            "attempt_count >= 0 AND attempt_count <= max_attempts",
        )
        batch_op.create_check_constraint("ck_background_jobs_max_attempts", "max_attempts > 0")
