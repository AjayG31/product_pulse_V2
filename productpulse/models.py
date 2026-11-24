from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'BUSINESS_USER')", name="ck_users_role"),
        CheckConstraint("status IN ('ACTIVE', 'DEACTIVATED')", name="ck_users_status"),
        CheckConstraint("must_change_password IN (0, 1)", name="ck_users_must_change_password"),
        CheckConstraint(
            "(status = 'ACTIVE' AND deactivated_at IS NULL) OR "
            "(status = 'DEACTIVATED' AND deactivated_at IS NOT NULL)",
            name="ck_users_deactivation_state",
        ),
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(24), nullable=False)
    deactivated_at: Mapped[str | None] = mapped_column(String(24))


class SessionRecord(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_live", "user_id", "expires_at", "revoked_at"),
    )

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(24), nullable=False)
    last_seen_at: Mapped[str | None] = mapped_column(String(24))
    revoked_at: Mapped[str | None] = mapped_column(String(24))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_resource", "resource_type", "resource_id", "created_at"),
        Index("ix_audit_events_actor", "actor_user_id", "created_at"),
    )

    audit_event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    before_state_text: Mapped[str | None] = mapped_column(Text)
    after_state_text: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)


class CsvUpload(Base):
    __tablename__ = "csv_uploads"
    __table_args__ = (
        CheckConstraint(
            "upload_kind IN ('REVIEWS', 'RETURNS', 'PRODUCT_REFERENCE', 'SUPPLIER_REFERENCE', 'BATCH_REFERENCE')",
            name="ck_csv_uploads_kind",
        ),
        CheckConstraint("file_size_bytes BETWEEN 1 AND 20000000", name="ck_csv_uploads_size"),
        CheckConstraint("length(file_sha256) = 64", name="ck_csv_uploads_hash_length"),
        UniqueConstraint("artifact_id", name="uq_csv_uploads_artifact_id"),
        Index("ix_csv_uploads_uploaded_by_at", "uploaded_by", "uploaded_at"),
    )

    upload_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    upload_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(36), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    uploaded_at: Mapped[str] = mapped_column(String(24), nullable=False)


class UploadPreview(Base):
    __tablename__ = "upload_previews"
    __table_args__ = (
        CheckConstraint(
            "state IN ('READY', 'INVALID', 'CONFIRMED', 'EXPIRED')",
            name="ck_upload_previews_state",
        ),
        CheckConstraint("total_row_count BETWEEN 0 AND 50000", name="ck_upload_previews_total_rows"),
        CheckConstraint("accepted_row_count >= 0", name="ck_upload_previews_accepted_rows"),
        CheckConstraint("rejected_row_count >= 0", name="ck_upload_previews_rejected_rows"),
        CheckConstraint("duplicate_row_count >= 0", name="ck_upload_previews_duplicate_rows"),
        CheckConstraint("conflict_row_count >= 0", name="ck_upload_previews_conflict_rows"),
        CheckConstraint(
            "total_row_count = accepted_row_count + rejected_row_count + duplicate_row_count + conflict_row_count",
            name="ck_upload_previews_count_total",
        ),
        CheckConstraint(
            "(state = 'CONFIRMED' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL) OR "
            "(state <> 'CONFIRMED' AND confirmed_by IS NULL AND confirmed_at IS NULL)",
            name="ck_upload_previews_confirmation",
        ),
        UniqueConstraint("preview_idempotency_key", name="uq_upload_previews_idempotency_key"),
        Index("ix_upload_previews_upload_created", "upload_id", "created_at"),
    )

    preview_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    preview_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    preview_request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_id: Mapped[str] = mapped_column(ForeignKey("csv_uploads.upload_id", ondelete="RESTRICT"), nullable=False)
    verified_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    column_mappings_text: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    total_row_count: Mapped[int] = mapped_column(nullable=False)
    accepted_row_count: Mapped[int] = mapped_column(nullable=False)
    rejected_row_count: Mapped[int] = mapped_column(nullable=False)
    duplicate_row_count: Mapped[int] = mapped_column(nullable=False)
    conflict_row_count: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    confirmed_at: Mapped[str | None] = mapped_column(String(24))


