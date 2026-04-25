"""End-to-end tests for ``/detail-pages/*`` HTTP endpoints.

The background pipeline (Module C — Gemini + Playwright + OCR) is a
side effect; we replace ``app.routers.detail_pages.process_detail_page``
with an :class:`AsyncMock` so the router can be exercised in isolation
without spawning Playwright or hitting a real LLM.

DB writes go through the standard ``api_db_session`` fixture provided
by ``conftest.py`` (transactional, per-test rollback). Direct
``api_db_session.add(...)`` is used to seed list/get tests so we don't
double-test the ingest path.
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DetailPage, SourceProduct
from app.services.detail_pages.templates import TEMPLATE_NAMES


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _payload(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid ``IngestRequest`` body, with overrides.

    Keeps each test's payload short by only spelling out fields it
    actually cares about. Override a field to ``None`` to delete it via
    the ``del`` shortcut below.
    """
    base: dict[str, Any] = {
        "source_url": "https://detail.1688.com/offer/abc-123.html",
        "source_platform": "1688",
        "title_zh": "可爱的猫咪自动饮水机",
        "price_cny": 28.5,
        "category_path": ["宠物", "猫用品", "饮水器"],
        "specs": {"무게": "0.5kg", "사이즈": "M/L"},
        "main_images": [
            "https://cbu01.alicdn.com/img/main_1.jpg",
            "https://cbu01.alicdn.com/img/main_2.jpg",
        ],
        "detail_images": ["https://cbu01.alicdn.com/img/detail_1.jpg"],
        "option_images": [
            {"name": "Red", "url": "https://cbu01.alicdn.com/img/opt_red.jpg"},
        ],
    }
    base.update(overrides)
    return base


@pytest.fixture()
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> Generator[AsyncMock, None, None]:
    """Replace ``process_detail_page`` with an async no-op for the test.

    Returning the mock lets tests assert call counts. We patch the name
    bound inside the router module rather than the source module so the
    already-imported reference picks up the replacement.
    """
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr("app.routers.detail_pages.process_detail_page", mock)
    yield mock


# ---------------------------------------------------------------------
# POST /detail-pages/ingest
# ---------------------------------------------------------------------


def test_ingest_happy_path(
    client: TestClient,
    api_db_session: Session,
    fake_pipeline: AsyncMock,
) -> None:
    response = client.post("/detail-pages/ingest", json=_payload())
    assert response.status_code == 202

    body = response.json()
    assert isinstance(body["id"], int)
    assert body["status"] == "pending"
    assert isinstance(body["message"], str) and body["message"]

    sources = api_db_session.execute(select(SourceProduct)).scalars().all()
    assert len(sources) == 1
    assert sources[0].source_url == "https://detail.1688.com/offer/abc-123.html"

    pages = api_db_session.execute(select(DetailPage)).scalars().all()
    assert len(pages) == 1
    assert pages[0].id == body["id"]
    assert pages[0].status == "pending"
    assert pages[0].source_product_id == sources[0].id


def test_ingest_rejects_empty_main_images(
    client: TestClient,
    fake_pipeline: AsyncMock,
) -> None:
    response = client.post(
        "/detail-pages/ingest", json=_payload(main_images=[])
    )
    assert response.status_code == 400
    assert "main_images" in response.json()["detail"]
    fake_pipeline.assert_not_called()


def test_ingest_upserts_source_url(
    client: TestClient,
    api_db_session: Session,
    fake_pipeline: AsyncMock,
) -> None:
    url = "https://detail.1688.com/offer/dup.html"

    first = client.post(
        "/detail-pages/ingest",
        json=_payload(source_url=url, title_zh="원본 제목"),
    )
    assert first.status_code == 202

    second = client.post(
        "/detail-pages/ingest",
        json=_payload(source_url=url, title_zh="갱신된 제목"),
    )
    assert second.status_code == 202

    sources = api_db_session.execute(select(SourceProduct)).scalars().all()
    assert len(sources) == 1, "duplicate source_url must be upserted, not duplicated"
    assert sources[0].raw_payload["title_zh"] == "갱신된 제목"

    pages = api_db_session.execute(select(DetailPage)).scalars().all()
    assert len(pages) == 2
    assert {p.source_product_id for p in pages} == {sources[0].id}


def test_ingest_with_template_name(
    client: TestClient,
    api_db_session: Session,
    fake_pipeline: AsyncMock,
) -> None:
    # Valid template name → persisted on the row.
    ok = client.post(
        "/detail-pages/ingest",
        json=_payload(
            source_url="https://detail.1688.com/offer/tmpl-ok.html",
            template_name="detail_page_v2_minimal.html",
        ),
    )
    assert ok.status_code == 202
    page = api_db_session.execute(
        select(DetailPage).where(DetailPage.id == ok.json()["id"])
    ).scalar_one()
    assert page.template_name == "detail_page_v2_minimal.html"

    # Bogus template name → 400 with helpful detail; sanity-check
    # the catalog set really doesn't contain this name.
    assert "definitely_not_a_template.html" not in TEMPLATE_NAMES
    bad = client.post(
        "/detail-pages/ingest",
        json=_payload(
            source_url="https://detail.1688.com/offer/tmpl-bad.html",
            template_name="definitely_not_a_template.html",
        ),
    )
    # Pydantic validator triggers 422 OR router-side check returns 400 —
    # both are acceptable "rejected" outcomes; either way ``detail`` should
    # mention the field. The current schema raises in field_validator, so
    # FastAPI returns 422.
    assert bad.status_code in (400, 422)
    detail_text = str(bad.json()["detail"])
    assert (
        "Unknown template_name" in detail_text or "template_name" in detail_text
    )


# ---------------------------------------------------------------------
# GET /detail-pages
# ---------------------------------------------------------------------


def _seed_detail_page(
    session: Session,
    *,
    source_url: str,
    status: str = "pending",
    template_name: str = "detail_page_v1.html",
    props: dict[str, Any] | None = None,
    title_ko: str | None = None,
    image_path: str | None = None,
) -> DetailPage:
    """Insert a SourceProduct + DetailPage directly via ORM."""
    source = SourceProduct(
        source_url=source_url,
        source_platform="1688",
        raw_payload={"title_zh": "test", "main_images": ["x"]},
    )
    session.add(source)
    session.flush()

    dp = DetailPage(
        source_product_id=source.id,
        status=status,
        template_name=template_name,
        props=props,
        title_ko=title_ko,
        image_path=image_path,
    )
    session.add(dp)
    session.flush()
    return dp


def test_list_detail_pages_pagination_and_status_filter(
    client: TestClient,
    api_db_session: Session,
) -> None:
    _seed_detail_page(
        api_db_session, source_url="https://detail.1688.com/offer/list-1.html",
        status="pending",
    )
    _seed_detail_page(
        api_db_session, source_url="https://detail.1688.com/offer/list-2.html",
        status="done",
    )
    _seed_detail_page(
        api_db_session, source_url="https://detail.1688.com/offer/list-3.html",
        status="pending",
    )
    _seed_detail_page(
        api_db_session, source_url="https://detail.1688.com/offer/list-4.html",
        status="failed",
    )
    api_db_session.commit()

    paged = client.get("/detail-pages", params={"limit": 2})
    assert paged.status_code == 200
    body = paged.json()
    assert body["total"] == 4
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    pending = client.get("/detail-pages", params={"status": "pending"})
    assert pending.status_code == 200
    pending_body = pending.json()
    assert pending_body["total"] == 2
    assert all(item["status"] == "pending" for item in pending_body["items"])


# ---------------------------------------------------------------------
# GET /detail-pages/{id}
# ---------------------------------------------------------------------


def test_get_detail_page_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/detail-pages/999999")
    assert response.status_code == 404


def test_get_detail_page_includes_props_and_template(
    client: TestClient,
    api_db_session: Session,
) -> None:
    props = {
        "title_ko": "고양이 자동급수기",
        "highlight": "한 줄 후킹 카피",
        "aida": {"attention": "A", "interest": "I", "desire": "D", "action": "Act"},
        "spec_table": [{"label": "무게", "value": "0.5kg"}],
        "gallery": ["/generated/1/raw/detail_0.jpg"],
        "options": [],
        "main_image_url": "/generated/1/raw/main_0.jpg",
    }
    dp = _seed_detail_page(
        api_db_session,
        source_url="https://detail.1688.com/offer/get-detail.html",
        status="done",
        template_name="detail_page_v3_storytelling.html",
        props=props,
        title_ko="고양이 자동급수기",
        image_path="42/page.jpg",
    )
    api_db_session.commit()

    response = client.get(f"/detail-pages/{dp.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == dp.id
    assert body["template_name"] == "detail_page_v3_storytelling.html"
    assert body["props"] == props
    assert body["title_ko"] == "고양이 자동급수기"
    assert body["image_path"] == "42/page.jpg"


# ---------------------------------------------------------------------
# POST /detail-pages/{id}/regenerate
# ---------------------------------------------------------------------


def test_regenerate_resets_status_and_optionally_switches_template(
    client: TestClient,
    api_db_session: Session,
    fake_pipeline: AsyncMock,
) -> None:
    dp = _seed_detail_page(
        api_db_session,
        source_url="https://detail.1688.com/offer/regen.html",
        status="done",
        template_name="detail_page_v1.html",
        props={"title_ko": "old"},
        title_ko="old",
        image_path="7/page.jpg",
    )
    # Also seed a failure_reason on the row so we can prove it's cleared.
    dp.failure_reason = "stale error message"
    api_db_session.commit()
    dp_id = dp.id

    # No body → just resets fields, keeps template, calls pipeline once.
    bare = client.post(f"/detail-pages/{dp_id}/regenerate")
    assert bare.status_code == 202
    assert bare.json()["status"] == "pending"

    api_db_session.expire_all()
    refreshed = api_db_session.get(DetailPage, dp_id)
    assert refreshed is not None
    assert refreshed.status == "pending"
    assert refreshed.image_path is None
    assert refreshed.failure_reason is None
    assert refreshed.props is None
    assert refreshed.template_name == "detail_page_v1.html"
    assert fake_pipeline.call_count == 1

    # With template_name → switches template + reruns pipeline again.
    switched = client.post(
        f"/detail-pages/{dp_id}/regenerate",
        json={"template_name": "detail_page_v3_storytelling.html"},
    )
    assert switched.status_code == 202

    api_db_session.expire_all()
    refreshed = api_db_session.get(DetailPage, dp_id)
    assert refreshed is not None
    assert refreshed.template_name == "detail_page_v3_storytelling.html"
    assert refreshed.status == "pending"
    assert fake_pipeline.call_count == 2


# ---------------------------------------------------------------------
# GET /detail-pages/templates
# ---------------------------------------------------------------------


def test_get_templates_returns_catalog(client: TestClient) -> None:
    response = client.get("/detail-pages/templates")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 3

    for entry in body:
        assert isinstance(entry["name"], str) and entry["name"]
        assert isinstance(entry["label"], str) and entry["label"]
        assert isinstance(entry["description"], str) and entry["description"]
        assert entry["name"] in TEMPLATE_NAMES

    returned_names = {entry["name"] for entry in body}
    assert returned_names == set(TEMPLATE_NAMES)
