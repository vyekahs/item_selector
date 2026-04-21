"""Concrete :class:`~app.scheduler.base.ScheduledJob` implementations.

Each module owns one pipeline stage:

* :mod:`.collect_keywords` — seed + related keyword expansion.
* :mod:`.collect_metrics`  — per-keyword Naver signals (DataLab,
  쇼핑, 블로그/카페).
* :mod:`.collect_customs`  — HS-code level 관세청 import statistics.
* :mod:`.collect_coupang`  — Coupang Partners refresh (10 req/hr).
* :mod:`.collect_exchange_rate` — CNY→KRW (and friends) cache.
* :mod:`.recalculate_opportunities` — composite scoring from the
  collected signals.
"""
from __future__ import annotations

from .collect_coupang import CollectCoupangJob
from .collect_customs import CollectCustomsJob
from .collect_exchange_rate import CollectExchangeRateJob
from .collect_keywords import CollectKeywordsJob
from .collect_metrics import CollectMetricsJob
from .fill_missing_signals import FillMissingSignalsJob
from .recalculate_opportunities import RecalculateOpportunitiesJob
from .translate_keywords import TranslateKeywordsJob

__all__ = [
    "CollectCoupangJob",
    "CollectCustomsJob",
    "CollectExchangeRateJob",
    "CollectKeywordsJob",
    "CollectMetricsJob",
    "FillMissingSignalsJob",
    "RecalculateOpportunitiesJob",
    "TranslateKeywordsJob",
]