class UploadPreviewRow(Base):
    __tablename__ = "upload_preview_rows"
    __table_args__ = (
        CheckConstraint(
            "row_status IN ('ACCEPTED', 'REJECTED', 'DUPLICATE_NOOP', 'CONFLICT')",
            name="ck_upload_preview_rows_status",
        ),
        CheckConstraint("row_number BETWEEN 1 AND 50000", name="ck_upload_preview_rows_number"),
        CheckConstraint("source_type IS NULL OR source_type IN ('REVIEW', 'RETURN')", name="ck_upload_preview_rows_source_type"),
        CheckConstraint(
            "(row_status IN ('ACCEPTED', 'DUPLICATE_NOOP', 'CONFLICT') AND normalized_row_text IS NOT NULL) OR "
            "(row_status = 'REJECTED' AND normalized_row_text IS NULL)",
            name="ck_upload_preview_rows_snapshot",
        ),
        CheckConstraint(
            "row_status = 'REJECTED' OR source_type IS NULL OR source_record_id IS NOT NULL",
            name="ck_upload_preview_rows_source_identity",
        ),
        Index("ix_upload_preview_rows_status", "preview_id", "row_status", "row_number"),
    )

    preview_id: Mapped[str] = mapped_column(
        ForeignKey("upload_previews.preview_id", ondelete="RESTRICT"), primary_key=True
    )
    row_number: Mapped[int] = mapped_column(primary_key=True)
    row_status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(16))
    source_record_id: Mapped[str | None] = mapped_column(String(256))
    normalized_row_text: Mapped[str | None] = mapped_column(Text)
    row_payload_sha256: Mapped[str | None] = mapped_column(String(64))
    rejection_codes_text: Mapped[str | None] = mapped_column(Text)
    rejection_detail: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)


