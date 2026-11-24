"""Add reference conflicts, linkage history, and versioned aggregate contracts."""

from alembic import op
import sqlalchemy as sa


revision = "pp015_reconciliation_001"
down_revision = "pp034_rejection_reports_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    unversioned_detection_jobs = connection.execute(
        sa.text("SELECT COUNT(*) FROM background_jobs WHERE job_type = 'DETECTION'")
    ).scalar_one()
    if unversioned_detection_jobs:
        raise RuntimeError("Cannot add explicit taxonomy contexts while unversioned DETECTION jobs exist")

    op.create_table(
        "taxonomy_versions",
        sa.Column("taxonomy_version_id", sa.String(128), nullable=False),
        sa.Column("version_label", sa.String(256), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.Column("activated_at", sa.String(24)),
        sa.Column("retired_at", sa.String(24)),
        sa.CheckConstraint("state IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_taxonomy_versions_state"),
        sa.CheckConstraint(
            "(state = 'DRAFT' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(state = 'ACTIVE' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(state = 'RETIRED' AND activated_at IS NOT NULL AND retired_at IS NOT NULL AND retired_at >= activated_at)",
            name="ck_taxonomy_versions_lifecycle",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("taxonomy_version_id"),
        sa.UniqueConstraint("version_label", name="uq_taxonomy_versions_label"),
    )
    op.create_index(
        "uq_taxonomy_versions_one_active", "taxonomy_versions", ["state"], unique=True,
        sqlite_where=sa.text("state = 'ACTIVE'"),
    )

    # SQLite permits adding a nullable FK column without rebuilding worker state.
    connection.exec_driver_sql(
        "ALTER TABLE background_jobs ADD COLUMN taxonomy_version_id VARCHAR(128) "
        "REFERENCES taxonomy_versions(taxonomy_version_id) ON DELETE RESTRICT"
    )
    op.create_index(
        "uq_background_jobs_id_taxonomy", "background_jobs",
        ["background_job_id", "taxonomy_version_id"], unique=True,
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER trg_background_jobs_taxonomy_insert "
        "BEFORE INSERT ON background_jobs "
        "WHEN (NEW.job_type = 'DETECTION' AND NEW.taxonomy_version_id IS NULL) "
        "OR (NEW.job_type <> 'DETECTION' AND NEW.taxonomy_version_id IS NOT NULL) "
        "BEGIN SELECT RAISE(ABORT, 'ck_background_jobs_taxonomy_version'); END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER trg_background_jobs_taxonomy_update "
        "BEFORE UPDATE OF job_type, taxonomy_version_id ON background_jobs "
        "WHEN (NEW.job_type = 'DETECTION' AND NEW.taxonomy_version_id IS NULL) "
        "OR (NEW.job_type <> 'DETECTION' AND NEW.taxonomy_version_id IS NOT NULL) "
        "OR (OLD.taxonomy_version_id IS NOT NEW.taxonomy_version_id) "
        "BEGIN SELECT RAISE(ABORT, 'ck_background_jobs_taxonomy_version_immutable'); END"
    )

    op.create_table(
        "ingestion_conflicts",
        sa.Column("conflict_id", sa.String(36), nullable=False),
        sa.Column("preview_id", sa.String(36), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("conflict_kind", sa.String(32), nullable=False),
        sa.Column("existing_feedback_id", sa.String(36)),
        sa.Column("source_type", sa.String(16)),
        sa.Column("source_record_id", sa.String(256)),
        sa.Column("existing_value_hash", sa.String(64)),
        sa.Column("incoming_value_hash", sa.String(64)),
        sa.Column("mapping_key", sa.String(512)),
        sa.Column("state", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("resolution_note", sa.String(2000)),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.Column("resolved_by", sa.String(36)),
        sa.Column("resolved_at", sa.String(24)),
        sa.CheckConstraint("conflict_kind IN ('SOURCE_PAYLOAD', 'REFERENCE_MAPPING')", name="ck_ingestion_conflicts_kind"),
        sa.CheckConstraint("state IN ('PENDING', 'RESOLVED', 'DISMISSED')", name="ck_ingestion_conflicts_state"),
        sa.CheckConstraint(
            "(state = 'PENDING' AND resolved_by IS NULL AND resolved_at IS NULL) OR "
            "(state IN ('RESOLVED', 'DISMISSED') AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_ingestion_conflicts_resolution",
        ),
        sa.CheckConstraint("resolved_at IS NULL OR resolved_at >= created_at", name="ck_ingestion_conflicts_timestamp_order"),
        sa.ForeignKeyConstraint(["preview_id", "row_number"], ["upload_preview_rows.preview_id", "upload_preview_rows.row_number"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["existing_feedback_id"], ["feedback.feedback_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("conflict_id"),
        sa.UniqueConstraint("preview_id", "row_number", "conflict_kind", name="uq_ingestion_conflicts_preview_row_kind"),
    )
    op.create_index("ix_ingestion_conflicts_state_created", "ingestion_conflicts", ["state", "created_at"])

    op.create_table(
        "taxonomy_categories",
        sa.Column("taxonomy_version_id", sa.String(128), nullable=False),
        sa.Column("category_code", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("category_kind", sa.String(16), nullable=False),
        sa.CheckConstraint("category_kind IN ('DEFECT', 'NO_DEFECT', 'UNCERTAIN')", name="ck_taxonomy_categories_kind"),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_versions.taxonomy_version_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("taxonomy_version_id", "category_code"),
    )
    op.create_table(
        "logical_defects",
        sa.Column("logical_defect_id", sa.String(128), nullable=False),
        sa.Column("meaning_description", sa.String(1000), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("logical_defect_id"),
    )
    op.create_table(
        "taxonomy_issue_codes",
        sa.Column("taxonomy_version_id", sa.String(128), nullable=False),
        sa.Column("category_code", sa.String(64), nullable=False),
        sa.Column("specific_issue_code", sa.String(64), nullable=False),
        sa.Column("logical_defect_id", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("active IN (0, 1)", name="ck_taxonomy_issue_active"),
        sa.ForeignKeyConstraint(["taxonomy_version_id", "category_code"], ["taxonomy_categories.taxonomy_version_id", "taxonomy_categories.category_code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["logical_defect_id"], ["logical_defects.logical_defect_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("taxonomy_version_id", "category_code", "specific_issue_code"),
        sa.UniqueConstraint("taxonomy_version_id", "category_code", "specific_issue_code", "logical_defect_id", name="uq_taxonomy_issue_logical_defect"),
    )

    op.create_table(
        "feedback_linkage_events",
        sa.Column("linkage_event_id", sa.String(36), nullable=False),
        sa.Column("feedback_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36)),
        sa.Column("ingestion_job_id", sa.String(36)),
        sa.Column("previous_supplier_id", sa.String(256)),
        sa.Column("previous_batch_id", sa.String(256)),
        sa.Column("new_supplier_id", sa.String(256)),
        sa.Column("new_batch_id", sa.String(256)),
        sa.Column("previous_status", sa.String(24), nullable=False),
        sa.Column("new_status", sa.String(24), nullable=False),
        sa.Column("resolution_method", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(1000)),
        sa.Column("recompute_job_id", sa.String(36)),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.CheckConstraint("previous_status IN ('LINKED', 'LINKAGE_PENDING')", name="ck_linkage_events_previous_status"),
        sa.CheckConstraint("new_status IN ('LINKED', 'LINKAGE_PENDING')", name="ck_linkage_events_new_status"),
        sa.CheckConstraint("resolution_method IN ('SOURCE_VALUE', 'REFERENCE_MAPPING', 'ADMIN_RECONCILIATION')", name="ck_linkage_events_method"),
        sa.CheckConstraint(
            "(new_status = 'LINKED' AND new_supplier_id IS NOT NULL AND new_batch_id IS NOT NULL) OR "
            "(new_status = 'LINKAGE_PENDING' AND new_batch_id IS NULL)", name="ck_linkage_events_new_values",
        ),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.feedback_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ingestion_job_id"], ["ingestion_jobs.job_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_supplier_id"], ["suppliers.supplier_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_batch_id"], ["batches.batch_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["new_supplier_id"], ["suppliers.supplier_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["new_batch_id"], ["batches.batch_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recompute_job_id"], ["background_jobs.background_job_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("linkage_event_id"),
    )
    op.create_index("ix_feedback_linkage_events_feedback_created", "feedback_linkage_events", ["feedback_id", "created_at"])

    op.create_table(
        "classifications",
        sa.Column("classification_id", sa.String(36), nullable=False),
        sa.Column("feedback_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("background_job_id", sa.String(36), nullable=False),
        sa.Column("taxonomy_version_id", sa.String(128), nullable=False),
        sa.Column("api_path", sa.String(16), nullable=False),
        sa.Column("model_id", sa.String(128)),
        sa.Column("prompt_version", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("has_defect", sa.Boolean()),
        sa.Column("needs_review", sa.Boolean()),
        sa.Column("severity_hint", sa.String(32)),
        sa.Column("evidence_excerpt", sa.String(2000)),
        sa.Column("provider_request_id", sa.String(256)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("estimated_cost_micro_usd", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.Column("started_at", sa.String(24)),
        sa.Column("completed_at", sa.String(24)),
        sa.CheckConstraint("attempt_number > 0", name="ck_classifications_attempt_number"),
        sa.CheckConstraint("api_path IN ('RESPONSES', 'BATCH')", name="ck_classifications_api_path"),
        sa.CheckConstraint("status IN ('QUEUED', 'IN_PROGRESS', 'COMPLETED', 'RETRYABLE_FAILED', 'TERMINAL_FAILED', 'NEEDS_REVIEW')", name="ck_classifications_status"),
        sa.CheckConstraint("has_defect IS NULL OR has_defect IN (0, 1)", name="ck_classifications_has_defect"),
        sa.CheckConstraint("needs_review IS NULL OR needs_review IN (0, 1)", name="ck_classifications_needs_review"),
        sa.CheckConstraint(
            "(status = 'QUEUED' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('COMPLETED', 'RETRYABLE_FAILED', 'TERMINAL_FAILED', 'NEEDS_REVIEW') AND completed_at IS NOT NULL)",
            name="ck_classifications_status_times",
        ),
        sa.CheckConstraint("status <> 'COMPLETED' OR (has_defect IS NOT NULL AND needs_review = 0)", name="ck_classifications_completed_definitive"),
        sa.CheckConstraint("completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at", name="ck_classifications_time_order"),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.feedback_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["background_job_id"], ["background_jobs.background_job_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_versions.taxonomy_version_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("classification_id"),
        sa.UniqueConstraint("feedback_id", "attempt_number", name="uq_classifications_feedback_attempt"),
        sa.UniqueConstraint("classification_id", "taxonomy_version_id", name="uq_classifications_id_taxonomy"),
    )
    op.create_index("ix_classifications_feedback_completed", "classifications", ["feedback_id", "taxonomy_version_id", "status", "completed_at"])

    op.create_table(
        "classification_labels",
        sa.Column("classification_id", sa.String(36), nullable=False),
        sa.Column("label_role", sa.String(16), nullable=False),
        sa.Column("taxonomy_version_id", sa.String(128), nullable=False),
        sa.Column("category_code", sa.String(64), nullable=False),
        sa.Column("specific_issue_code", sa.String(64)),
        sa.Column("logical_defect_id", sa.String(128)),
        sa.Column("label_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("label_role IN ('PRIMARY', 'SECONDARY')", name="ck_classification_labels_role"),
        sa.CheckConstraint("(specific_issue_code IS NULL AND logical_defect_id IS NULL) OR (specific_issue_code IS NOT NULL AND logical_defect_id IS NOT NULL)", name="ck_classification_labels_issue_pair"),
        sa.CheckConstraint("(label_role = 'PRIMARY' AND label_order = 0) OR (label_role = 'SECONDARY' AND label_order = 1)", name="ck_classification_labels_order"),
        sa.ForeignKeyConstraint(["classification_id", "taxonomy_version_id"], ["classifications.classification_id", "classifications.taxonomy_version_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["taxonomy_version_id", "category_code"], ["taxonomy_categories.taxonomy_version_id", "taxonomy_categories.category_code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["taxonomy_version_id", "category_code", "specific_issue_code", "logical_defect_id"], ["taxonomy_issue_codes.taxonomy_version_id", "taxonomy_issue_codes.category_code", "taxonomy_issue_codes.specific_issue_code", "taxonomy_issue_codes.logical_defect_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["logical_defect_id"], ["logical_defects.logical_defect_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("classification_id", "label_role"),
        sa.UniqueConstraint("classification_id", "label_order", name="uq_classification_labels_order"),
        sa.UniqueConstraint("classification_id", "taxonomy_version_id", "label_role", "logical_defect_id", name="uq_classification_labels_defect"),
    )
    op.create_index("uq_classification_labels_issue", "classification_labels", ["classification_id", "specific_issue_code"], unique=True, sqlite_where=sa.text("specific_issue_code IS NOT NULL"))

    op.create_table(
        "detection_rule_versions",
        sa.Column("rule_version", sa.String(128), nullable=False),
        sa.Column("taxonomy_version_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("config_text", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.Column("activated_at", sa.String(24)),
        sa.Column("retired_at", sa.String(24)),
        sa.CheckConstraint("state IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_detection_rule_versions_state"),
        sa.CheckConstraint(
            "(state = 'DRAFT' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(state = 'ACTIVE' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(state = 'RETIRED' AND activated_at IS NOT NULL AND retired_at IS NOT NULL AND retired_at >= activated_at)",
            name="ck_detection_rule_versions_lifecycle",
        ),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_versions.taxonomy_version_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("rule_version"),
        sa.UniqueConstraint("rule_version", "taxonomy_version_id", name="uq_detection_rules_version_taxonomy"),
    )
    op.create_index("uq_detection_rules_one_active", "detection_rule_versions", ["state"], unique=True, sqlite_where=sa.text("state = 'ACTIVE'"))

    op.create_table(
        "defect_clusters",
        sa.Column("cluster_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(256), nullable=False),
        sa.Column("supplier_id", sa.String(256), nullable=False),
        sa.Column("batch_id", sa.String(256), nullable=False),
        sa.Column("logical_defect_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.supplier_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["logical_defect_id"], ["logical_defects.logical_defect_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id", "product_id", "supplier_id"], ["batches.batch_id", "batches.product_id", "batches.supplier_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("cluster_id"),
        sa.UniqueConstraint("product_id", "supplier_id", "batch_id", "logical_defect_id", name="uq_defect_clusters_context"),
        sa.UniqueConstraint("cluster_id", "logical_defect_id", name="uq_defect_clusters_id_defect"),
    )

    op.create_table(
        "detection_results",
        sa.Column("detection_result_id", sa.String(36), nullable=False),
        sa.Column("result_key", sa.String(64), nullable=False),
        sa.Column("result_input_snapshot_text", sa.Text(), nullable=False),
        sa.Column("cluster_id", sa.String(36), nullable=False),
        sa.Column("taxonomy_version_id", sa.String(128), nullable=False),
        sa.Column("background_job_id", sa.String(36)),
        sa.Column("rule_version", sa.String(128), nullable=False),
        sa.Column("coverage_policy_version", sa.String(128), nullable=False),
        sa.Column("evaluation_mode", sa.String(32), nullable=False),
        sa.Column("evaluated_at", sa.String(24), nullable=False),
        sa.Column("observed_start_utc", sa.String(24), nullable=False),
        sa.Column("observed_end_utc", sa.String(24), nullable=False),
        sa.Column("baseline_start_utc", sa.String(24), nullable=False),
        sa.Column("baseline_end_utc", sa.String(24), nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("baseline_28d_count", sa.Integer(), nullable=False),
        sa.Column("normalized_baseline_7d", sa.Float()),
        sa.Column("observed_to_baseline_ratio", sa.Float()),
        sa.Column("coverage_state", sa.String(24), nullable=False),
        sa.Column("baseline_source_coverage_state", sa.String(16), nullable=False),
        sa.Column("observed_classification_coverage_state", sa.String(16), nullable=False),
        sa.Column("observed_classification_assessed_count", sa.Integer(), nullable=False),
        sa.Column("observed_classification_complete_count", sa.Integer(), nullable=False),
        sa.Column("baseline_classification_coverage_state", sa.String(16), nullable=False),
        sa.Column("baseline_classification_assessed_count", sa.Integer(), nullable=False),
        sa.Column("baseline_classification_complete_count", sa.Integer(), nullable=False),
        sa.Column("decision_state", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16)),
        sa.Column("incident_application_state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.String(24), nullable=False),
        sa.CheckConstraint("evaluation_mode IN ('CURRENT_MONITORING', 'HISTORICAL_RECOMPUTE')", name="ck_detection_results_mode"),
        sa.CheckConstraint("coverage_state IN ('SUFFICIENT_NONZERO', 'SUFFICIENT_ZERO', 'INSUFFICIENT')", name="ck_detection_results_coverage"),
        sa.CheckConstraint("baseline_source_coverage_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')", name="ck_detection_results_source_coverage"),
        sa.CheckConstraint("observed_classification_coverage_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')", name="ck_detection_results_observed_coverage"),
        sa.CheckConstraint("baseline_classification_coverage_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')", name="ck_detection_results_baseline_coverage"),
        sa.CheckConstraint("decision_state IN ('NO_TRIGGER', 'TRIGGERED', 'INSUFFICIENT_COVERAGE')", name="ck_detection_results_decision"),
        sa.CheckConstraint("incident_application_state IN ('NOT_APPLICABLE', 'PENDING', 'APPLIED', 'SUPERSEDED')", name="ck_detection_results_incident_state"),
        sa.CheckConstraint(
            "observed_count >= 0 AND baseline_28d_count >= 0 AND observed_classification_assessed_count >= 0 AND "
            "observed_classification_complete_count >= 0 AND baseline_classification_assessed_count >= 0 AND "
            "baseline_classification_complete_count >= 0 AND observed_classification_complete_count <= observed_classification_assessed_count AND "
            "baseline_classification_complete_count <= baseline_classification_assessed_count",
            name="ck_detection_results_counts",
        ),
        sa.CheckConstraint("observed_end_utc > observed_start_utc AND baseline_end_utc > baseline_start_utc", name="ck_detection_results_windows"),
        sa.CheckConstraint(
            "(evaluation_mode <> 'HISTORICAL_RECOMPUTE' OR incident_application_state = 'NOT_APPLICABLE') AND "
            "(decision_state <> 'INSUFFICIENT_COVERAGE' OR (coverage_state = 'INSUFFICIENT' AND severity IS NULL AND observed_to_baseline_ratio IS NULL AND incident_application_state = 'NOT_APPLICABLE'))",
            name="ck_detection_results_fail_closed",
        ),
        sa.ForeignKeyConstraint(["cluster_id"], ["defect_clusters.cluster_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["taxonomy_version_id"], ["taxonomy_versions.taxonomy_version_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rule_version", "taxonomy_version_id"], ["detection_rule_versions.rule_version", "detection_rule_versions.taxonomy_version_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["background_job_id", "taxonomy_version_id"], ["background_jobs.background_job_id", "background_jobs.taxonomy_version_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("detection_result_id"),
        sa.UniqueConstraint("result_key", name="uq_detection_results_result_key"),
        sa.UniqueConstraint("detection_result_id", "cluster_id", "taxonomy_version_id", name="uq_detection_results_context"),
    )
    op.create_index("ix_detection_results_cluster_evaluated", "detection_results", ["cluster_id", "evaluated_at"])
    op.create_index("ix_detection_results_job", "detection_results", ["background_job_id"])
    connection.exec_driver_sql(
        "CREATE TRIGGER trg_feedback_linkage_events_no_update BEFORE UPDATE ON feedback_linkage_events "
        "BEGIN SELECT RAISE(ABORT, 'feedback_linkage_events_are_append_only'); END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER trg_feedback_linkage_events_no_delete BEFORE DELETE ON feedback_linkage_events "
        "BEGIN SELECT RAISE(ABORT, 'feedback_linkage_events_are_append_only'); END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER trg_detection_rule_versions_immutable_config "
        "BEFORE UPDATE OF taxonomy_version_id, config_text ON detection_rule_versions "
        "WHEN OLD.taxonomy_version_id IS NOT NEW.taxonomy_version_id OR OLD.config_text IS NOT NEW.config_text "
        "BEGIN SELECT RAISE(ABORT, 'detection_rule_configuration_is_immutable'); END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER trg_detection_results_no_update BEFORE UPDATE ON detection_results "
        "BEGIN SELECT RAISE(ABORT, 'detection_results_are_immutable'); END"
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER trg_detection_results_no_delete BEFORE DELETE ON detection_results "
        "BEGIN SELECT RAISE(ABORT, 'detection_results_are_immutable'); END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in (
        "detection_results", "defect_clusters", "detection_rule_versions", "classification_labels",
        "classifications", "feedback_linkage_events", "ingestion_conflicts", "taxonomy_issue_codes",
        "logical_defects", "taxonomy_categories", "taxonomy_versions",
    ):
        if connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one():
            raise RuntimeError(f"Cannot downgrade while {table_name} contains M3 data")

    op.drop_index("ix_detection_results_job", table_name="detection_results")
    op.drop_index("ix_detection_results_cluster_evaluated", table_name="detection_results")
    for table_name in (
        "detection_results", "defect_clusters", "detection_rule_versions", "classification_labels",
        "classifications", "feedback_linkage_events", "ingestion_conflicts", "taxonomy_issue_codes",
        "logical_defects", "taxonomy_categories", "taxonomy_versions",
    ):
        op.drop_table(table_name)
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_background_jobs_taxonomy_update")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_background_jobs_taxonomy_insert")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_feedback_linkage_events_no_update")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_feedback_linkage_events_no_delete")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_detection_rule_versions_immutable_config")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_detection_results_no_update")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS trg_detection_results_no_delete")
    op.drop_index("uq_background_jobs_id_taxonomy", table_name="background_jobs")
    op.drop_column("background_jobs", "taxonomy_version_id")
