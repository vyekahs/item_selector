"""CRUD + constraint tests for every key ORM model.

We don't aim for exhaustive column coverage — just enough to prove
that:
    * each model can round-trip through the DB
    * FKs cascade / restrict where declared
    * UNIQUE constraints raise IntegrityError
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ApiCache,
    Category,
    Channel,
    ChannelProfit,
    CoupangFee,
    ExchangeRate,
    Feedback,
    HsCode,
    ImportStat,
    Keyword,
    KeywordHsMapping,
    KeywordMetric,
    KeywordStatus,
    OpportunityScore,
    Product,
    ProductScore,
    Recommendation,
)


# ---- Category --------------------------------------------------------------


def test_category_self_reference_cascade_restrict(db_session: Session) -> None:
    parent = Category(name="root", is_certification_required=False)
    db_session.add(parent)
    db_session.flush()

    child = Category(name="child", parent_id=parent.id)
    db_session.add(child)
    db_session.flush()

    assert child.parent is not None
    assert child.parent.id == parent.id
    assert parent.children[0].id == child.id

    # ON DELETE RESTRICT must reject deletion at the DB level.
    # Use raw SQL to bypass the ORM relationship cascade (which would
    # delete the child first and never trigger the FK RESTRICT).
    from sqlalchemy import text as _text

    sp = db_session.begin_nested()
    with pytest.raises(IntegrityError):
        db_session.execute(
            _text("DELETE FROM categories WHERE id = :id"),
            {"id": parent.id},
        )
        db_session.flush()
    sp.rollback()


# ---- HsCode ---------------------------------------------------------------


def test_hs_code_unique_constraint(db_session: Session) -> None:
    db_session.add(HsCode(code="230910", name_ko="개·고양이용 사료"))
    db_session.flush()

    sp = db_session.begin_nested()
    db_session.add(HsCode(code="230910", name_ko="duplicate"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()


def test_hs_code_check_constraint_on_length(db_session: Session) -> None:
    # 7-digit code must be rejected by the CHECK constraint.
    sp = db_session.begin_nested()
    db_session.add(HsCode(code="1234567", name_ko="invalid"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()


# ---- Keyword --------------------------------------------------------------


def test_keyword_crud_and_status_default(db_session: Session) -> None:
    kw = Keyword(term="고양이 자동급수기", is_seed=True)
    db_session.add(kw)
    db_session.flush()
    db_session.refresh(kw)

    assert kw.id is not None
    assert kw.status == KeywordStatus.PENDING
    assert kw.is_seed is True

    # update
    kw.status = KeywordStatus.ACTIVE
    db_session.flush()
    assert kw.status == KeywordStatus.ACTIVE

    # unique
    sp = db_session.begin_nested()
    db_session.add(Keyword(term="고양이 자동급수기"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()


# ---- KeywordHsMapping -----------------------------------------------------


def test_keyword_hs_mapping_cascade_and_unique(db_session: Session) -> None:
    kw = Keyword(term="펫 매트")
    hs = HsCode(code="630790", name_ko="펫 매트")
    db_session.add_all([kw, hs])
    db_session.flush()

    mapping = KeywordHsMapping(
        keyword_id=kw.id, hs_code=hs.code, confidence=Decimal("0.85")
    )
    db_session.add(mapping)
    db_session.flush()

    # Unique on (keyword_id, hs_code)
    sp = db_session.begin_nested()
    db_session.add(
        KeywordHsMapping(keyword_id=kw.id, hs_code=hs.code, confidence=Decimal("0.5"))
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()

    # Cascade on keyword delete
    kw_id = kw.id
    db_session.delete(kw)
    db_session.flush()
    remaining = db_session.execute(
        select(KeywordHsMapping).where(KeywordHsMapping.keyword_id == kw_id)
    ).scalars().all()
    assert remaining == []


def test_keyword_hs_mapping_confidence_check(db_session: Session) -> None:
    kw = Keyword(term="펫 캠")
    hs = HsCode(code="852580", name_ko="카메라")
    db_session.add_all([kw, hs])
    db_session.flush()
    sp = db_session.begin_nested()
    db_session.add(
        KeywordHsMapping(keyword_id=kw.id, hs_code=hs.code, confidence=Decimal("1.5"))
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()


# ---- KeywordMetric --------------------------------------------------------


def test_keyword_metric_snapshot_unique(db_session: Session) -> None:
    kw = Keyword(term="펫 휠")
    db_session.add(kw)
    db_session.flush()

    snap = date(2026, 4, 1)
    db_session.add(
        KeywordMetric(
            keyword_id=kw.id,
            snapshot_date=snap,
            monthly_search_volume=12000,
            competition_score=Decimal("0.32"),
        )
    )
    db_session.flush()

    sp = db_session.begin_nested()
    db_session.add(
        KeywordMetric(keyword_id=kw.id, snapshot_date=snap, monthly_search_volume=999)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()


# ---- ImportStat -----------------------------------------------------------


def test_import_stat_period_unique(db_session: Session) -> None:
    hs = HsCode(code="230910", name_ko="개·고양이용 사료")
    db_session.add(hs)
    db_session.flush()

    db_session.add(
        ImportStat(
            hs_code=hs.code,
            year_month="2026-03",
            country_code="CN",
            import_quantity=Decimal("12345.000"),
            import_value_usd=Decimal("987654.32"),
        )
    )
    db_session.flush()

    sp = db_session.begin_nested()
    db_session.add(
        ImportStat(
            hs_code=hs.code,
            year_month="2026-03",
            country_code="CN",
            import_quantity=Decimal("1.0"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()


# ---- OpportunityScore -----------------------------------------------------


def test_opportunity_score_round_trip(db_session: Session) -> None:
    kw = Keyword(term="고양이 자동급수기")
    db_session.add(kw)
    db_session.flush()

    score = OpportunityScore(
        keyword_id=kw.id,
        snapshot_date=date(2026, 4, 18),
        total_score=Decimal("87.50"),
        demand_score=Decimal("22.00"),
        growth_score=Decimal("18.00"),
        competition_score=Decimal("17.00"),
        customs_score=Decimal("18.50"),
        trend_score=Decimal("8.00"),
        stability_score=Decimal("4.00"),
        is_excluded=False,
    )
    db_session.add(score)
    db_session.flush()

    fetched = db_session.execute(
        select(OpportunityScore).where(OpportunityScore.keyword_id == kw.id)
    ).scalar_one()
    assert fetched.total_score == Decimal("87.50")
    assert fetched.is_excluded is False


# ---- Product / ProductScore / ChannelProfit chain -------------------------


def test_product_chain_cascades_on_delete(db_session: Session) -> None:
    kw = Keyword(term="고양이 자동급수기")
    db_session.add(kw)
    db_session.flush()

    product = Product(
        keyword_id=kw.id,
        url="https://1688.com/item.html?id=123",
        name="자동급수기",
        cny_price=Decimal("45.00"),
        moq=50,
    )
    db_session.add(product)
    db_session.flush()

    pscore = ProductScore(
        product_id=product.id,
        snapshot_date=date(2026, 4, 18),
        total_score=Decimal("83.00"),
        opportunity_score=Decimal("34.00"),
        profit_score=Decimal("28.00"),
        risk_score=Decimal("13.00"),
        stability_score=Decimal("8.00"),
        recommendation=Recommendation.GO,
    )
    db_session.add(pscore)
    db_session.flush()

    cp_smart = ChannelProfit(
        product_score_id=pscore.id,
        channel=Channel.SMARTSTORE,
        unit_cost_krw=Decimal("8200.00"),
        expected_price_krw=Decimal("38000.00"),
        platform_fee_pct=Decimal("5.500"),
        ad_cost_pct=Decimal("10.000"),
        unit_profit_krw=Decimal("24400.00"),
        margin_pct=Decimal("64.000"),
        roi_pct=Decimal("128.000"),
        breakeven_units=17,
    )
    cp_coupang = ChannelProfit(
        product_score_id=pscore.id,
        channel=Channel.COUPANG,
        unit_cost_krw=Decimal("8200.00"),
        expected_price_krw=Decimal("42000.00"),
        platform_fee_pct=Decimal("10.800"),
        ad_cost_pct=Decimal("15.000"),
        unit_profit_krw=Decimal("19100.00"),
        margin_pct=Decimal("50.000"),
        roi_pct=Decimal("98.000"),
        breakeven_units=21,
    )
    db_session.add_all([cp_smart, cp_coupang])
    db_session.flush()

    # Unique on (product_score_id, channel)
    sp = db_session.begin_nested()
    db_session.add(
        ChannelProfit(
            product_score_id=pscore.id,
            channel=Channel.SMARTSTORE,
            unit_cost_krw=Decimal("0"),
            expected_price_krw=Decimal("0"),
            platform_fee_pct=Decimal("0"),
            ad_cost_pct=Decimal("0"),
            unit_profit_krw=Decimal("0"),
            margin_pct=Decimal("0"),
            roi_pct=Decimal("0"),
            breakeven_units=0,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()

    # Cascade verification: deleting the product wipes scores + channel
    # profits (cascade chain products → product_scores → channel_profits).
    product_id = product.id
    db_session.delete(product)
    db_session.flush()

    remaining_scores = db_session.execute(
        select(ProductScore).where(ProductScore.product_id == product_id)
    ).scalars().all()
    assert remaining_scores == []
    remaining_cp = db_session.execute(select(ChannelProfit)).scalars().all()
    assert remaining_cp == []


# ---- Feedback -------------------------------------------------------------


def test_feedback_round_trip(db_session: Session) -> None:
    product = Product(url="https://1688.com/x", cny_price=Decimal("10"), moq=1)
    db_session.add(product)
    db_session.flush()

    fb = Feedback(
        product_id=product.id,
        purchased=True,
        monthly_sales=42,
        actual_revenue=Decimal("1234567.89"),
        notes="좋음",
    )
    db_session.add(fb)
    db_session.flush()
    db_session.refresh(fb)
    assert fb.id is not None
    assert fb.recorded_at is not None
    assert fb.purchased is True


# ---- CoupangFee -----------------------------------------------------------


def test_coupang_fee_unique(db_session: Session) -> None:
    eff = date(2026, 1, 1)
    db_session.add(
        CoupangFee(category_path="반려동물", fee_pct=Decimal("10.800"), effective_from=eff)
    )
    db_session.flush()
    sp = db_session.begin_nested()
    db_session.add(
        CoupangFee(category_path="반려동물", fee_pct=Decimal("11.000"), effective_from=eff)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()


# ---- ExchangeRate ---------------------------------------------------------


def test_exchange_rate_insert(db_session: Session) -> None:
    rate = ExchangeRate(currency_pair="CNY/KRW", rate=Decimal("190.123456"))
    db_session.add(rate)
    db_session.flush()
    db_session.refresh(rate)
    assert rate.id is not None
    assert rate.fetched_at is not None


# ---- ApiCache -------------------------------------------------------------


def test_api_cache_unique_key_and_jsonb(db_session: Session) -> None:
    expires = datetime.now(tz=timezone.utc) + timedelta(hours=24)
    cache = ApiCache(
        cache_key="coupang:search:고양이 자동급수기",
        response_json={"items": [{"id": 1}], "ts": "2026-04-18"},
        expires_at=expires,
    )
    db_session.add(cache)
    db_session.flush()

    sp = db_session.begin_nested()
    db_session.add(
        ApiCache(
            cache_key="coupang:search:고양이 자동급수기",
            response_json={"items": []},
            expires_at=expires,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    sp.rollback()
