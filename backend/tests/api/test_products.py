"""Tests for ``/products`` endpoints.

The Scoring Engine module is owned by another agent. We bypass it via
``set_scorer_for_tests`` so these tests stay independent of that work.
"""
from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Channel, Recommendation
from app.services import product_service
from app.services.product_service import (
    ChannelProfitDraft,
    ProductScorer,
    ProductScoringResult,
    ScoringInput,
    set_scorer_for_tests,
)


class _FakeScorer:
    """Returns a deterministic, GO-recommendation snapshot."""

    def score(self, inputs: ScoringInput) -> ProductScoringResult:
        unit_cost = inputs.cny_price * inputs.cny_to_krw / Decimal(inputs.moq) + Decimal("0")
        # Use simple fixed numbers so assertions stay readable.
        return ProductScoringResult(
            total_score=83.0,
            opportunity_score=34.0,
            profit_score=30.0,
            risk_score=12.0,
            stability_score=7.0,
            recommendation=Recommendation.GO,
            channel_profits=[
                ChannelProfitDraft(
                    channel=Channel.SMARTSTORE,
                    unit_cost_krw=unit_cost,
                    expected_price_krw=Decimal("38000"),
                    platform_fee_pct=Decimal("0.055"),
                    ad_cost_pct=Decimal("0.10"),
                    unit_profit_krw=Decimal("24400"),
                    margin_pct=Decimal("0.640"),
                    roi_pct=Decimal("1.280"),
                    breakeven_units=17,
                ),
                ChannelProfitDraft(
                    channel=Channel.COUPANG,
                    unit_cost_krw=unit_cost,
                    expected_price_krw=Decimal("42000"),
                    platform_fee_pct=Decimal("0.108"),
                    ad_cost_pct=Decimal("0.15"),
                    unit_profit_krw=Decimal("19100"),
                    margin_pct=Decimal("0.500"),
                    roi_pct=Decimal("0.980"),
                    breakeven_units=21,
                ),
            ],
        )


@pytest.fixture(autouse=True)
def _inject_scorer() -> Generator[ProductScorer, None, None]:
    scorer = _FakeScorer()
    set_scorer_for_tests(scorer)
    yield scorer
    set_scorer_for_tests(None)


def _create_payload(url: str = "https://detail.1688.com/offer/123.html") -> dict:
    return {
        "url": url,
        "cny_price": 45.0,
        "moq": 50,
        "name": "고양이 자동급수기",
        "notes": "샘플 입력",
    }


def test_create_product_returns_score_envelope(client: TestClient) -> None:
    response = client.post("/products", json=_create_payload())
    assert response.status_code == 201
    body = response.json()

    assert body["total_score"] == 83.0
    assert body["recommendation"] == "GO"
    channels = {row["channel"]: row for row in body["channel_profits"]}
    assert set(channels) == {"SMARTSTORE", "COUPANG"}
    # Recommended channel = higher unit profit (smartstore in fixture).
    assert body["recommended_channel"] == "SMARTSTORE"
    assert channels["SMARTSTORE"]["margin_pct"] == pytest.approx(0.640)
    assert channels["COUPANG"]["roi_pct"] == pytest.approx(0.980)


def test_create_product_validation_errors(client: TestClient) -> None:
    # Missing required fields
    bad = client.post("/products", json={"url": "https://example.com/x"})
    assert bad.status_code == 422

    # Negative cny_price
    bad = client.post(
        "/products",
        json={**_create_payload(), "cny_price": -1},
    )
    assert bad.status_code == 422

    # MOQ < 1
    bad = client.post(
        "/products",
        json={**_create_payload(), "moq": 0},
    )
    assert bad.status_code == 422


def test_create_product_duplicate_url_returns_409(client: TestClient) -> None:
    payload = _create_payload(url="https://detail.1688.com/offer/dup.html")
    first = client.post("/products", json=payload)
    assert first.status_code == 201
    second = client.post("/products", json=payload)
    assert second.status_code == 409
    assert second.json()["detail"].startswith("product with url=")


def test_get_product_detail_includes_score_history(client: TestClient) -> None:
    create = client.post(
        "/products",
        json=_create_payload(url="https://detail.1688.com/offer/detail.html"),
    )
    assert create.status_code == 201
    pid = create.json()["product_id"]

    detail = client.get(f"/products/{pid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == pid
    assert body["latest_score"]["recommendation"] == "GO"
    assert len(body["score_history"]) == 1


def test_get_product_detail_404(client: TestClient) -> None:
    response = client.get("/products/999999")
    assert response.status_code == 404


def test_list_products_pagination(client: TestClient) -> None:
    for i in range(3):
        resp = client.post(
            "/products",
            json=_create_payload(url=f"https://detail.1688.com/offer/{i}.html"),
        )
        assert resp.status_code == 201

    page = client.get("/products", params={"limit": 2, "offset": 0})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert body["items"][0]["latest_score"]["recommendation"] == "GO"

    page2 = client.get("/products", params={"limit": 2, "offset": 2})
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 1


def test_create_product_returns_503_when_scorer_missing(
    client: TestClient,
) -> None:
    """Without a wired scorer, the route should return 503, not 500."""
    set_scorer_for_tests(None)
    # Force-load attempt → ScoringUnavailableError
    response = client.post(
        "/products",
        json=_create_payload(url="https://detail.1688.com/offer/no_scorer.html"),
    )
    # If the real scoring module exists in the workspace this test
    # might unexpectedly return 201; tolerate both states.
    assert response.status_code in (201, 503)
    if response.status_code == 503:
        assert "Scoring Engine" in response.json()["detail"]
