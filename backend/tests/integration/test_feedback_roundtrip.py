"""Feedback round-trip integration.

Exercises the full feedback path (spec §6.3):

1. ``POST /products`` — create a scored product (scoring agent wired).
2. ``POST /feedback`` — submit 60-day actual-sales figures.
3. Query the DB directly to confirm the ``feedbacks`` row exists, is
   linked to the product, and carries the expected values.

The feedback response doesn't currently surface inside
``GET /products/{id}`` (no ``feedbacks`` array on
:class:`ProductDetailResponse`), so "reflected in the detail" is
verified at the DB-relationship level instead of the HTTP payload.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import Category, Feedback, Keyword, KeywordStatus, Product


def _seed(session) -> None:
    cat = Category(name="반려동물용품")
    session.add(cat)
    session.flush()
    session.add(
        Keyword(
            term="고양이 자동급수기",
            is_seed=True,
            status=KeywordStatus.ACTIVE,
            category_id=cat.id,
        )
    )
    session.flush()
    session.commit()


def test_feedback_is_persisted_and_linked(client, db_session) -> None:
    _seed(db_session)

    product_resp = client.post(
        "/products",
        json={
            "url": "https://detail.1688.com/offer/fb-int.html",
            "cny_price": 45.0,
            "moq": 50,
            "name": "고양이 자동급수기 2L",
        },
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["product_id"]

    feedback_payload = {
        "product_id": product_id,
        "purchased": True,
        "monthly_sales": 120,
        "actual_revenue": 4_560_000,
        "notes": "첫 달 실적",
    }
    fb_resp = client.post("/feedback", json=feedback_payload)
    assert fb_resp.status_code == 201
    fb_body = fb_resp.json()
    assert fb_body["product_id"] == product_id
    assert fb_body["purchased"] is True
    assert fb_body["monthly_sales"] == 120
    assert fb_body["actual_revenue"] == 4_560_000
    assert fb_body["recorded_at"] is not None

    # DB assertion: feedbacks row exists + is linked via FK.
    row = db_session.execute(
        select(Feedback).where(Feedback.id == fb_body["id"])
    ).scalar_one()
    assert row.product_id == product_id
    assert row.purchased is True
    assert row.monthly_sales == 120
    assert float(row.actual_revenue) == 4_560_000.0

    # Product-side relationship is populated.
    product = db_session.execute(
        select(Product).where(Product.id == product_id)
    ).scalar_one()
    linked = list(product.feedbacks)
    assert len(linked) == 1
    assert linked[0].id == fb_body["id"]


def test_feedback_404_when_product_missing(client, db_session) -> None:
    _seed(db_session)

    resp = client.post(
        "/feedback",
        json={"product_id": 9_999_999, "purchased": False},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]