class RejectionReportArtifact(Base):
    __tablename__ = "rejection_report_artifacts"
    __table_args__ = (
        CheckConstraint("file_size_bytes >= 0", name="ck_rejection_report_artifacts_size"),
        CheckConstraint("length(file_sha256) = 64", name="ck_rejection_report_artifacts_hash_length"),
        UniqueConstraint("preview_id", name="uq_rejection_report_artifacts_preview"),
    )

    artifact_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    preview_id: Mapped[str] = mapped_column(ForeignKey("upload_previews.preview_id", ondelete="RESTRICT"), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    generated_by: Mapped[str | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(1024))
    category: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(24), nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(24), nullable=False)


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("batch_id", "product_id", "supplier_id", name="uq_batches_linkage"),
    )

    batch_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(24), nullable=False)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "processing_mode IS NULL OR processing_mode IN ('HISTORICAL_BATCH', 'INCREMENTAL_RESPONSES')",
            name="ck_ingestion_jobs_mode",
        ),
        CheckConstraint("status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')", name="ck_ingestion_jobs_status"),
        CheckConstraint("total_row_count >= 0", name="ck_ingestion_jobs_total_rows"),
        CheckConstraint("accepted_row_count >= 0", name="ck_ingestion_jobs_accepted_rows"),
        CheckConstraint("rejected_row_count >= 0", name="ck_ingestion_jobs_rejected_rows"),
        CheckConstraint("duplicate_row_count >= 0", name="ck_ingestion_jobs_duplicate_rows"),
        CheckConstraint("conflict_row_count >= 0", name="ck_ingestion_jobs_conflict_rows"),
        CheckConstraint("persisted_feedback_count >= 0", name="ck_ingestion_jobs_persisted_rows"),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'PARTIAL', 'FAILED') AND completed_at IS NOT NULL)",
            name="ck_ingestion_jobs_status_timestamps",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_ingestion_jobs_timestamp_order",
        ),
        UniqueConstraint("preview_id", name="uq_ingestion_jobs_preview_id"),
        UniqueConstraint("idempotency_key", name="uq_ingestion_jobs_idempotency_key"),
        UniqueConstraint("preview_id", "job_id", name="uq_ingestion_jobs_preview_job"),
        Index("ix_ingestion_jobs_status_created", "status", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    preview_id: Mapped[str] = mapped_column(ForeignKey("upload_previews.preview_id", ondelete="RESTRICT"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    processing_mode: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", server_default="QUEUED")
    total_row_count: Mapped[int] = mapped_column(nullable=False)
    accepted_row_count: Mapped[int] = mapped_column(nullable=False)
    rejected_row_count: Mapped[int] = mapped_column(nullable=False)
    duplicate_row_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    conflict_row_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    persisted_feedback_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(24))
    completed_at: Mapped[str | None] = mapped_column(String(24))
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class IngestionConflict(Base):
    __tablename__ = "ingestion_conflicts"
    __table_args__ = (
        CheckConstraint("conflict_kind IN ('SOURCE_PAYLOAD', 'REFERENCE_MAPPING')", name="ck_ingestion_conflicts_kind"),
        CheckConstraint("state IN ('PENDING', 'RESOLVED', 'DISMISSED')", name="ck_ingestion_conflicts_state"),
        CheckConstraint(
            "(state = 'PENDING' AND resolved_by IS NULL AND resolved_at IS NULL) OR "
            "(state IN ('RESOLVED', 'DISMISSED') AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_ingestion_conflicts_resolution",
        ),
        CheckConstraint("resolved_at IS NULL OR resolved_at >= created_at", name="ck_ingestion_conflicts_timestamp_order"),
        ForeignKeyConstraint(
            ["preview_id", "row_number"],
            ["upload_preview_rows.preview_id", "upload_preview_rows.row_number"],
            name="fk_ingestion_conflicts_preview_row",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("preview_id", "row_number", "conflict_kind", name="uq_ingestion_conflicts_preview_row_kind"),
        Index("ix_ingestion_conflicts_state_created", "state", "created_at"),
    )

    conflict_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    preview_id: Mapped[str] = mapped_column(ForeignKey("upload_previews.preview_id", ondelete="RESTRICT"), nullable=False)
    row_number: Mapped[int] = mapped_column(nullable=False)
    conflict_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    existing_feedback_id: Mapped[str | None] = mapped_column(ForeignKey("feedback.feedback_id", ondelete="RESTRICT"))
    source_type: Mapped[str | None] = mapped_column(String(16))
    source_record_id: Mapped[str | None] = mapped_column(String(256))
    existing_value_hash: Mapped[str | None] = mapped_column(String(64))
    incoming_value_hash: Mapped[str | None] = mapped_column(String(64))
    mapping_key: Mapped[str | None] = mapped_column(String(512))
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", server_default="PENDING")
    resolution_note: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    resolved_at: Mapped[str | None] = mapped_column(String(24))


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('INGESTION', 'CLASSIFICATION', 'BATCH_POLL', 'DETECTION', 'RECONCILIATION')",
            name="ck_background_jobs_type",
        ),
        CheckConstraint(
            "(job_type = 'DETECTION' AND taxonomy_version_id IS NOT NULL) OR "
            "(job_type <> 'DETECTION' AND taxonomy_version_id IS NULL)",
            name="ck_background_jobs_taxonomy_version",
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRY_WAIT', 'COMPLETED', 'PARTIAL', 'FAILED')",
            name="ck_background_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND (max_attempts IS NULL OR attempt_count <= max_attempts)",
            name="ck_background_jobs_attempt_count",
        ),
        CheckConstraint("max_attempts IS NULL OR max_attempts > 0", name="ck_background_jobs_max_attempts"),
        CheckConstraint(
            "(job_type = 'BATCH_POLL' AND max_attempts IS NULL) OR "
            "(job_type IN ('INGESTION', 'CLASSIFICATION', 'DETECTION', 'RECONCILIATION') AND max_attempts = 3)",
            name="ck_background_jobs_approved_budget",
        ),
        CheckConstraint(
            "((status IN ('QUEUED', 'RETRY_WAIT')) AND completed_at IS NULL AND worker_id IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL AND worker_id IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status IN ('COMPLETED', 'PARTIAL', 'FAILED') AND completed_at IS NOT NULL AND worker_id IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_background_jobs_status_timestamps",
        ),
        CheckConstraint("next_attempt_at IS NULL OR status = 'RETRY_WAIT'", name="ck_background_jobs_next_attempt_state"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_background_jobs_timestamp_order",
        ),
        UniqueConstraint("work_key", name="uq_background_jobs_work_key"),
        UniqueConstraint("background_job_id", "taxonomy_version_id", name="uq_background_jobs_id_taxonomy"),
        Index("ix_background_jobs_status_schedule", "status", "next_attempt_at", "scheduled_at"),
        Index(
            "ix_background_jobs_lease_expires",
            "lease_expires_at",
            sqlite_where=text("lease_expires_at IS NOT NULL"),
        ),
        Index(
            "uq_background_jobs_provider_input",
            "provider_input_file_id",
            unique=True,
            sqlite_where=text("provider_input_file_id IS NOT NULL"),
        ),
    )

    background_job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    taxonomy_version_id: Mapped[str | None] = mapped_column(ForeignKey("taxonomy_versions.taxonomy_version_id", ondelete="RESTRICT"))
    work_key: Mapped[str] = mapped_column(String(256), nullable=False)
    ingestion_job_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_jobs.job_id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", server_default="QUEUED")
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int | None] = mapped_column(nullable=True)
    scheduled_at: Mapped[str] = mapped_column(String(24), nullable=False)
    next_attempt_at: Mapped[str | None] = mapped_column(String(24))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[str | None] = mapped_column(String(24))
    provider_input_file_id: Mapped[str | None] = mapped_column(String(256))
    provider_batch_id: Mapped[str | None] = mapped_column(String(256))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(24))
    completed_at: Mapped[str | None] = mapped_column(String(24))


