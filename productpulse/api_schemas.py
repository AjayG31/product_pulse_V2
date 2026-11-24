from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class PublicUser(StrictModel):
    user_id: str
    email: str
    role: Literal["ADMIN", "BUSINESS_USER"]
    status: Literal["ACTIVE", "DEACTIVATED"]
    must_change_password: bool
    created_at: str
    updated_at: str


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128, json_schema_extra={"writeOnly": True})


class PasswordChangeRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=128, json_schema_extra={"writeOnly": True})
    new_password: str = Field(min_length=15, max_length=128, json_schema_extra={"writeOnly": True})


class LoginResponse(StrictModel):
    user: PublicUser
    csrf_token: str


class PreLoginCsrfResponse(StrictModel):
    csrf_token: str


class CreateUserRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["ADMIN", "BUSINESS_USER"]
    initial_password: str = Field(min_length=15, max_length=128, json_schema_extra={"writeOnly": True})


class ResetUserPasswordRequest(StrictModel):
    temporary_password: str = Field(min_length=15, max_length=128, json_schema_extra={"writeOnly": True})


class DeactivateUserRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=1000)


class PageMeta(StrictModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class UserPage(StrictModel):
    items: list[PublicUser]
    page: PageMeta


UploadKind = Literal["REVIEWS", "RETURNS", "PRODUCT_REFERENCE", "SUPPLIER_REFERENCE", "BATCH_REFERENCE"]
PreviewState = Literal["READY", "INVALID", "CONFIRMED", "EXPIRED"]
PreviewRowStatus = Literal["ACCEPTED", "REJECTED", "DUPLICATE_NOOP", "CONFLICT"]


class UploadColumnMapping(StrictModel):
    source_column_index: int = Field(ge=0)
    source_header: str = Field(min_length=1, max_length=1024)
    target_field: str = Field(min_length=1, max_length=40)


class UploadPreviewCounts(StrictModel):
    total_rows: int = Field(ge=0, le=50000)
    accepted_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    duplicate_noop_rows: int = Field(ge=0)
    conflict_rows: int = Field(ge=0)


class RejectionReportLink(StrictModel):
    available: bool
    href: str | None = None
    content_type: str | None = None


class UploadPreviewResponse(StrictModel):
    preview_id: str
    upload_id: str
    upload_kind: UploadKind
    original_filename: str
    file_size_bytes: int = Field(ge=1, le=20000000)
    verified_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_contract_version: str
    column_mappings: list[UploadColumnMapping]
    state: PreviewState
    counts: UploadPreviewCounts
    rejection_report: RejectionReportLink | None = None
    uploaded_by: str | None = None
    created_at: str
    confirmed_by: str | None = None
    confirmed_at: str | None = None


class UploadPreviewRowResponse(StrictModel):
    preview_id: str
    row_number: int = Field(ge=1, le=50000)
    row_status: PreviewRowStatus
    source_type: Literal["REVIEW", "RETURN"] | None = None
    source_record_id: str | None = None
    rejection_codes: list[str]
    rejection_detail: str | None = None


class UploadPreviewRowPage(StrictModel):
    items: list[UploadPreviewRowResponse]
    page: PageMeta


ConflictKind = Literal["SOURCE_PAYLOAD", "REFERENCE_MAPPING"]
ConflictState = Literal["PENDING", "RESOLVED", "DISMISSED"]
ConflictDecision = Literal["KEEP_EXISTING", "APPLY_INCOMING_REFERENCE", "DISMISS"]


class IngestionConflictResponse(StrictModel):
    conflict_id: str
    preview_id: str
    row_number: int = Field(ge=1, le=50000)
    conflict_kind: ConflictKind
    existing_feedback_id: str | None = None
    source_type: Literal["REVIEW", "RETURN"] | None = None
    source_record_id: str | None = None
    existing_value_hash: str | None = None
    incoming_value_hash: str | None = None
    mapping_key: str | None = None
    state: ConflictState
    resolution_note: str | None = None
    created_at: str
    resolved_by: str | None = None
    resolved_at: str | None = None


class IngestionConflictPage(StrictModel):
    items: list[IngestionConflictResponse]
    page: PageMeta


class ResolveConflictRequest(StrictModel):
    decision: ConflictDecision
    expected_existing_value_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    resolution_note: str = Field(min_length=1, max_length=2000)


ImportProcessingMode = Literal["HISTORICAL_BATCH", "INCREMENTAL_RESPONSES"]
IngestionJobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED"]
RetryEligibilityReason = Literal[
    "ELIGIBLE", "NOT_FAILED", "WORK_IN_PROGRESS", "NO_RETRYABLE_WORK", "BLOCKING_CAUSE_UNRESOLVED",
    "RETRY_POLICY_BLOCKED", "PERMANENT_FAILURE", "OUTCOME_UNKNOWN", "NOT_RETRYABLE",
]


class ConfirmPreviewRequest(StrictModel):
    verified_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    processing_mode: ImportProcessingMode | None = None


class IngestionJobCounts(StrictModel):
    total_rows: int = Field(ge=0)
    accepted_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    duplicate_noop_rows: int = Field(ge=0)
    conflict_rows: int = Field(ge=0)
    persisted_feedback: int = Field(ge=0)


class RetryEligibility(StrictModel):
    eligible: bool
    reason_code: RetryEligibilityReason


class IngestionJobResponse(StrictModel):
    job_id: str
    preview_id: str
    idempotency_key: str
    processing_mode: ImportProcessingMode | None
    status: IngestionJobStatus
    counts: IngestionJobCounts
    retry_eligibility: RetryEligibility
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    last_error_code: str | None = None
    rejection_report: RejectionReportLink | None = None


class IngestionJobPage(StrictModel):
    items: list[IngestionJobResponse]
    page: PageMeta


BackgroundJobType = Literal["INGESTION", "CLASSIFICATION", "BATCH_POLL", "DETECTION", "RECONCILIATION"]
BackgroundJobStatus = Literal["QUEUED", "RUNNING", "RETRY_WAIT", "COMPLETED", "PARTIAL", "FAILED"]


class BackgroundJobResponse(StrictModel):
    background_job_id: str
    job_type: BackgroundJobType
    status: BackgroundJobStatus
    ingestion_job_id: str | None = None
    attempt_count: int = Field(ge=0)
    max_attempts: int | None = Field(default=None, ge=1)
    scheduled_at: str
    next_attempt_at: str | None = None
    provider_batch_id: str | None = None
    last_error_code: str | None = None
    last_error_summary: str | None = None
    retry_eligibility: RetryEligibility
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class IngestionRetryResponse(StrictModel):
    ingestion_job: IngestionJobResponse
    run: BackgroundJobResponse


LinkageStatus = Literal["LINKED", "LINKAGE_PENDING"]


class FeedbackLinkageRequest(StrictModel):
    expected_linkage_status: LinkageStatus
    expected_supplier_id: str | None
    expected_batch_id: str | None
    supplier_id: str = Field(min_length=1, max_length=256)
    batch_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=1000)


