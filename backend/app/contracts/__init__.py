"""Shared DTO contracts between the three agents.

This package is the single source of truth for the interchange types used
between Data Collection, Scoring Engine and Backend API agents. Importers
should **only** depend on names exported here — concrete clients are free
to reshape their internal representations, but the DTO surface must stay
wire-stable.
"""
from __future__ import annotations

from .dto import (
    BlogCafeDTO,
    Channel,
    CoupangProductDTO,
    CoupangSearchDTO,
    CustomsImportDTO,
    CustomsTrendDTO,
    ExchangeRateDTO,
    GoogleTrendDTO,
    HsCodeDTO,
    KeywordVolumeDTO,
    NaverTrendDTO,
    Recommendation,
    ShoppingItem,
    ShoppingResultDTO,
    TrendPoint,
    YouTubeSignalDTO,
)

__all__ = [
    "BlogCafeDTO",
    "Channel",
    "CoupangProductDTO",
    "CoupangSearchDTO",
    "CustomsImportDTO",
    "CustomsTrendDTO",
    "ExchangeRateDTO",
    "GoogleTrendDTO",
    "HsCodeDTO",
    "KeywordVolumeDTO",
    "NaverTrendDTO",
    "Recommendation",
    "ShoppingItem",
    "ShoppingResultDTO",
    "TrendPoint",
    "YouTubeSignalDTO",
]
