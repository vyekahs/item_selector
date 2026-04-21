"""Tests for ``POST /feedback``."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Product


def _seed_product(session: Session, *, url: str) -> Product:
    product = Product(
        url=url,
        name="test",
        cny_price=45,
        moq=50,
    )
    session.add(product)
    session.flush()
    session.commit()
    return product


def test_submit_feedback_ok(client: TestClient, api_db_session: Session) -> None:
    product = _seed_product(api_db_session, url="https://detail.1688.com/offer/fb1.html")
    payload = {
        "product_id": product.id,
        "purchased": True,
        "monthly_sales": 120,
        "actual_revenue": 4_560_000,
        "notes": "첫 달 실적",
    }
    response = client.post("/feedback", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["product_id"] == product.id
    assert body["purchased"] is True
    assert body["monthly_sales"] == 120
    assert body["actual_revenue"] == 4_560_000
    assert body["recorded_at"] is not None


def test_submit_feedback_product_not_found(client: TestClient) -> None:
    response = client.post(
        "/feedback",
        json={
            "product_id": 9_999_999,
            "purchased": False,
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["detail"].startswith("product id=")


def test_submit_feedback_validation_errors(client: TestClient) -> None:
    # Missing product_id
    response = client.post("/feedback", json={"purchased": True})
    assert response.status_code == 422

    # Negative sales
    response = client.post(
        "/feedback",
        json={"product_id": 1, "monthly_sales": -1},
    )
    assert response.status_code == 422