class FeedbackLinkageResponse(StrictModel):
    feedback_id: str
    linkage_status: LinkageStatus
    supplier_id: str
    batch_id: str
    linkage_event_id: str
    recompute_job_id: str
    updated_at: str


class ProductSummary(StrictModel):
    product_id: str
    taxonomy_version_id: str
    name: str | None = None
    category: str | None = None
    defect_feedback_count: int = Field(ge=0)
    unclassified_feedback_count: int = Field(ge=0)
    return_record_count: int = Field(ge=0)
    returned_units: int | None = Field(default=None, ge=0)
    linkage_pending_feedback_count: int = Field(ge=0)
    linkage_pending_defect_feedback_count: int = Field(ge=0)
    linkage_pending_unclassified_feedback_count: int = Field(ge=0)
    linkage_pending_return_record_count: int = Field(ge=0)
    linkage_pending_returned_units: int | None = Field(default=None, ge=0)


class ProductPage(StrictModel):
    taxonomy_version_id: str
    items: list[ProductSummary]
    page: PageMeta


class ProductAssociation(StrictModel):
    product_id: str
    supplier_id: str
    supplier_name: str | None = None
    batch_id: str
    linked_feedback_count: int = Field(ge=0)


class DefectBreakdown(StrictModel):
    taxonomy_version_id: str
    category_code: str
    category_name: str
    logical_defect_id: str
    display_name: str
    distinct_feedback_count: int = Field(ge=0)
    linkage_pending_distinct_feedback_count: int = Field(ge=0)


class ProductDetail(StrictModel):
    product: ProductSummary
    associations: list[ProductAssociation]
    defect_breakdown: list[DefectBreakdown]
    generated_at: str

