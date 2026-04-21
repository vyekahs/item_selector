"""Real client stub tests.

Each ``Real*Client`` must:

1. Be instantiable without API keys (so unit tests can construct it).
2. Satisfy its module's ``*ClientProtocol`` (structural check).
3. Raise a clear :class:`AuthError` — *not* a cryptic ``KeyError``
   or ``HTTP 401`` — when :meth:`fetch` is called without credentials.

When ``USE_MOCK_CLIENTS=false`` the factory must dispatch to the real
client.
"""
from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

import pytest

from app.clients.base import AuthError
from app.clients.coupang_partners import (
    CoupangPartnersClientProtocol,
    RealCoupangPartnersClient,
    get_coupang_partners_client,
)
from app.clients.customs import (
    CustomsClientProtocol,
    RealCustomsClient,
    get_customs_client,
)
from app.clients.exchange_rate import (
    ExchangeRateClientProtocol,
    RealExchangeRateClient,
    get_exchange_rate_client,
)
from app.clients.google_trends import (
    GoogleTrendsClientProtocol,
    RealGoogleTrendsClient,
    get_google_trends_client,
)
from app.clients.hs_code import (
    DbHsCodeClient,
    HsCodeClientProtocol,
    get_hs_code_client,
)
from app.clients.naver_blogcafe import (
    NaverBlogCafeClientProtocol,
    RealNaverBlogCafeClient,
    get_naver_blogcafe_client,
)
from app.clients.naver_datalab import (
    NaverDataLabClientProtocol,
    RealNaverDataLabClient,
    get_naver_datalab_client,
)
from app.clients.naver_searchad import (
    NaverSearchAdClientProtocol,
    RealNaverSearchAdClient,
    get_naver_searchad_client,
)
from app.clients.naver_shopping import (
    NaverShoppingClientProtocol,
    RealNaverShoppingClient,
    get_naver_shopping_client,
)
from app.clients.youtube import (
    RealYouTubeClient,
    YouTubeClientProtocol,
    get_youtube_client,
)


def _run(coro):
    return asyncio.run(coro)


# ---- instantiation without keys ------------------------------------


@pytest.fixture(autouse=True)
def _clear_api_keys(monkeypatch):
    """Strip every API key env var so AuthError is reliably raised."""
    for key in [
        "NAVER_SEARCHAD_API_KEY",
        "NAVER_SEARCHAD_SECRET_KEY",
        "NAVER_SEARCHAD_CUSTOMER_ID",
        "NAVER_OPENAPI_CLIENT_ID",
        "NAVER_OPENAPI_CLIENT_SECRET",
        "COUPANG_ACCESS_KEY",
        "COUPANG_SECRET_KEY",
        "CUSTOMS_API_KEY",
        "HS_CODE_API_KEY",
        "EXIM_API_KEY",
        "EXIM_BANK_API_KEY",
        "YOUTUBE_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_real_clients_instantiate_without_keys():
    RealNaverSearchAdClient()
    RealNaverDataLabClient()
    RealNaverShoppingClient()
    RealNaverBlogCafeClient()
    RealCoupangPartnersClient()
    RealCustomsClient()
    # HS codes are loaded from a local file → DB, no API key needed.
    DbHsCodeClient(session_factory=lambda: None)
    RealExchangeRateClient()
    RealYouTubeClient()
    RealGoogleTrendsClient()


# ---- factory dispatches to Real* when mocks disabled ---------------


def test_factories_return_real_when_mocks_disabled(monkeypatch):
    monkeypatch.setenv("USE_MOCK_CLIENTS", "false")
    assert isinstance(get_naver_searchad_client(), RealNaverSearchAdClient)
    assert isinstance(get_naver_datalab_client(), RealNaverDataLabClient)
    assert isinstance(get_naver_shopping_client(), RealNaverShoppingClient)
    assert isinstance(get_naver_blogcafe_client(), RealNaverBlogCafeClient)
    assert isinstance(get_coupang_partners_client(), RealCoupangPartnersClient)
    assert isinstance(get_customs_client(), RealCustomsClient)
    assert isinstance(get_hs_code_client(), DbHsCodeClient)
    assert isinstance(get_exchange_rate_client(), RealExchangeRateClient)
    assert isinstance(get_youtube_client(), RealYouTubeClient)
    assert isinstance(get_google_trends_client(), RealGoogleTrendsClient)


# ---- fetch without credentials raises AuthError --------------------


@pytest.mark.parametrize(
    "client_factory, call_kwargs",
    [
        (RealNaverSearchAdClient, {"keywords": ["x"]}),
        (RealNaverDataLabClient, {"keyword_groups": [["x"]]}),
        (RealNaverShoppingClient, {"query": "x"}),
        (RealNaverBlogCafeClient, {"term": "x"}),
        (RealCoupangPartnersClient, {"query": "x"}),
        (RealCustomsClient, {"hs_code": "841451"}),
        # HS code: no key required (file-based) — covered by a separate test.
        (RealExchangeRateClient, {"currency_pair": "CNY/KRW"}),
        (RealYouTubeClient, {"term": "x"}),
    ],
)
def test_real_client_fetch_without_keys_raises_auth_error(client_factory, call_kwargs):
    client = client_factory()
    with pytest.raises(AuthError):
        _run(client.fetch(**call_kwargs))


def test_google_trends_real_stub_raises_not_implemented():
    # pytrends doesn't need an API key — the stub still isn't wired.
    client = RealGoogleTrendsClient()
    with pytest.raises(NotImplementedError):
        _run(client.fetch("x"))


# ---- structural Protocol satisfaction ------------------------------


@runtime_checkable
class _HasAsyncFetch(Protocol):
    async def fetch(self, *args, **kwargs): ...  # noqa: E501


def test_real_clients_satisfy_has_async_fetch():
    """Guard against accidentally deleting a ``fetch`` method."""
    for client in [
        RealNaverSearchAdClient(),
        RealNaverDataLabClient(),
        RealNaverShoppingClient(),
        RealNaverBlogCafeClient(),
        RealCoupangPartnersClient(),
        RealCustomsClient(),
        DbHsCodeClient(session_factory=lambda: None),
        RealExchangeRateClient(),
        RealYouTubeClient(),
        RealGoogleTrendsClient(),
    ]:
        assert isinstance(client, _HasAsyncFetch)
