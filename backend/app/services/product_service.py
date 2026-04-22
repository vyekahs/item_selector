"""Service layer for ``/products`` endpoints.

Three responsibilities:

1. Persist user-supplied 1688 products (``create_product_and_score``).
2. Hand the cost basis off to the Scoring Engine (deferred import) and
   persist the resulting ``product_scores`` + ``channel_profits`` rows.
3. Read-side helpers (``get_product_detail``, ``list_products``).

The Scoring Engine is owned by another agent. We isolate the dependency
behind a small ``Protocol`` and a ``_load_scorer()`` helper so:

* The route compiles even when ``app.scoring`` does not exist yet
  (``ScoringUnavailableError`` is raised at call time, not import time).
* Tests can inject a ``ProductScorer`` fake without needing to monkeypatch
  the real module.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Channel,
    ChannelProfit,
    ExchangeRate,
    Product,
    ProductScore,
    Recommendation,
)
from app.schemas.requests.product import ProductCreateRequest
from app.schemas.responses.product import (
    ChannelProfitResponse,
    PaginatedProductsResponse,
    ProductDetailResponse,
    ProductResponse,
    ProductScoreResponse,
)


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class ProductServiceError(RuntimeError):
    """Base for service-level (non-HTTP) errors."""


class ProductNotFoundError(ProductServiceError):
    pass


class DuplicateProductError(ProductServiceError):
    pass


class ScoringUnavailableError(ProductServiceError):
    """Raised when the Scoring Engine module is missing/unwired.

    Routers translate this into HTTP 503 so the frontend can show a
    "scoring engine not yet available" banner instead of a 500.
    """


# ---------------------------------------------------------------------
# Scoring Protocol -- owned by Scoring Engine agent
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class ScoringInput:
    """Inputs the scorer needs to compute a snapshot."""

    cny_price: Decimal
    moq: int
    cny_to_krw: Decimal
    keyword_id: int | None
    smartstore_fee_pct: Decimal = Decimal("0.055")
    smartstore_payment_pct: Decimal = Decimal("0.0374")
    smartstore_ad_pct: Decimal = Decimal("0.10")
    coupang_fee_pct: Decimal = Decimal("0.108")  # default = 반려동물
    coupang_ad_pct: Decimal = Decimal("0.15")
    # Expected KRW sell price. When None, the scorer falls back to the
    # 3× unit-cost heuristic. The service layer populates this from
    # ``keyword_metrics.shopping_avg_price_krw`` (Naver 쇼핑 API) when
    # the product is linked to a keyword.
    expected_sell_price_krw: int | None = None
    china_domestic_shipping_krw: int | None = None
    intl_shipping_krw: int | None = None
    customs_duty_pct: Decimal | None = None


@dataclass(frozen=True)
class ChannelProfitDraft:
    """One row destined for ``channel_profits`` (DB-shaped)."""

    channel: Channel
    unit_cost_krw: Decimal
    expected_price_krw: Decimal
    platform_fee_pct: Decimal
    ad_cost_pct: Decimal
    unit_profit_krw: Decimal
    margin_pct: Decimal
    roi_pct: Decimal
    breakeven_units: int


@dataclass(frozen=True)
class CostBreakdownDraft:
    """Channel-agnostic landed-cost decomposition shown on the detail page."""

    moq: int
    goods_cost_krw: int
    china_domestic_shipping_krw: int
    intl_shipping_krw: int
    cif_krw: int
    cif_usd_approx: float
    customs_duty_krw: int
    vat_krw: int
    filing_fee_krw: int
    mokrok_duty_free: bool
    total_cost_krw: int
    unit_cost_krw: int
    effective_duty_pct: float
    effective_vat_pct: float


@dataclass(frozen=True)
class ProductScoringResult:
    """What the scorer hands back to the service layer."""

    total_score: float
    opportunity_score: float
    profit_score: float
    risk_score: float
    stability_score: float
    recommendation: Recommendation
    channel_profits: list[ChannelProfitDraft]
    cost_breakdown: CostBreakdownDraft | None = None


@runtime_checkable
class ProductScorer(Protocol):
    def score(self, inputs: ScoringInput) -> ProductScoringResult: ...


# ---------------------------------------------------------------------
# Scorer loading (deferred / pluggable)
# ---------------------------------------------------------------------


def _load_scorer() -> ProductScorer:  # pragma: depends on scoring-engine-agent
    """Return a ``ProductScorer`` instance, importing lazily.

    Two lookup paths (first hit wins):

    1. ``app.scoring.product.DefaultProductScorer`` -- a ready-made
       scorer class (preferred if the Scoring agent ever ships one).
    2. The functional trio ``calculate_product_score`` +
       ``calculate_smartstore_revenue`` + ``calculate_coupang_revenue``,
       wrapped in a small adapter that satisfies
       :class:`ProductScorer`.

    If neither is importable, :class:`ScoringUnavailableError` bubbles up
    so the route returns a clean 503 instead of a 500.
    """
    try:  # pragma: no cover - import guarded
        from app.scoring.product import DefaultProductScorer  # type: ignore

        return DefaultProductScorer()  # type: ignore[no-any-return]
    except (ImportError, AttributeError):
        pass

    try:  # pragma: no cover - import guarded
        from app.scoring.functional_adapter import build_functional_scorer

        return build_functional_scorer()
    except (ImportError, AttributeError) as exc:
        raise ScoringUnavailableError(
            "Scoring Engine module not available "
            "(expected app.scoring.product.DefaultProductScorer or "
            "app.scoring.functional_adapter.build_functional_scorer)"
        ) from exc


# Test injection point.
_scorer_override: ProductScorer | None = None


def set_scorer_for_tests(scorer: ProductScorer | None) -> None:
    """Allow tests to inject a fake scorer without monkey-patching."""
    global _scorer_override
    _scorer_override = scorer


def _resolve_scorer() -> ProductScorer:
    if _scorer_override is not None:
        return _scorer_override
    return _load_scorer()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


_DEFAULT_CNY_KRW = Decimal("190.0")  # spec assumes ~¥45 → 8,200₩ unit cost.


def _latest_cny_krw(session: Session) -> Decimal:
    """Most recent CNY/KRW rate (falls back to a sane default)."""
    stmt = (
        select(ExchangeRate.rate)
        .where(ExchangeRate.currency_pair == "CNY/KRW")
        .order_by(desc(ExchangeRate.fetched_at))
        .limit(1)
    )
    rate = session.execute(stmt).scalar_one_or_none()
    if rate is None:
        return _DEFAULT_CNY_KRW
    return Decimal(str(rate))


def _lookup_one_rate(
    session: Session,
    method: str,
    total_weight_kg: Decimal,
    tier: str,
) -> int | None:
    from app.models import InternationalShippingRate

    row = session.execute(
        select(InternationalShippingRate)
        .where(
            InternationalShippingRate.method == method,
            InternationalShippingRate.max_weight_kg >= total_weight_kg,
        )
        .order_by(InternationalShippingRate.max_weight_kg.asc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    column = {
        "general": row.general_seller_krw,
        "super": row.super_seller_krw,
        "partner": row.partner_krw,
    }.get(tier, row.partner_krw)
    return int(column)


def _lookup_intl_shipping_krw(
    session: Session,
    method: str | None,
    total_weight_kg: Decimal,
    tier: str = "partner",
) -> tuple[int | None, str | None]:
    """Return ``(price_krw, applied_method)`` or ``(None, None)``.

    When ``method`` is None, pick whichever tier tier is cheaper at this
    weight. LCL and 해운(자가) rate tables are unevenly priced — LCL is
    often per-kg air-freight-style, 자가 is container-shared (cheaper for
    most weights). An explicit user-chosen method always wins.
    """
    if method in ("lcl", "sea_self"):
        price = _lookup_one_rate(session, method, total_weight_kg, tier)
        if price is not None:
            return (price, method)
        # Explicit choice out of range → fall back to the other.
        other = "sea_self" if method == "lcl" else "lcl"
        price = _lookup_one_rate(session, other, total_weight_kg, tier)
        return (price, other) if price is not None else (None, None)

    # Auto-pick: compare both methods, return the cheaper one.
    lcl_price = _lookup_one_rate(session, "lcl", total_weight_kg, tier)
    sea_price = _lookup_one_rate(session, "sea_self", total_weight_kg, tier)
    candidates = [
        (p, m) for p, m in [(lcl_price, "lcl"), (sea_price, "sea_self")] if p is not None
    ]
    if not candidates:
        return (None, None)
    price, chosen = min(candidates, key=lambda x: x[0])
    return (price, chosen)


def _resolve_intl_shipping(
    session: Session,
    product: "Product",
) -> tuple[int | None, str | None, Decimal | None]:
    """Return ``(intl_shipping_krw, applied_method, total_weight_kg)``.

    When product has explicit ``intl_shipping_krw`` override, that wins.
    Otherwise: need ``unit_weight_kg`` (either product-supplied or None).
    """
    # Priority: weight-based auto lookup (if both fields present) > explicit override.
    if product.unit_weight_kg is not None and product.unit_weight_kg > 0:
        total = Decimal(str(product.unit_weight_kg)) * Decimal(product.moq)
        # Empty ``shipping_method`` → auto-pick whichever tier is cheaper
        # at this weight (see _lookup_intl_shipping_krw).
        method = product.shipping_method or None
        price, applied = _lookup_intl_shipping_krw(session, method, total)
        if price is not None:
            return (price, applied, total)
    if product.intl_shipping_krw is not None:
        return (int(product.intl_shipping_krw), None, None)
    return (None, None, None)


def _lookup_duty_rates(
    session: Session, keyword_id: int | None
) -> tuple[Decimal | None, Decimal | None]:
    """Return ``(base_duty_pct, kcfta_duty_pct)`` for a keyword's first
    mapped HS code, or ``(None, None)`` when nothing matches.

    The 품목번호별 관세율표 is 10-digit; :func:`suggest_hs_codes`
    produces 6-digit suggestions so we match by ``LIKE '<6digits>%'``
    and take the first row (lowest ``id``).
    """
    if keyword_id is None:
        return (None, None)
    from app.models import CustomsDutyRate, KeywordHsMapping  # local
    from app.scoring import suggest_hs_codes

    # Prefer explicit DB mapping first.
    mapping_hs = session.execute(
        select(KeywordHsMapping.hs_code)
        .where(KeywordHsMapping.keyword_id == keyword_id)
        .order_by(KeywordHsMapping.confidence.desc())
        .limit(1)
    ).scalar_one_or_none()
    hs6: str | None = None
    if mapping_hs:
        hs6 = "".join(c for c in str(mapping_hs) if c.isdigit())[:6]
    if not hs6:
        # Fallback to static suggestions via keyword term.
        from app.models import Keyword

        kw = session.execute(
            select(Keyword).where(Keyword.id == keyword_id)
        ).scalar_one_or_none()
        if kw is None:
            return (None, None)
        cat_name = "반려동물용품"  # category name lookup is Phase-2
        suggestions = suggest_hs_codes(cat_name, kw.term)
        if not suggestions:
            return (None, None)
        hs6 = "".join(c for c in suggestions[0] if c.isdigit())[:6]
    if not hs6 or len(hs6) != 6:
        return (None, None)

    rate = session.execute(
        select(CustomsDutyRate.base_duty_pct, CustomsDutyRate.kcfta_duty_pct)
        .where(CustomsDutyRate.hs_code.like(f"{hs6}%"))
        .order_by(CustomsDutyRate.hs_code.asc())
        .limit(1)
    ).one_or_none()
    if rate is None:
        return (None, None)
    base, fta = rate
    return (
        Decimal(str(base)) if base is not None else None,
        Decimal(str(fta)) if fta is not None else None,
    )


def _latest_shopping_avg_price(
    session: Session, keyword_id: int | None
) -> int | None:
    """Most recent ``keyword_metrics.shopping_avg_price_krw`` for the
    keyword the product is linked to (Naver 쇼핑 평균가).

    ``None`` when no keyword or no metric snapshot yet -- the scorer
    will fall back to the 3× unit-cost heuristic in that case.
    """
    if keyword_id is None:
        return None
    from app.models import KeywordMetric  # local import to avoid cycles

    stmt = (
        select(KeywordMetric.shopping_avg_price_krw)
        .where(KeywordMetric.keyword_id == keyword_id)
        .order_by(desc(KeywordMetric.snapshot_date))
        .limit(1)
    )
    value = session.execute(stmt).scalar_one_or_none()
    if value is None or value <= 0:
        return None
    return int(value)


def _cost_breakdown_for(product: "Product", session: Session):
    """Re-compute the cost breakdown for ``product`` from stored inputs.

    We don't persist the breakdown — it's cheap to recompute deterministically
    from (cny_price, moq, exchange_rate). This keeps history reads simple
    and avoids a migration.
    """
    from decimal import Decimal as _D

    from app.scoring import RevenueInputs as _RevenueInputs, compute_cost_breakdown
    from app.schemas.responses.product import CostBreakdownResponse

    rate = _latest_cny_krw(session)
    # Resolve duty: user override > HS auto lookup > default 8%.
    base_auto, fta_auto = _lookup_duty_rates(session, product.keyword_id)
    if product.customs_duty_pct is not None:
        duty = _D(str(product.customs_duty_pct))
        source = "user_override"
    elif base_auto is not None:
        duty = base_auto
        source = "hs_lookup"
    else:
        duty = _D("0.08")
        source = "default_8pct"

    # Resolve sell price: user override > Naver avg > heuristic (unset here).
    naver_avg = _latest_shopping_avg_price(session, product.keyword_id)
    if product.expected_sell_price_krw is not None:
        current_sell = int(product.expected_sell_price_krw)
        sell_source = "user_override"
    elif naver_avg is not None:
        current_sell = naver_avg
        sell_source = "naver_avg"
    else:
        current_sell = None
        sell_source = "heuristic_3x"

    # Resolve intl shipping for display (auto by weight × method).
    auto_intl_price, applied_method, total_weight = _resolve_intl_shipping(
        session, product
    )
    bd = compute_cost_breakdown(
        _RevenueInputs(
            cny_price=_D(str(product.cny_price)),
            moq=product.moq,
            expected_sell_price_krw=1,
            category_name="default",
            exchange_rate=rate,
            china_domestic_shipping_krw=product.china_domestic_shipping_krw or 0,
            intl_shipping_krw=auto_intl_price,
            customs_duty_pct=duty,
            ad_cost_pct=_D("0.10"),
        )
    )
    return CostBreakdownResponse(
        moq=bd.moq,
        goods_cost_krw=bd.goods_cost_krw,
        china_domestic_shipping_krw=bd.china_domestic_shipping_krw,
        intl_shipping_krw=bd.intl_shipping_krw,
        cif_krw=bd.cif_krw,
        cif_usd_approx=bd.cif_usd_approx,
        customs_duty_krw=bd.customs_duty_krw,
        vat_krw=bd.vat_krw,
        filing_fee_krw=bd.filing_fee_krw,
        mokrok_duty_free=bd.mokrok_duty_free,
        total_cost_krw=bd.total_cost_krw,
        unit_cost_krw=bd.unit_cost_krw,
        effective_duty_pct=bd.effective_duty_pct,
        effective_vat_pct=bd.effective_vat_pct,
        suggested_base_duty_pct=float(base_auto) if base_auto is not None else None,
        suggested_kcfta_duty_pct=float(fta_auto) if fta_auto is not None else None,
        duty_source=source,
        exchange_rate_cny_krw=float(rate),
        expected_sell_price_krw=current_sell,
        naver_avg_price_krw=naver_avg,
        sell_price_source=sell_source,
        shipping_method_applied=applied_method,
        total_weight_kg=float(total_weight) if total_weight is not None else None,
        intl_shipping_source=(
            "rate_table"
            if applied_method is not None
            else (
                "user_override"
                if product.intl_shipping_krw is not None
                else ("auto_lookup" if auto_intl_price is not None else "default_per_unit")
            )
        ),
    )


def _serialise_score(score: ProductScore, session: Session | None = None) -> ProductScoreResponse:
    profits = [
        ChannelProfitResponse(
            channel=cp.channel.value if hasattr(cp.channel, "value") else str(cp.channel),  # type: ignore[arg-type]
            unit_cost_krw=float(cp.unit_cost_krw),
            expected_price_krw=float(cp.expected_price_krw),
            platform_fee_pct=float(cp.platform_fee_pct),
            ad_cost_pct=float(cp.ad_cost_pct),
            unit_profit_krw=float(cp.unit_profit_krw),
            margin_pct=float(cp.margin_pct),
            roi_pct=float(cp.roi_pct),
            breakeven_units=int(cp.breakeven_units),
        )
        for cp in sorted(score.channel_profits, key=lambda x: str(x.channel))
    ]
    recommended: str | None = None
    if profits:
        best = max(profits, key=lambda p: p.unit_profit_krw)
        recommended = best.channel
    breakdown = None
    if session is not None:
        try:
            product = score.product
            if product is None:
                # Fall back to explicit fetch when the relationship wasn't
                # eagerly loaded (e.g. score came from a fresh flush).
                product = session.execute(
                    select(Product).where(Product.id == score.product_id)
                ).scalar_one_or_none()
            if product is not None:
                breakdown = _cost_breakdown_for(product, session)
        except Exception as exc:  # pragma: no cover - debug aid
            import logging

            logging.getLogger(__name__).warning(
                "cost breakdown failed for product_id=%s: %r",
                score.product_id,
                exc,
            )
            breakdown = None
    return ProductScoreResponse(
        product_id=score.product_id,
        snapshot_date=score.snapshot_date,
        total_score=float(score.total_score),
        opportunity_score=float(score.opportunity_score),
        profit_score=float(score.profit_score),
        risk_score=float(score.risk_score),
        stability_score=float(score.stability_score),
        recommendation=score.recommendation.value
        if hasattr(score.recommendation, "value")
        else str(score.recommendation),  # type: ignore[arg-type]
        channel_profits=profits,
        recommended_channel=recommended,
        cost_breakdown=breakdown,
    )


def _serialise_product(
    product: Product,
    *,
    latest_score: ProductScore | None = None,
    session: Session | None = None,
) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        keyword_id=product.keyword_id,
        url=product.url,
        name=product.name,
        cny_price=float(product.cny_price),
        moq=int(product.moq),
        notes=product.notes,
        created_by_user=product.created_by_user,
        created_at=product.created_at,
        latest_score=_serialise_score(latest_score, session) if latest_score else None,
    )


# ---------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------


def create_product_and_score(
    session: Session,
    request: ProductCreateRequest,
    *,
    snapshot_date: dt.date | None = None,
) -> ProductScoreResponse:
    """Persist the input product, run the scorer, persist the snapshot.

    Raises:
        DuplicateProductError: A product with the same URL already exists.
        ScoringUnavailableError: Scoring Engine module not wired up yet.
    """
    url_str = str(request.url)
    existing_id = session.execute(
        select(Product.id).where(Product.url == url_str).limit(1)
    ).scalar_one_or_none()
    if existing_id is not None:
        raise DuplicateProductError(
            f"product with url={url_str!r} already exists (id={existing_id})"
        )

    product = Product(
        keyword_id=request.keyword_id,
        url=url_str,
        name=request.name,
        cny_price=request.cny_price,
        moq=request.moq,
        china_domestic_shipping_krw=getattr(
            request, "china_domestic_shipping_krw", None
        ),
        intl_shipping_krw=getattr(request, "intl_shipping_krw", None),
        customs_duty_pct=getattr(request, "customs_duty_pct", None),
        expected_sell_price_krw=getattr(request, "expected_sell_price_krw", None),
        ad_cost_pct=getattr(request, "ad_cost_pct", None),
        unit_weight_kg=getattr(request, "unit_weight_kg", None),
        shipping_method=getattr(request, "shipping_method", None),
        notes=request.notes,
        created_by_user=request.created_by_user,
    )
    session.add(product)
    session.flush()  # populate product.id

    snapshot = snapshot_date or dt.date.today()
    scorer = _resolve_scorer()
    duty_override = getattr(request, "customs_duty_pct", None)
    if duty_override is None:
        # Phase-B auto-lookup: 품목번호별 관세율표에서 base_duty_pct 적용.
        auto_base, _auto_fta = _lookup_duty_rates(session, request.keyword_id)
        auto_duty = auto_base
    else:
        auto_duty = Decimal(str(duty_override))

    sell_price_override = getattr(request, "expected_sell_price_krw", None)
    if sell_price_override is None:
        sell_price = _latest_shopping_avg_price(session, request.keyword_id)
    else:
        sell_price = int(sell_price_override)

    ad_override = getattr(request, "ad_cost_pct", None)
    ad_kwargs: dict = {}
    if ad_override is not None:
        ad_decimal = Decimal(str(ad_override))
        ad_kwargs = {
            "smartstore_ad_pct": ad_decimal,
            "coupang_ad_pct": ad_decimal,
        }

    # Resolve intl shipping: weight-based auto wins over stored manual override.
    intl_final, _m, _w = _resolve_intl_shipping(session, product)

    inputs = ScoringInput(
        cny_price=Decimal(str(request.cny_price)),
        moq=request.moq,
        cny_to_krw=_latest_cny_krw(session),
        keyword_id=request.keyword_id,
        expected_sell_price_krw=sell_price,
        china_domestic_shipping_krw=getattr(
            request, "china_domestic_shipping_krw", None
        ),
        intl_shipping_krw=intl_final,
        customs_duty_pct=auto_duty,
        **ad_kwargs,
    )
    result = scorer.score(inputs)

    score_row = ProductScore(
        product_id=product.id,
        snapshot_date=snapshot,
        total_score=result.total_score,
        opportunity_score=result.opportunity_score,
        profit_score=result.profit_score,
        risk_score=result.risk_score,
        stability_score=result.stability_score,
        recommendation=result.recommendation,
    )
    session.add(score_row)
    session.flush()

    for draft in result.channel_profits:
        session.add(
            ChannelProfit(
                product_score_id=score_row.id,
                channel=draft.channel,
                unit_cost_krw=draft.unit_cost_krw,
                expected_price_krw=draft.expected_price_krw,
                platform_fee_pct=draft.platform_fee_pct,
                ad_cost_pct=draft.ad_cost_pct,
                unit_profit_krw=draft.unit_profit_krw,
                margin_pct=draft.margin_pct,
                roi_pct=draft.roi_pct,
                breakeven_units=draft.breakeven_units,
            )
        )
    session.flush()
    session.commit()

    # Reload with eager profits for serialisation.
    persisted = session.execute(
        select(ProductScore)
        .options(selectinload(ProductScore.channel_profits))
        .where(ProductScore.id == score_row.id)
    ).scalar_one()
    return _serialise_score(persisted, session)


def update_product_costs(
    session: Session,
    product_id: int,
    request,  # ProductUpdateRequest
    *,
    snapshot_date: dt.date | None = None,
) -> ProductScoreResponse:
    """Apply cost overrides from the user and upsert today's score snapshot.

    Unlike :func:`create_product_and_score`, this replaces today's score
    row (ON CONFLICT) so the UI reflects the adjustment immediately
    without creating score history churn.
    """
    product = session.execute(
        select(Product).where(Product.id == product_id)
    ).scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError(f"product id={product_id} not found")

    if request.moq is not None:
        product.moq = request.moq
    if request.china_domestic_shipping_krw is not None:
        product.china_domestic_shipping_krw = request.china_domestic_shipping_krw
    if request.intl_shipping_krw is not None:
        product.intl_shipping_krw = request.intl_shipping_krw
    if request.customs_duty_pct is not None:
        product.customs_duty_pct = request.customs_duty_pct
    if request.expected_sell_price_krw is not None:
        product.expected_sell_price_krw = request.expected_sell_price_krw
    if request.ad_cost_pct is not None:
        product.ad_cost_pct = request.ad_cost_pct
    if request.unit_weight_kg is not None:
        product.unit_weight_kg = request.unit_weight_kg
        if request.unit_weight_kg > 0:
            product.intl_shipping_krw = None
    if request.shipping_method is not None:
        product.shipping_method = request.shipping_method or None

    session.flush()

    snapshot = snapshot_date or dt.date.today()
    scorer = _resolve_scorer()
    duty = product.customs_duty_pct
    if duty is None:
        auto_base, _auto_fta = _lookup_duty_rates(session, product.keyword_id)
        duty = auto_base
    sell_price = product.expected_sell_price_krw
    if sell_price is None:
        sell_price = _latest_shopping_avg_price(session, product.keyword_id)
    ad_kwargs2: dict = {}
    if product.ad_cost_pct is not None:
        ad_d = Decimal(str(product.ad_cost_pct))
        ad_kwargs2 = {"smartstore_ad_pct": ad_d, "coupang_ad_pct": ad_d}
    intl, _m, _w = _resolve_intl_shipping(session, product)
    inputs = ScoringInput(
        cny_price=Decimal(str(product.cny_price)),
        moq=product.moq,
        cny_to_krw=_latest_cny_krw(session),
        keyword_id=product.keyword_id,
        expected_sell_price_krw=sell_price,
        china_domestic_shipping_krw=product.china_domestic_shipping_krw,
        intl_shipping_krw=intl,
        customs_duty_pct=Decimal(str(duty)) if duty is not None else None,
        **ad_kwargs2,
    )
    result = scorer.score(inputs)

    # Upsert today's snapshot (delete existing first for simplicity so
    # channel_profits cascade out cleanly).
    existing = session.execute(
        select(ProductScore)
        .where(
            ProductScore.product_id == product.id,
            ProductScore.snapshot_date == snapshot,
        )
    ).scalar_one_or_none()
    if existing is not None:
        session.delete(existing)
        session.flush()

    score_row = ProductScore(
        product_id=product.id,
        snapshot_date=snapshot,
        total_score=result.total_score,
        opportunity_score=result.opportunity_score,
        profit_score=result.profit_score,
        risk_score=result.risk_score,
        stability_score=result.stability_score,
        recommendation=result.recommendation,
    )
    session.add(score_row)
    session.flush()

    for draft in result.channel_profits:
        session.add(
            ChannelProfit(
                product_score_id=score_row.id,
                channel=draft.channel,
                unit_cost_krw=draft.unit_cost_krw,
                expected_price_krw=draft.expected_price_krw,
                platform_fee_pct=draft.platform_fee_pct,
                ad_cost_pct=draft.ad_cost_pct,
                unit_profit_krw=draft.unit_profit_krw,
                margin_pct=draft.margin_pct,
                roi_pct=draft.roi_pct,
                breakeven_units=draft.breakeven_units,
            )
        )
    session.commit()

    persisted = session.execute(
        select(ProductScore)
        .options(selectinload(ProductScore.channel_profits))
        .where(ProductScore.id == score_row.id)
    ).scalar_one()
    return _serialise_score(persisted, session)


def get_product_detail(session: Session, product_id: int) -> ProductDetailResponse:
    product = session.execute(
        select(Product)
        .options(selectinload(Product.scores).selectinload(ProductScore.channel_profits))
        .where(Product.id == product_id)
    ).scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError(f"product id={product_id} not found")

    history_rows = sorted(product.scores, key=lambda s: s.snapshot_date, reverse=True)
    history = [_serialise_score(s, session) for s in history_rows]
    latest = history_rows[0] if history_rows else None
    base = _serialise_product(product, latest_score=latest, session=session)
    return ProductDetailResponse(
        **base.model_dump(),
        score_history=history,
    )


def list_products(
    session: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    keyword_id: int | None = None,
) -> PaginatedProductsResponse:
    if limit <= 0 or limit > 200:
        raise ValueError("limit must be in 1..200")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    base_count = select(func.count()).select_from(Product)
    base_list = (
        select(Product)
        .options(
            selectinload(Product.scores).selectinload(ProductScore.channel_profits)
        )
        .order_by(desc(Product.created_at))
    )
    if keyword_id is not None:
        base_count = base_count.where(Product.keyword_id == keyword_id)
        base_list = base_list.where(Product.keyword_id == keyword_id)

    total = session.execute(base_count).scalar_one()
    products = (
        session.execute(base_list.limit(limit).offset(offset)).scalars().all()
    )

    items: list[ProductResponse] = []
    for product in products:
        latest = max(product.scores, key=lambda s: s.snapshot_date, default=None)
        items.append(_serialise_product(product, latest_score=latest))

    return PaginatedProductsResponse(
        items=items,
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )
