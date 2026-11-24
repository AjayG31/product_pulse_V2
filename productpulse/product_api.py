from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from productpulse.api_common import ApiError
from productpulse.api_schemas import ProductDetail, ProductPage
from productpulse.auth_api import AuthContext, get_normal_context
from productpulse.models import Product
from productpulse.product_aggregates import list_products, product_detail


router = APIRouter()


@router.get("/products", response_model=ProductPage, tags=["Products"])
def get_products(
    taxonomy_version_id: str = Query(..., min_length=1, max_length=128),
    q: str | None = Query(default=None, max_length=200),
    from_utc: datetime | None = Query(default=None),
    to_utc: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    sort_by: Literal["product_id", "name", "defect_feedback_count", "return_record_count"] = Query(default="product_id"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    context: AuthContext = Depends(get_normal_context),
) -> ProductPage:
    return list_products(
        context.db,
        taxonomy_version_id,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/products/{product_id}", response_model=ProductDetail, tags=["Products"])
def get_product(
    product_id: str,
    taxonomy_version_id: str = Query(..., min_length=1, max_length=128),
    from_utc: datetime | None = Query(default=None),
    to_utc: datetime | None = Query(default=None),
    context: AuthContext = Depends(get_normal_context),
) -> ProductDetail:
    product = context.db.scalar(select(Product).where(Product.product_id == product_id))
    if product is None:
        raise ApiError(404, "PRODUCT_NOT_FOUND", "The requested product was not found.", "Not found")
    return product_detail(context.db, product, taxonomy_version_id, from_utc=from_utc, to_utc=to_utc)