class BackgroundJobAttempt(Base):
    __tablename__ = "background_job_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="ck_background_job_attempts_number"),
        CheckConstraint(
            "outcome IN ('IN_PROGRESS', 'SUCCEEDED', 'RETRYABLE_FAILURE', 'TERMINAL_FAILURE', 'ABANDONED')",
            name="ck_background_job_attempts_outcome",
        ),
        CheckConstraint(
            "(outcome = 'IN_PROGRESS' AND finished_at IS NULL AND next_attempt_at IS NULL) OR "
            "(outcome <> 'IN_PROGRESS' AND finished_at IS NOT NULL)",
            name="ck_background_job_attempts_finished_state",
        ),
        CheckConstraint(
            "(outcome = 'RETRYABLE_FAILURE' AND next_attempt_at IS NOT NULL) OR "
            "(outcome <> 'RETRYABLE_FAILURE' AND next_attempt_at IS NULL)",
            name="ck_background_job_attempts_next_attempt",
        ),
        ForeignKeyConstraint(
            ["background_job_id"],
            ["background_jobs.background_job_id"],
            name="fk_background_job_attempts_job",
            ondelete="RESTRICT",
        ),
    )

    background_job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_number: Mapped[int] = mapped_column(primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    claimed_at: Mapped[str] = mapped_column(String(24), nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String(24))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    safe_error_summary: Mapped[str | None] = mapped_column(String(512))
    next_attempt_at: Mapped[str | None] = mapped_column(String(24))


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("source_type IN ('REVIEW', 'RETURN')", name="ck_feedback_source_type"),
        CheckConstraint("linkage_status IN ('LINKED', 'LINKAGE_PENDING')", name="ck_feedback_linkage_status"),
        CheckConstraint("(linkage_status <> 'LINKED') OR (supplier_id IS NOT NULL AND batch_id IS NOT NULL)", name="ck_feedback_linked_values"),
        CheckConstraint("batch_id IS NULL OR supplier_id IS NOT NULL", name="ck_feedback_batch_supplier"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
        CheckConstraint("return_quantity IS NULL OR return_quantity > 0", name="ck_feedback_return_quantity"),
        CheckConstraint(
            "(source_type = 'REVIEW' AND return_quantity IS NULL AND return_category IS NULL) OR "
            "(source_type = 'RETURN' AND rating IS NULL AND source_label IS NULL)",
            name="ck_feedback_source_fields",
        ),
        CheckConstraint(
            "(record_origin = 'CSV_UPLOAD' AND ingestion_job_id IS NOT NULL AND origin_preview_id IS NOT NULL "
            "AND origin_row_number IS NOT NULL AND origin_manifest_ref IS NULL) OR "
            "(record_origin = 'SYNTHETIC_SEED' AND ingestion_job_id IS NULL AND origin_preview_id IS NULL "
            "AND origin_row_number IS NULL AND origin_manifest_ref IS NOT NULL)",
            name="ck_feedback_origin_lineage",
        ),
        UniqueConstraint("source_type", "source_record_id", name="uq_feedback_source_identity"),
        UniqueConstraint("origin_preview_id", "origin_row_number", name="uq_feedback_origin_row"),
        ForeignKeyConstraint(
            ["origin_preview_id", "ingestion_job_id"],
            ["ingestion_jobs.preview_id", "ingestion_jobs.job_id"],
            name="fk_feedback_origin_job_preview",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["origin_preview_id", "origin_row_number"],
            ["upload_preview_rows.preview_id", "upload_preview_rows.row_number"],
            name="fk_feedback_origin_preview_row",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["batch_id", "product_id", "supplier_id"],
            ["batches.batch_id", "batches.product_id", "batches.supplier_id"],
            name="fk_feedback_batch_linkage",
            ondelete="RESTRICT",
        ),
        Index("ix_feedback_event_time", "event_time_utc"),
        Index("ix_feedback_product_event_time", "product_id", "event_time_utc"),
        Index("ix_feedback_ingestion_job", "ingestion_job_id"),
    )

    feedback_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"))
    batch_id: Mapped[str | None] = mapped_column(String(256))
    reported_supplier_id: Mapped[str | None] = mapped_column(String(256))
    reported_batch_id: Mapped[str | None] = mapped_column(String(256))
    linkage_status: Mapped[str] = mapped_column(String(24), nullable=False)
    event_time_utc: Mapped[str] = mapped_column(String(24), nullable=False)
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int | None] = mapped_column()
    source_label: Mapped[str | None] = mapped_column(String(1024))
    return_quantity: Mapped[int | None] = mapped_column()
    return_category: Mapped[str | None] = mapped_column(String(1024))
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record_origin: Mapped[str] = mapped_column(String(24), nullable=False)
    ingestion_job_id: Mapped[str | None] = mapped_column(String(36))
    origin_preview_id: Mapped[str | None] = mapped_column(ForeignKey("upload_previews.preview_id", ondelete="RESTRICT"))
    origin_row_number: Mapped[int | None] = mapped_column()
    origin_manifest_ref: Mapped[str | None] = mapped_column(String(512))
    ingested_at: Mapped[str] = mapped_column(String(24), nullable=False)


class FeedbackLinkageEvent(Base):
    __tablename__ = "feedback_linkage_events"
    __table_args__ = (
        CheckConstraint("previous_status IN ('LINKED', 'LINKAGE_PENDING')", name="ck_linkage_events_previous_status"),
        CheckConstraint("new_status IN ('LINKED', 'LINKAGE_PENDING')", name="ck_linkage_events_new_status"),
        CheckConstraint(
            "resolution_method IN ('SOURCE_VALUE', 'REFERENCE_MAPPING', 'ADMIN_RECONCILIATION')",
            name="ck_linkage_events_method",
        ),
        CheckConstraint(
            "(new_status = 'LINKED' AND new_supplier_id IS NOT NULL AND new_batch_id IS NOT NULL) OR "
            "(new_status = 'LINKAGE_PENDING' AND new_batch_id IS NULL)",
            name="ck_linkage_events_new_values",
        ),
        Index("ix_feedback_linkage_events_feedback_created", "feedback_id", "created_at"),
    )

    linkage_event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback.feedback_id", ondelete="RESTRICT"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    ingestion_job_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_jobs.job_id", ondelete="RESTRICT"))
    previous_supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"))
    previous_batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.batch_id", ondelete="RESTRICT"))
    new_supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"))
    new_batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.batch_id", ondelete="RESTRICT"))
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    resolution_method: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    recompute_job_id: Mapped[str | None] = mapped_column(ForeignKey("background_jobs.background_job_id", ondelete="RESTRICT"))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)


class TaxonomyVersion(Base):
    __tablename__ = "taxonomy_versions"
    __table_args__ = (
        CheckConstraint("state IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_taxonomy_versions_state"),
        CheckConstraint(
            "(state = 'DRAFT' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(state = 'ACTIVE' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(state = 'RETIRED' AND activated_at IS NOT NULL AND retired_at IS NOT NULL AND retired_at >= activated_at)",
            name="ck_taxonomy_versions_lifecycle",
        ),
        UniqueConstraint("version_label", name="uq_taxonomy_versions_label"),
        Index("uq_taxonomy_versions_one_active", "state", unique=True, sqlite_where=text("state = 'ACTIVE'")),
    )

    taxonomy_version_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_label: Mapped[str] = mapped_column(String(256), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    activated_at: Mapped[str | None] = mapped_column(String(24))
    retired_at: Mapped[str | None] = mapped_column(String(24))


class TaxonomyCategory(Base):
    __tablename__ = "taxonomy_categories"
    __table_args__ = (
        CheckConstraint("category_kind IN ('DEFECT', 'NO_DEFECT', 'UNCERTAIN')", name="ck_taxonomy_categories_kind"),
    )

    taxonomy_version_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_versions.taxonomy_version_id", ondelete="RESTRICT"), primary_key=True)
    category_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category_kind: Mapped[str] = mapped_column(String(16), nullable=False)


class LogicalDefect(Base):
    __tablename__ = "logical_defects"

    logical_defect_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    meaning_description: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)


