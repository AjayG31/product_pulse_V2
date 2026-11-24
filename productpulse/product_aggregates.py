"""Version-scoped product aggregates derived from immutable source facts."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from productpulse.api_common import ApiError, page_meta
from productpulse.api_schemas import (
    DefectBreakdown,
    ProductAssociation,
    ProductDetail,
    ProductPage,
    ProductSummary,
)
from productpulse.models import (
    Batch,
    Classification,
    ClassificationLabel,
    Feedback,
    Product,
    Supplier,
    TaxonomyCategory,
    TaxonomyIssueCode,
    TaxonomyVersion,
)


def _utc_filter(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ApiError(422, "UTC_OFFSET_REQUIRED", "Date-time filters must include an explicit UTC offset.", "Validation failed")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _check_window(from_utc: datetime | None, to_utc: datetime | None) -> tuple[str | None, str | None]:
    start = _utc_filter(from_utc)
    end = _utc_filter(to_utc)
    if start is not None and end is not None and start >= end:
        raise ApiError(422, "INVALID_TIME_WINDOW", "The from_utc value must be earlier than to_utc.", "Validation failed")
    return start, end


def validate_taxonomy_version(db: Session, taxonomy_version_id: str) -> None:
    if not 1 <= len(taxonomy_version_id) <= 128 or db.get(TaxonomyVersion, taxonomy_version_id) is None:
        raise ApiError(422, "TAXONOMY_VERSION_INVALID", "Choose an existing taxonomy version for this aggregate context.", "Validation failed")


def latest_qualifying_classifications(
    db: Session,
    taxonomy_version_id: str,
    feedback_ids: list[str] | None = None,
) -> list[Classification]:
    primary_category_matches = exists(
        select(1)
        .select_from(ClassificationLabel)
        .join(
            TaxonomyCategory,
            and_(
                TaxonomyCategory.taxonomy_version_id == ClassificationLabel.taxonomy_version_id,
                TaxonomyCategory.category_code == ClassificationLabel.category_code,
            ),
        )
        .where(
            ClassificationLabel.classification_id == Classification.classification_id,
            ClassificationLabel.taxonomy_version_id == taxonomy_version_id,
            ClassificationLabel.label_role == "PRIMARY",
            or_(
                and_(Classification.has_defect.is_(True), TaxonomyCategory.category_kind == "DEFECT"),
                and_(Classification.has_defect.is_(False), TaxonomyCategory.category_kind == "NO_DEFECT"),
            ),
        )
    )
    row_number = func.row_number().over(
        partition_by=Classification.feedback_id,
        order_by=(Classification.completed_at.desc(), Classification.classification_id.collate("BINARY").desc()),
    ).label("version_rank")
    statement = select(
        Classification.classification_id,
        Classification.feedback_id,
        Classification.attempt_number,
        Classification.background_job_id,
        Classification.taxonomy_version_id,
        Classification.api_path,
        Classification.model_id,
        Classification.prompt_version,
        Classification.schema_version,
        Classification.status,
        Classification.has_defect,
        Classification.needs_review,
        Classification.severity_hint,
        Classification.evidence_excerpt,
        Classification.provider_request_id,
        Classification.input_tokens,
        Classification.output_tokens,
        Classification.estimated_cost_micro_usd,
        Classification.latency_ms,
        Classification.error_code,
        Classification.created_at,
        Classification.started_at,
        Classification.completed_at,
        row_number,
    ).where(
        Classification.taxonomy_version_id == taxonomy_version_id,
        Classification.status == "COMPLETED",
        Classification.needs_review.is_(False),
        Classification.has_defect.is_not(None),
        primary_category_matches,
    )
    if feedback_ids is not None:
        if not feedback_ids:
            return []
        statement = statement.where(Classification.feedback_id.in_(feedback_ids))
    ranked = statement.subquery()
    identifiers = select(ranked.c.classification_id).where(ranked.c.version_rank == 1)
    return db.scalars(select(Classification).where(Classification.classification_id.in_(identifiers))).all()


def _selected_feedback(
    db: Session,
    product_id: str,
    from_utc: datetime | None,
    to_utc: datetime | None,
) -> list[Feedback]:
    start, end = _check_window(from_utc, to_utc)
    statement = select(Feedback).where(Feedback.product_id == product_id)
    if start is not None:
        statement = statement.where(Feedback.event_time_utc >= start)
    if end is not None:
        statement = statement.where(Feedback.event_time_utc < end)
    return db.scalars(statement.order_by(Feedback.event_time_utc, Feedback.feedback_id)).all()


def _units(records: list[Feedback]) -> int | None:
    if not records:
        return 0
    known = [record.return_quantity for record in records if record.return_quantity is not None]
    return sum(known) if known else None


def product_summary(
    db: Session,
    product: Product,
    taxonomy_version_id: str,
    *,
    from_utc: datetime | None = None,
    to_utc: datetime | None = None,
) -> ProductSummary:
    validate_taxonomy_version(db, taxonomy_version_id)
    records = _selected_feedback(db, product.product_id, from_utc, to_utc)
    selected = latest_qualifying_classifications(
        db, taxonomy_version_id, [record.feedback_id for record in records]
    )
    outcomes = {item.feedback_id: bool(item.has_defect) for item in selected}
    linked = [record for record in records if record.linkage_status == "LINKED"]
    pending = [record for record in records if record.linkage_status == "LINKAGE_PENDING"]
    linked_returns = [record for record in linked if record.source_type == "RETURN"]
    pending_returns = [record for record in pending if record.source_type == "RETURN"]
    linked_classified = [record for record in linked if record.feedback_id in outcomes]
    pending_classified = [record for record in pending if record.feedback_id in outcomes]
    return ProductSummary(
        product_id=product.product_id,
        taxonomy_version_id=taxonomy_version_id,
        name=product.name,
        category=product.category,
        defect_feedback_count=sum(outcomes.get(record.feedback_id) is True for record in linked),
        unclassified_feedback_count=len(linked) - len(linked_classified),
        return_record_count=len(linked_returns),
        returned_units=_units(linked_returns),
        linkage_pending_feedback_count=len(pending),
        linkage_pending_defect_feedback_count=sum(outcomes.get(record.feedback_id) is True for record in pending),
        linkage_pending_unclassified_feedback_count=len(pending) - len(pending_classified),
        linkage_pending_return_record_count=len(pending_returns),
        linkage_pending_returned_units=_units(pending_returns),
    )


def list_products(
    db: Session,
    taxonomy_version_id: str,
    *,
    q: str | None = None,
    from_utc: datetime | None = None,
    to_utc: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "product_id",
    sort_order: str = "asc",
) -> ProductPage:
    validate_taxonomy_version(db, taxonomy_version_id)
    _check_window(from_utc, to_utc)
    if sort_by not in {"product_id", "name", "defect_feedback_count", "return_record_count"} or sort_order not in {"asc", "desc"}:
        raise ApiError(422, "INVALID_SORT", "The requested product sort is not supported.", "Validation failed")
    products = db.scalars(select(Product).where(
        Product.product_id.ilike(f"%{q}%") if q else True
    ).order_by(Product.product_id)).all()
    summaries = [product_summary(db, product, taxonomy_version_id, from_utc=from_utc, to_utc=to_utc) for product in products]
    def sort_key(item: ProductSummary):
        value = getattr(item, sort_by)
        if isinstance(value, str):
            return (value is None, (value or "").casefold(), item.product_id)
        return (value is None, value if value is not None else 0, item.product_id)

    summaries.sort(key=sort_key, reverse=sort_order == "desc")
    total = len(summaries)
    offset = (page - 1) * page_size
    return ProductPage(taxonomy_version_id=taxonomy_version_id, items=summaries[offset:offset + page_size], page=page_meta(page, page_size, total))


def product_detail(
    db: Session,
    product: Product,
    taxonomy_version_id: str,
    *,
    from_utc: datetime | None = None,
    to_utc: datetime | None = None,
) -> ProductDetail:
    validate_taxonomy_version(db, taxonomy_version_id)
    records = _selected_feedback(db, product.product_id, from_utc, to_utc)
    summary = product_summary(db, product, taxonomy_version_id, from_utc=from_utc, to_utc=to_utc)
    linked_associations: dict[tuple[str, str], int] = defaultdict(int)
    for record in records:
        if record.linkage_status == "LINKED" and record.supplier_id and record.batch_id:
            linked_associations[(record.supplier_id, record.batch_id)] += 1
    supplier_ids = {supplier_id for supplier_id, _batch_id in linked_associations}
    suppliers = {
        supplier.supplier_id: supplier.name
        for supplier in db.scalars(select(Supplier).where(Supplier.supplier_id.in_(supplier_ids))).all()
    } if supplier_ids else {}
    associations = [
        ProductAssociation(
            product_id=product.product_id,
            supplier_id=supplier_id,
            supplier_name=suppliers.get(supplier_id),
            batch_id=batch_id,
            linked_feedback_count=count,
        )
        for (supplier_id, batch_id), count in sorted(linked_associations.items())
    ]

    selected = latest_qualifying_classifications(db, taxonomy_version_id, [record.feedback_id for record in records])
    selected_by_feedback = {item.feedback_id: item for item in selected}
    feedback_by_id = {record.feedback_id: record for record in records}
    label_rows = db.execute(
        select(ClassificationLabel, TaxonomyCategory, TaxonomyIssueCode)
        .join(TaxonomyCategory, and_(
            TaxonomyCategory.taxonomy_version_id == ClassificationLabel.taxonomy_version_id,
            TaxonomyCategory.category_code == ClassificationLabel.category_code,
        ))
        .outerjoin(TaxonomyIssueCode, and_(
            TaxonomyIssueCode.taxonomy_version_id == ClassificationLabel.taxonomy_version_id,
            TaxonomyIssueCode.category_code == ClassificationLabel.category_code,
            TaxonomyIssueCode.specific_issue_code == ClassificationLabel.specific_issue_code,
            TaxonomyIssueCode.logical_defect_id == ClassificationLabel.logical_defect_id,
        ))
        .where(
            ClassificationLabel.taxonomy_version_id == taxonomy_version_id,
            ClassificationLabel.classification_id.in_([item.classification_id for item in selected] or [""]),
            ClassificationLabel.logical_defect_id.is_not(None),
        )
    ).all()
    counts: dict[tuple[str, str, str, str], set[tuple[str, str]]] = defaultdict(set)
    for label, category, issue in label_rows:
        classification = next((item for item in selected if item.classification_id == label.classification_id), None)
        if classification is None or not classification.has_defect:
            continue
        record = feedback_by_id.get(classification.feedback_id)
        if record is None:
            continue
        display = issue.display_name if issue is not None else category.display_name
        counts[(label.category_code, category.display_name, label.logical_defect_id, display)].add((record.feedback_id, record.linkage_status))
    breakdown = [
        DefectBreakdown(
            taxonomy_version_id=taxonomy_version_id,
            category_code=category_code,
            category_name=category_name,
            logical_defect_id=logical_defect_id,
            display_name=display_name,
            distinct_feedback_count=sum(status == "LINKED" for _feedback_id, status in feedback_status),
            linkage_pending_distinct_feedback_count=sum(status == "LINKAGE_PENDING" for _feedback_id, status in feedback_status),
        )
        for (category_code, category_name, logical_defect_id, display_name), feedback_status in sorted(counts.items())
    ]
    return ProductDetail(
        product=summary,
        associations=associations,
        defect_breakdown=breakdown,
        generated_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )
