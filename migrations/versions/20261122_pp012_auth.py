"""Create the PP-012 identity, session, and audit tables."""

from alembic import op
import sqlalchemy as sa


revision = "pp012_auth_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("updated_at", sa.String(length=24), nullable=False),
        sa.Column("deactivated_at", sa.String(length=24), nullable=True),
        sa.CheckConstraint("role IN ('ADMIN', 'BUSINESS_USER')", name="ck_users_role"),
        sa.CheckConstraint("status IN ('ACTIVE', 'DEACTIVATED')", name="ck_users_status"),
        sa.CheckConstraint("must_change_password IN (0, 1)", name="ck_users_must_change_password"),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND deactivated_at IS NULL) OR "
            "(status = 'DEACTIVATED' AND deactivated_at IS NOT NULL)",
            name="ck_users_deactivation_state",
        ),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
    )
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.String(length=24), nullable=False),
        sa.Column("last_seen_at", sa.String(length=24), nullable=True),
        sa.Column("revoked_at", sa.String(length=24), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_live", "sessions", ["user_id", "expires_at", "revoked_at"])
    op.create_table(
        "audit_events",
        sa.Column("audit_event_id", sa.String(length=36), primary_key=True),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("before_state_text", sa.Text(), nullable=True),
        sa.Column("after_state_text", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.String(length=24), nullable=False),
    )
    op.create_index("ix_audit_events_resource", "audit_events", ["resource_type", "resource_id", "created_at"])
    op.create_index("ix_audit_events_actor", "audit_events", ["actor_user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_actor", table_name="audit_events")
    op.drop_index("ix_audit_events_resource", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_sessions_user_live", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")