class TaxonomyIssueCode(Base):
    __tablename__ = "taxonomy_issue_codes"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version_id", "category_code", "specific_issue_code", "logical_defect_id",
            name="uq_taxonomy_issue_logical_defect",
        ),
        ForeignKeyConstraint(
            ["taxonomy_version_id", "category_code"],
            ["taxonomy_categories.taxonomy_version_id", "taxonomy_categories.category_code"],
            name="fk_taxonomy_issue_category", ondelete="RESTRICT",
        ),
        CheckConstraint("active IN (0, 1)", name="ck_taxonomy_issue_active"),
    )

    taxonomy_version_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    category_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    specific_issue_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    logical_defect_id: Mapped[str] = mapped_column(ForeignKey("logical_defects.logical_defect_id", ondelete="RESTRICT"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="ck_classifications_attempt_number"),
        CheckConstraint("api_path IN ('RESPONSES', 'BATCH')", name="ck_classifications_api_path"),
        CheckConstraint(
            "status IN ('QUEUED', 'IN_PROGRESS', 'COMPLETED', 'RETRYABLE_FAILED', 'TERMINAL_FAILED', 'NEEDS_REVIEW')",
            name="ck_classifications_status",
        ),
        CheckConstraint("has_defect IS NULL OR has_defect IN (0, 1)", name="ck_classifications_has_defect"),
        CheckConstraint("needs_review IS NULL OR needs_review IN (0, 1)", name="ck_classifications_needs_review"),
        CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'RETRYABLE_FAILED', 'TERMINAL_FAILED', 'NEEDS_REVIEW') AND completed_at IS NOT NULL)",
            name="ck_classifications_status_times",
        ),
        CheckConstraint(
            "status <> 'COMPLETED' OR (has_defect IS NOT NULL AND needs_review = 0)",
            name="ck_classifications_completed_definitive",
        ),
        CheckConstraint("completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at", name="ck_classifications_time_order"),
        UniqueConstraint("feedback_id", "attempt_number", name="uq_classifications_feedback_attempt"),
        UniqueConstraint("classification_id", "taxonomy_version_id", name="uq_classifications_id_taxonomy"),
        Index("ix_classifications_feedback_completed", "feedback_id", "taxonomy_version_id", "status", "completed_at"),
    )

    classification_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback.feedback_id", ondelete="RESTRICT"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    background_job_id: Mapped[str] = mapped_column(ForeignKey("background_jobs.background_job_id", ondelete="RESTRICT"), nullable=False)
    taxonomy_version_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_versions.taxonomy_version_id", ondelete="RESTRICT"), nullable=False)
    api_path: Mapped[str] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    has_defect: Mapped[bool | None] = mapped_column(Boolean)
    needs_review: Mapped[bool | None] = mapped_column(Boolean)
    severity_hint: Mapped[str | None] = mapped_column(String(32))
    evidence_excerpt: Mapped[str | None] = mapped_column(String(2000))
    provider_request_id: Mapped[str | None] = mapped_column(String(256))
    input_tokens: Mapped[int | None] = mapped_column()
    output_tokens: Mapped[int | None] = mapped_column()
    estimated_cost_micro_usd: Mapped[int | None] = mapped_column()
    latency_ms: Mapped[int | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(24))
    completed_at: Mapped[str | None] = mapped_column(String(24))


