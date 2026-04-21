"""External API client layer for itemSelector.

Each sub-module exposes:

* A ``Protocol`` defining the client's public surface.
* A ``Mock*Client`` implementation backed by sample JSON fixtures in
  ``app/clients/mocks/``. This is the default when ``USE_MOCK_CLIENTS``
  is truthy (or unset).
* A ``Real*Client`` stub whose ``fetch(...)`` coroutine raises a clear
  ``NotImplementedError`` or :class:`~app.clients.base.AuthError`.
  It will be fleshed out once the corresponding API keys are issued.
* A ``get_*_client()`` factory that honours the ``USE_MOCK_CLIENTS``
  environment variable.

Downstream agents (Scoring, Scheduler, Backend API) should only import
the factory + the DTOs from :mod:`app.contracts.dto` -- never the
concrete classes.
"""
from __future__ import annotations

# Re-export the contract DTOs for ergonomic importing -- but the DTOs
# themselves *live* in ``app.contracts.dto`` and that module is the
# single source of truth.
from app.contracts.dto import (
    BlogCafeDTO,
    CoupangProductDTO,
    CoupangSearchDTO,
    CustomsImportDTO,
    CustomsTrendDTO,
    ExchangeRateDTO,
    GoogleTrendDTO,
    HsCodeDTO,
    KeywordVolumeDTO,
    NaverTrendDTO,
    ShoppingItem,
    ShoppingResultDTO,
    YouTubeSignalDTO,
)

from .base import (
    ApiError,
    AuthError,
    BaseApiClient,
    RateLimitError,
    use_mock_clients,
)
from .coupang_partners import (
    CoupangPartnersClientProtocol,
    get_coupang_partners_client,
)
from .customs import CustomsClientProtocol, get_customs_client
from .exchange_rate import (
    ExchangeRateClientProtocol,
    HybridExchangeRateClient,
    get_exchange_rate_client,
)
from .google_trends import GoogleTrendsClientProtocol, get_google_trends_client
from .google_translate import (
    GoogleTranslateClientProtocol,
    get_google_translate_client,
)
from .hs_code import HsCodeClientProtocol, get_hs_code_client
from .naver_blogcafe import (
    NaverBlogCafeClientProtocol,
    get_naver_blogcafe_client,
)
from .naver_datalab import (
    NaverDataLabClientProtocol,
    get_naver_datalab_client,
)
from .naver_searchad import (
    NaverSearchAdClientProtocol,
    get_naver_searchad_client,
)
from .naver_shopping import (
    NaverShoppingClientProtocol,
    get_naver_shopping_client,
)
from .youtube import YouTubeClientProtocol, get_youtube_client

__all__ = [
    # base
    "ApiError",
    "AuthError",
    "BaseApiClient",
    "RateLimitError",
    "use_mock_clients",
    # factories
    "get_coupang_partners_client",
    "get_customs_client",
    "get_exchange_rate_client",
    "get_google_trends_client",
    "GoogleTranslateClientProtocol",
    "get_google_translate_client",
    "get_hs_code_client",
    "get_naver_blogcafe_client",
    "get_naver_datalab_client",
    "get_naver_searchad_client",
    "get_naver_shopping_client",
    "get_youtube_client",
    # extras
    "HybridExchangeRateClient",
    # protocols
    "CoupangPartnersClientProtocol",
    "CustomsClientProtocol",
    "ExchangeRateClientProtocol",
    "GoogleTrendsClientProtocol",
    "HsCodeClientProtocol",
    "NaverBlogCafeClientProtocol",
    "NaverDataLabClientProtocol",
    "NaverSearchAdClientProtocol",
    "NaverShoppingClientProtocol",
    "YouTubeClientProtocol",
    # DTOs (re-exported from app.contracts.dto)
    "BlogCafeDTO",
    "CoupangProductDTO",
    "CoupangSearchDTO",
    "CustomsImportDTO",
    "CustomsTrendDTO",
    "ExchangeRateDTO",
    "GoogleTrendDTO",
    "HsCodeDTO",
    "KeywordVolumeDTO",
    "NaverTrendDTO",
    "ShoppingItem",
    "ShoppingResultDTO",
    "YouTubeSignalDTO",
]
