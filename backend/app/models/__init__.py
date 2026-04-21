"""SQLAlchemy ORM models for itemSelector.

Import every model module here so ``Base.metadata`` is populated
whenever anything imports :mod:`app.models`. Alembic ``env.py`` relies
on this to see the full schema.
"""
from __future__ import annotations

from .api_cache import ApiCache
from .category import Category
from .channel_profit import Channel, ChannelProfit
from .coupang_fee import CoupangFee
from .customs_duty_rate import CustomsDutyRate
from .exchange_rate import ExchangeRate
from .feedback import Feedback
from .hs_code import HsCode
from .import_stat import ImportStat
from .intl_shipping_rate import InternationalShippingRate
from .keyword import Keyword, KeywordStatus
from .keyword_hs_mapping import KeywordHsMapping
from .keyword_metric import KeywordMetric
from .opportunity_score import OpportunityScore
from .product import Product
from .product_score import ProductScore, Recommendation

__all__ = [
    "ApiCache",
    "Category",
    "Channel",
    "ChannelProfit",
    "CoupangFee",
    "CustomsDutyRate",
    "ExchangeRate",
    "Feedback",
    "HsCode",
    "ImportStat",
    "InternationalShippingRate",
    "Keyword",
    "KeywordHsMapping",
    "KeywordMetric",
    "KeywordStatus",
    "OpportunityScore",
    "Product",
    "ProductScore",
    "Recommendation",
]