class ClassificationLabel(Base):
    __tablename__ = "classification_labels"
    __table_args__ = (
        CheckConstraint("label_role IN ('PRIMARY', 'SECONDARY')", name="ck_classification_labels_role"),
        CheckConstraint("(specific_issue_code IS NULL AND logical_defect_id IS NULL) OR (specific_issue_code IS NOT NULL AND logical_defect_id IS NOT NULL)", name="ck_classification_labels_issue_pair"),
        CheckConstraint("(label_role = 'PRIMARY' AND label_order = 0) OR (label_role = 'SECONDARY' AND label_order = 1)", name="ck_classification_labels_order"),
        ForeignKeyConstraint(
            ["classification_id", "taxonomy_version_id"],
            ["classifications.classification_id", "classifications.taxonomy_version_id"],
            name="fk_classification_labels_parent_version", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["taxonomy_version_id", "category_code"],
            ["taxonomy_categories.taxonomy_version_id", "taxonomy_categories.category_code"],
            name="fk_classification_labels_category", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["taxonomy_version_id", "category_code", "specific_issue_code", "logical_defect_id"],
            ["taxonomy_issue_codes.taxonomy_version_id", "taxonomy_issue_codes.category_code", "taxonomy_issue_codes.specific_issue_code", "taxonomy_issue_codes.logical_defect_id"],
            name="fk_classification_labels_issue", ondelete="RESTRICT",
        ),
        UniqueConstraint("classification_id", "label_order", name="uq_classification_labels_order"),
        UniqueConstraint("classification_id", "taxonomy_version_id", "label_role", "logical_defect_id", name="uq_classification_labels_defect"),
        Index("uq_classification_labels_issue", "classification_id", "specific_issue_code", unique=True, sqlite_where=text("specific_issue_code IS NOT NULL")),
    )

    classification_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    label_role: Mapped[str] = mapped_column(String(16), primary_key=True)
    taxonomy_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category_code: Mapped[str] = mapped_column(String(64), nullable=False)
    specific_issue_code: Mapped[str | None] = mapped_column(String(64))
    logical_defect_id: Mapped[str | None] = mapped_column(ForeignKey("logical_defects.logical_defect_id", ondelete="RESTRICT"))
    label_order: Mapped[int] = mapped_column(nullable=False)


class DetectionRuleVersion(Base):
    __tablename__ = "detection_rule_versions"
    __table_args__ = (
        CheckConstraint("state IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_detection_rule_versions_state"),
        CheckConstraint(
            "(state = 'DRAFT' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(state = 'ACTIVE' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(state = 'RETIRED' AND activated_at IS NOT NULL AND retired_at IS NOT NULL AND retired_at >= activated_at)",
            name="ck_detection_rule_versions_lifecycle",
        ),
        UniqueConstraint("rule_version", "taxonomy_version_id", name="uq_detection_rules_version_taxonomy"),
        Index("uq_detection_rules_one_active", "state", unique=True, sqlite_where=text("state = 'ACTIVE'")),
    )

    rule_version: Mapped[str] = mapped_column(String(128), primary_key=True)
    taxonomy_version_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_versions.taxonomy_version_id", ondelete="RESTRICT"), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    config_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)
    activated_at: Mapped[str | None] = mapped_column(String(24))
    retired_at: Mapped[str | None] = mapped_column(String(24))


