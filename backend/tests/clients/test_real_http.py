"""Real client HTTP-transport tests.

Each ``Real*Client`` implements ``fetch(...)`` via ``httpx.AsyncClient``.
We mock the outbound HTTP calls with ``respx`` so these tests never
touch the upstream services. Two scenarios per client: one happy-path
that should return a well-formed DTO, and one error-path (401 / 4xx)
that should raise :class:`AuthError` / :class:`ApiError`.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import respx

from app.clients.base import ApiError, AuthError
from app.clients.customs import RealCustomsClient
from app.clients.exchange_rate import RealExchangeRateClient
from app.clients.naver_blogcafe import RealNaverBlogCafeClient
from app.clients.naver_datalab import RealNaverDataLabClient
from app.clients.naver_shopping import RealNaverShoppingClient
from app.clients.youtube import RealYouTubeClient
from app.contracts.dto import (
    BlogCafeDTO,
    CustomsTrendDTO,
    ExchangeRateDTO,
    NaverTrendDTO,
    ShoppingResultDTO,
    YouTubeSignalDTO,
)


def _run(coro):
    return asyncio.run(coro)


# ---- NaverDataLab ---------------------------------------------------


def _datalab_ok_payload():
    # Two years of monthly data so 3/6/12m growth rates can all resolve.
    data = []
    for year in (2024, 2025):
        for month in range(1, 13):
            data.append(
                {
                    "period": f"{year}-{month:02d}-01",
                    "ratio": float(10 + month + (year - 2024) * 24),
                }
            )
    return {
        "startDate": "2024-01-01",
        "endDate": "2025-12-31",
        "timeUnit": "month",
        "results": [
            {
                "title": "휴대용선풍기",
                "keywords": ["휴대용선풍기"],
                "data": data,
            }
        ],
    }


def test_naver_datalab_real_success():
    client = RealNaverDataLabClient(client_id="id", client_secret="secret")
    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://openapi.naver.com/v1/datalab/search").mock(
            return_value=httpx.Response(200, json=_datalab_ok_payload())
        )
        result = _run(client.fetch([["휴대용선풍기"]]))

    assert route.called
    assert len(result) == 1
    dto = result[0]
    assert isinstance(dto, NaverTrendDTO)
    assert dto.term == "휴대용선풍기"
    assert len(dto.points) == 24
    # growth rates are percent-units (not decimals).
    assert dto.growth_rate_12m != 0.0

    # Sanity-check that headers + JSON body were set properly.
    sent = route.calls.last.request
    assert sent.headers["X-Naver-Client-Id"] == "id"
    assert sent.headers["X-Naver-Client-Secret"] == "secret"
    assert b"keywordGroups" in sent.content


def test_naver_datalab_real_auth_error():
    client = RealNaverDataLabClient(client_id="id", client_secret="secret")
    with respx.mock() as router:
        router.post("https://openapi.naver.com/v1/datalab/search").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )
        with pytest.raises(AuthError):
            _run(client.fetch([["x"]]))


def test_naver_datalab_real_http_error():
    client = RealNaverDataLabClient(client_id="id", client_secret="secret")
    with respx.mock() as router:
        router.post("https://openapi.naver.com/v1/datalab/search").mock(
            return_value=httpx.Response(400, text="bad request")
        )
        with pytest.raises(ApiError):
            _run(client.fetch([["x"]]))


# ---- NaverShopping --------------------------------------------------


def _shopping_payload():
    return {
        "total": 42,
        "start": 1,
        "display": 3,
        "items": [
            {
                "title": "<b>휴대용</b> 선풍기",
                "lprice": "12900",
                "mallName": "몰A",
                "productId": "1",
                "brand": "브랜드",
                "category1": "디지털/가전",
            },
            {
                "title": "미니 선풍기",
                "lprice": "9800",
                "mallName": "몰B",
                "productId": "2",
            },
            {
                "title": "탁상용 선풍기",
                "lprice": "15000",
                "mallName": "몰C",
                "productId": "3",
            },
        ],
    }


def test_naver_shopping_real_success():
    client = RealNaverShoppingClient(client_id="id", client_secret="secret")
    with respx.mock() as router:
        route = router.get("https://openapi.naver.com/v1/search/shop.json").mock(
            return_value=httpx.Response(200, json=_shopping_payload())
        )
        dto = _run(client.fetch("선풍기", display=50))

    assert route.called
    sent = route.calls.last.request
    assert sent.headers["X-Naver-Client-Id"] == "id"
    # query is URL-encoded; just verify the key is present.
    assert "query=" in str(sent.url)
    assert "display=50" in str(sent.url)

    assert isinstance(dto, ShoppingResultDTO)
    assert dto.query == "선풍기"
    assert dto.total_count == 42
    assert len(dto.items) == 3
    assert dto.items[0].title == "휴대용 선풍기"  # <b> stripped
    assert dto.avg_price > 0


def test_naver_shopping_real_auth_error():
    client = RealNaverShoppingClient(client_id="id", client_secret="secret")
    with respx.mock() as router:
        router.get("https://openapi.naver.com/v1/search/shop.json").mock(
            return_value=httpx.Response(403, text="forbidden")
        )
        with pytest.raises(AuthError):
            _run(client.fetch("x"))


# ---- NaverBlogCafe --------------------------------------------------


def test_naver_blogcafe_real_success():
    client = RealNaverBlogCafeClient(client_id="id", client_secret="secret")
    today = date.today()
    recent = (today - timedelta(days=5)).strftime("%Y%m%d")
    old = (today - timedelta(days=45)).strftime("%Y%m%d")

    blog_payload = {
        "total": 1234,
        "items": [
            {"postdate": recent, "title": "a"},
            {"postdate": recent, "title": "b"},
            {"postdate": old, "title": "c"},
        ],
    }
    cafe_payload = {"total": 567, "items": []}

    with respx.mock() as router:
        blog_route = router.get(
            "https://openapi.naver.com/v1/search/blog.json"
        ).mock(return_value=httpx.Response(200, json=blog_payload))
        cafe_route = router.get(
            "https://openapi.naver.com/v1/search/cafearticle.json"
        ).mock(return_value=httpx.Response(200, json=cafe_payload))
        dto = _run(client.fetch("휴대용선풍기"))

    assert blog_route.called
    assert cafe_route.called
    assert isinstance(dto, BlogCafeDTO)
    assert dto.blog_post_count == 1234
    assert dto.cafe_post_count == 567
    assert dto.recent_30d_blog_count == 2


def test_naver_blogcafe_real_http_error():
    client = RealNaverBlogCafeClient(client_id="id", client_secret="secret")
    # ``asyncio.gather`` may cancel the sibling coroutine once the blog
    # call fails, so relax ``assert_all_called`` — we only care that the
    # failure propagates.
    with respx.mock(assert_all_called=False) as router:
        router.get("https://openapi.naver.com/v1/search/blog.json").mock(
            return_value=httpx.Response(500, text="server error")
        )
        router.get("https://openapi.naver.com/v1/search/cafearticle.json").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )
        with pytest.raises(ApiError):
            _run(client.fetch("x"))


# ---- Customs --------------------------------------------------------


def _customs_payload(items):
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {
                "items": {"item": items},
                "numOfRows": 100,
                "pageNo": 1,
                "totalCount": len(items) if isinstance(items, list) else 1,
            },
        }
    }


def test_customs_real_success_list():
    client = RealCustomsClient(service_key="sk")
    items = []
    # 15 months of data so 12m window has > 2x coverage.
    for month in range(1, 16):
        items.append(
            {
                "hsSgn": "841451",
                "statCd": "CN",
                "statMonth": f"2024{month:02d}" if month <= 12 else f"2025{month - 12:02d}",
                "expDlr": "0",
                "impDlr": str(1000 * month),
                "impWgt": str(100 * month),
            }
        )
    with respx.mock() as router:
        route = router.get(
            "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
        ).mock(return_value=httpx.Response(200, json=_customs_payload(items)))
        dto = _run(client.fetch("841451", country_code="CN", months=6))

    assert route.called
    assert isinstance(dto, CustomsTrendDTO)
    assert dto.hs_code == "841451"
    assert dto.country_code == "CN"
    assert len(dto.points) == 6  # sliced to requested window
    assert dto.growth_rate_3m > 0  # monotonic increase


def test_customs_real_success_single_dict():
    """Upstream collapses ``item`` to a dict when there's exactly one record.

    The client issues **two** windowed requests to get 24 months of
    coverage; we respond with the record on the first call and an empty
    envelope on the second so aggregation does not double-count.
    """
    client = RealCustomsClient(service_key="sk")
    single = {
        "hsSgn": "841451",
        "statCd": "CN",
        "statMonth": "202501",
        "expDlr": "0",
        "impDlr": "1200",
        "impWgt": "10",
    }
    empty = {"response": {"body": {}}}
    with respx.mock() as router:
        router.get(
            "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
        ).mock(
            side_effect=[
                httpx.Response(200, json=_customs_payload(single)),
                httpx.Response(200, json=empty),
            ]
        )
        dto = _run(client.fetch("841451"))

    assert len(dto.points) == 1
    assert dto.points[0].import_value_usd == Decimal("1200")


def test_customs_real_auth_error():
    client = RealCustomsClient(service_key="sk")
    with respx.mock() as router:
        router.get(
            "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
        ).mock(return_value=httpx.Response(401, text="unauthorized"))
        with pytest.raises(AuthError):
            _run(client.fetch("841451"))


# ---- ExchangeRate ---------------------------------------------------


def test_exchange_rate_real_success_cny():
    client = RealExchangeRateClient(auth_key="k")
    payload = [
        {"result": 1, "cur_unit": "USD", "deal_bas_r": "1,384.00"},
        {"result": 1, "cur_unit": "CNH", "deal_bas_r": "191.33"},
    ]
    with respx.mock() as router:
        route = router.get(
            "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
        ).mock(return_value=httpx.Response(200, json=payload))
        dto = _run(client.fetch("CNY/KRW"))

    assert route.called
    assert isinstance(dto, ExchangeRateDTO)
    assert dto.currency_pair == "CNY/KRW"
    assert dto.rate == Decimal("191.33")


def test_exchange_rate_real_walks_back_on_weekend():
    """Empty list → advance to the previous day until one returns data."""
    client = RealExchangeRateClient(auth_key="k")
    responses = [
        httpx.Response(200, json=[]),
        httpx.Response(200, json=[]),
        httpx.Response(
            200,
            json=[{"result": 1, "cur_unit": "CNH", "deal_bas_r": "190.10"}],
        ),
    ]
    with respx.mock() as router:
        route = router.get(
            "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
        ).mock(side_effect=responses)
        dto = _run(client.fetch("CNY/KRW"))

    assert route.call_count == 3
    assert dto.rate == Decimal("190.10")


def test_exchange_rate_real_http_error():
    client = RealExchangeRateClient(auth_key="k")
    with respx.mock() as router:
        router.get(
            "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
        ).mock(return_value=httpx.Response(401, text="bad key"))
        with pytest.raises(AuthError):
            _run(client.fetch("CNY/KRW"))


# ---- YouTube --------------------------------------------------------


def _youtube_search_payload():
    now = datetime.now(tz=timezone.utc)
    recent = (now - timedelta(days=3)).isoformat().replace("+00:00", "Z")
    older = (now - timedelta(days=45)).isoformat().replace("+00:00", "Z")
    return {
        "pageInfo": {"totalResults": 7820, "resultsPerPage": 3},
        "items": [
            {
                "id": {"kind": "youtube#video", "videoId": "a1"},
                "snippet": {"publishedAt": recent, "title": "a"},
            },
            {
                "id": {"kind": "youtube#video", "videoId": "a2"},
                "snippet": {"publishedAt": recent, "title": "b"},
            },
            {
                "id": {"kind": "youtube#video", "videoId": "a3"},
                "snippet": {"publishedAt": older, "title": "c"},
            },
        ],
    }


def _youtube_videos_payload():
    return {
        "items": [
            {"id": "a1", "statistics": {"viewCount": "1000"}},
            {"id": "a2", "statistics": {"viewCount": "2000"}},
            {"id": "a3", "statistics": {"viewCount": "3000"}},
        ]
    }


def test_youtube_real_success():
    client = RealYouTubeClient(api_key="k")
    with respx.mock() as router:
        search_route = router.get(
            "https://www.googleapis.com/youtube/v3/search"
        ).mock(return_value=httpx.Response(200, json=_youtube_search_payload()))
        videos_route = router.get(
            "https://www.googleapis.com/youtube/v3/videos"
        ).mock(return_value=httpx.Response(200, json=_youtube_videos_payload()))
        dto = _run(client.fetch("휴대용선풍기"))

    assert search_route.called
    assert videos_route.called
    assert isinstance(dto, YouTubeSignalDTO)
    assert dto.total_video_count == 7820
    # 2 of 3 items are within 30d; scaled by total/len.
    assert dto.recent_30d_video_count > 0
    assert dto.avg_view_count == 2000


def test_youtube_real_auth_error():
    client = RealYouTubeClient(api_key="k")
    with respx.mock() as router:
        router.get("https://www.googleapis.com/youtube/v3/search").mock(
            return_value=httpx.Response(
                403, text="The request cannot be completed because..."
            )
        )
        with pytest.raises(AuthError):
            _run(client.fetch("x"))


def test_youtube_real_http_error():
    client = RealYouTubeClient(api_key="k")
    with respx.mock() as router:
        router.get("https://www.googleapis.com/youtube/v3/search").mock(
            return_value=httpx.Response(400, text="bad request")
        )
        with pytest.raises(ApiError):
            _run(client.fetch("x"))
