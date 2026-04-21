"""Integration test for the product-input → 2채널 수익 flow.

Exercises the end-to-end path that powers spec §6.2:

1. Seed a category + keyword (so ``?keyword_id=`` pre-fill is a real FK).
2. ``POST /products`` with URL + CNY + MOQ.
3. Parse the returned :class:`ProductScoreResponse`:
   - ``total_score`` is in 0..100
   - 2-channel comparison (SMARTSTORE + COUPANG) with margin/ROI/breakeven
   - ``recommended_channel`` is set to whichever side has the higher
     unit profit
4. ``GET /products/{id}`` returns the full detail including the history.
5. ``GET /products`` paginates the latest N.

The scorer is **not** mocked — the Scoring Agent's functional adapter
(``app.scoring.functional_adapter.build_functional_scorer``) is wired
via the service-layer loader, so this test also covers the contract
between the two agents.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Category, Keyword, KeywordStatus


def _seed(session: Session) -> Keyword:
    cat = Category(name="반려동물용품", is_certification_required=False)
    session.add(cat)
    session.flush()
    kw = Keyword(
        term="고양이 자동급수기",
        is_seed=True,
        status=KeywordStatus.ACTIVE,
        category_id=cat.id,
    )
    session.add(kw)
    session.flush()
    session.commit()
    return kw


def test_create_product_returns_two_channel_score(client, db_session) -> None:
    kw = _seed(db_session)

    payload = {
        "keyword_id": kw.id,
        "url": "https://detail.1688.com/offer/abc-int.html",
        "cny_price": 45.0,
        "moq": 50,
        "name": "고양이 자동급수기 2L",
        "notes": "통합 테스트",
    }
    resp = client.post("/products", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Envelope shape (spec §5.3).
    for key in (
        "product_id",
        "snapshot_date",
        "total_score",
        "opportunity_score",
        "profit_score",
        "risk_score",
        "stability_score",
        "recommendation",
        "channel_profits",
        "recommended_channel",
    ):
        assert key in body, f"missing key={key}"

    assert isinstance(body["product_id"], int) and body["product_id"] > 0
    assert 0 <= body["total_score"] <= 100
    assert body["recommendation"] in {"GO", "CONDITIONAL", "PASS"}

    # 2 channels must be present with consistent margin/ROI math.
    channels = {row["channel"]: row for row in body["channel_profits"]}
    assert set(channels) == {"SMARTSTORE", "COUPANG"}
    for side in channels.values():
        assert side["unit_cost_krw"] > 0
        assert side["expected_price_krw"] > 0
        assert side["breakeven_units"] >= 0

    # Recommended channel == higher unit_profit_krw side (or None on tie).
    ss = channels["SMARTSTORE"]
    cp = channels["COUPANG"]
    if ss["unit_profit_krw"] > cp["unit_profit_krw"]:
        assert body["recommended_channel"] == "SMARTSTORE"
    elif cp["unit_profit_krw"] > ss["unit_profit_krw"]:
        assert body["recommended_channel"] == "COUPANG"
    else:
        # Ties are allowed but extremely unlikely with the phase-1 fees.
        assert body["recommended_channel"] in {"SMARTSTORE", "COUPANG", None}


def test_get_product_detail_returns_history_and_list_endpoint(
    client, db_session
) -> None:
    _seed(db_session)

    payload = {
        "url": "https://detail.1688.com/offer/detail-int.html",
        "cny_price": 45.0,
        "moq": 50,
        "name": "자동급수기",
    }
    created = client.post("/products", json=payload)
    assert created.status_code == 201
    product_id = created.json()["product_id"]

    detail = client.get(f"/products/{product_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == product_id
    assert detail_body["url"] == payload["url"]
    assert detail_body["latest_score"] is not None
    # score_history has at least today's snapshot.
    assert len(detail_body["score_history"]) >= 1

    # Paginated list should now contain our product.
    listing = client.get("/products", params={"limit": 10, "offset": 0})
    assert listing.status_code == 200
    list_body = listing.json()
    assert list_body["total"] >= 1
    assert list_body["limit"] == 10
    assert list_body["offset"] == 0
    ids = [item["id"] for item in list_body["items"]]
    assert product_id in ids


def test_duplicate_url_returns_409(client, db_session) -> None:
    _seed(db_session)
    payload = {
        "url": "https://detail.1688.com/offer/dup-int.html",
        "cny_price": 45.0,
        "moq": 50,
    }
    first = client.post("/products", json=payload)
    assert first.status_code == 201

    second = client.post("/products", json=payload)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]