class DefectCluster(Base):
    __tablename__ = "defect_clusters"
    __table_args__ = (
        UniqueConstraint("product_id", "supplier_id", "batch_id", "logical_defect_id", name="uq_defect_clusters_context"),
        UniqueConstraint("cluster_id", "logical_defect_id", name="uq_defect_clusters_id_defect"),
        ForeignKeyConstraint(
            ["batch_id", "product_id", "supplier_id"],
            ["batches.batch_id", "batches.product_id", "batches.supplier_id"],
            name="fk_defect_clusters_batch_linkage", ondelete="RESTRICT",
        ),
    )

    cluster_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(256), nullable=False)
    logical_defect_id: Mapped[str] = mapped_column(ForeignKey("logical_defects.logical_defect_id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)


class DetectionResult(Base):
    __tablename__ = "detection_results"
    __table_args__ = (
        CheckConstraint("evaluation_mode IN ('CURRENT_MONITORING', 'HISTORICAL_RECOMPUTE')", name="ck_detection_results_mode"),
        CheckConstraint("coverage_state IN ('SUFFICIENT_NONZERO', 'SUFFICIENT_ZERO', 'INSUFFICIENT')", name="ck_detection_results_coverage"),
        CheckConstraint("baseline_source_coverage_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')", name="ck_detection_results_source_coverage"),
        CheckConstraint("observed_classification_coverage_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')", name="ck_detection_results_observed_coverage"),
        CheckConstraint("baseline_classification_coverage_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')", name="ck_detection_results_baseline_coverage"),
        CheckConstraint("decision_state IN ('NO_TRIGGER', 'TRIGGERED', 'INSUFFICIENT_COVERAGE')", name="ck_detection_results_decision"),
        CheckConstraint("incident_application_state IN ('NOT_APPLICABLE', 'PENDING', 'APPLIED', 'SUPERSEDED')", name="ck_detection_results_incident_state"),
        CheckConstraint(
            "observed_count >= 0 AND baseline_28d_count >= 0 AND "
            "observed_classification_assessed_count >= 0 AND observed_classification_complete_count >= 0 AND "
            "baseline_classification_assessed_count >= 0 AND baseline_classification_complete_count >= 0 AND "
            "observed_classification_complete_count <= observed_classification_assessed_count AND "
            "baseline_classification_complete_count <= baseline_classification_assessed_count",
            name="ck_detection_results_counts",
        ),
        CheckConstraint("observed_end_utc > observed_start_utc AND baseline_end_utc > baseline_start_utc", name="ck_detection_results_windows"),
        CheckConstraint(
            "(evaluation_mode <> 'HISTORICAL_RECOMPUTE' OR incident_application_state = 'NOT_APPLICABLE') AND "
            "(decision_state <> 'INSUFFICIENT_COVERAGE' OR (coverage_state = 'INSUFFICIENT' AND severity IS NULL AND observed_to_baseline_ratio IS NULL AND incident_application_state = 'NOT_APPLICABLE'))",
            name="ck_detection_results_fail_closed",
        ),
        UniqueConstraint("result_key", name="uq_detection_results_result_key"),
        UniqueConstraint("detection_result_id", "cluster_id", "taxonomy_version_id", name="uq_detection_results_context"),
        ForeignKeyConstraint(
            ["rule_version", "taxonomy_version_id"],
            ["detection_rule_versions.rule_version", "detection_rule_versions.taxonomy_version_id"],
            name="fk_detection_results_rule_version", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["background_job_id", "taxonomy_version_id"],
            ["background_jobs.background_job_id", "background_jobs.taxonomy_version_id"],
            name="fk_detection_results_job_version", ondelete="RESTRICT",
        ),
        Index("ix_detection_results_cluster_evaluated", "cluster_id", "evaluated_at"),
        Index("ix_detection_results_job", "background_job_id"),
    )

    detection_result_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result_key: Mapped[str] = mapped_column(String(64), nullable=False)
    result_input_snapshot_text: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("defect_clusters.cluster_id", ondelete="RESTRICT"), nullable=False)
    taxonomy_version_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_versions.taxonomy_version_id", ondelete="RESTRICT"), nullable=False)
    background_job_id: Mapped[str | None] = mapped_column(String(36))
    rule_version: Mapped[str] = mapped_column(String(128), nullable=False)
    coverage_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluation_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_at: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_start_utc: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_end_utc: Mapped[str] = mapped_column(String(24), nullable=False)
    baseline_start_utc: Mapped[str] = mapped_column(String(24), nullable=False)
    baseline_end_utc: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_count: Mapped[int] = mapped_column(nullable=False)
    baseline_28d_count: Mapped[int] = mapped_column(nullable=False)
    normalized_baseline_7d: Mapped[float | None] = mapped_column()
    observed_to_baseline_ratio: Mapped[float | None] = mapped_column()
    coverage_state: Mapped[str] = mapped_column(String(24), nullable=False)
    baseline_source_coverage_state: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_classification_coverage_state: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_classification_assessed_count: Mapped[int] = mapped_column(nullable=False)
    observed_classification_complete_count: Mapped[int] = mapped_column(nullable=False)
    baseline_classification_coverage_state: Mapped[str] = mapped_column(String(16), nullable=False)
    baseline_classification_assessed_count: Mapped[int] = mapped_column(nullable=False)
    baseline_classification_complete_count: Mapped[int] = mapped_column(nullable=False)
    decision_state: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(16))
    incident_application_state: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[str] = mapped_column(String(24), nullable=False)

