"""Smoke test for the detail-page orchestrator.

Every external call (DB session, image download, OCR, LLM, Playwright
render) is stubbed so the test can run on a slim laptop without
postgres, the chromium binary, tesseract or Pillow.

The point of this test is to lock down the *control flow* and the
``props`` contract — i.e. the orchestrator wires the pieces together
the way the renderer template expects.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from app.models import DetailPage, SourceProduct
from app.services.detail_pages import ingest


# ---- in-memory stubs ------------------------------------------------


class _StubSession:
    """Minimal session double: serves prepared objects by id, records
    commits, ignores ``close()``."""

    def __init__(self, store: dict[tuple[type, int], object]):
        self._store = store
        self.commit_count = 0
        self.closed = False

    def get(self, model, pk):
        return self._store.get((model, pk))

    def commit(self) -> None:
        self.commit_count += 1

    def close(self) -> None:
        self.closed = True


def _make_detail_page(
    *, dp_id: int = 42, source_id: int = 7,
    template_name: str = "detail_page_v1.html",
) -> DetailPage:
    """Build a transient DetailPage (not bound to any session)."""
    dp = DetailPage(
        source_product_id=source_id,
        status="pending",
        template_name=template_name,
    )
    # Attribute-only assignment is fine — the Mapped descriptors accept
    # plain Python ints/strs as long as we never flush them.
    dp.id = dp_id
    return dp


def _make_source_product(*, source_id: int = 7) -> SourceProduct:
    sp = SourceProduct(
        source_url="https://detail.1688.com/offer/test.html",
        source_platform="1688",
        raw_payload={
            "title_zh": "测试产品",
            "category_path": ["宠物", "猫用品"],
            "specs": {"무게": "0.5kg"},
            "main_images": ["https://cdn.example.com/main_0.jpg"],
            "detail_images": ["https://cdn.example.com/detail_0.jpg"],
            "option_images": [
                {"name": "Red", "url": "https://cdn.example.com/opt_red.jpg"},
            ],
        },
    )
    sp.id = source_id
    return sp


# ---- the test --------------------------------------------------------


def test_process_detail_page_smoke_with_all_external_calls_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    # 1. Working directory → tmp so ``GENERATED_ROOT = Path("generated")``
    #    resolves under tmp_path. We restore on teardown via monkeypatch.
    monkeypatch.chdir(tmp_path)

    dp_id = 42
    detail_page = _make_detail_page(dp_id=dp_id, source_id=7)
    source = _make_source_product(source_id=7)

    store: dict[tuple[type, int], object] = {
        (DetailPage, dp_id): detail_page,
        (SourceProduct, 7): source,
    }
    session = _StubSession(store)

    # 2. SessionLocal → returns our stub. Patch on the *ingest* module
    #    where the symbol is imported, not on app.db.session.
    monkeypatch.setattr(ingest, "SessionLocal", lambda: session)

    # 3. download_image → write 4 bytes; pretend success.
    async def _fake_download(url: str, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake")
        return True

    monkeypatch.setattr(ingest, "download_image", _fake_download)

    # 4. detect_chinese_ratio → always 0.0 → no masking, gallery passes through.
    monkeypatch.setattr(ingest, "detect_chinese_ratio", lambda p: 0.0)

    # 5. generate_copy → fixed 4-field payload.
    fixed_copy = {
        "title_ko": "스마트 자동급수기 5L 대용량",
        "highlight": "한 줄 후킹 카피",
        "aida": {
            "attention": "A",
            "interest": "I",
            "desire": "D",
            "action": "Act",
        },
        "spec_table": [{"label": "용량", "value": "5L"}],
    }

    async def _fake_generate(title_zh, category_path, specs):
        return fixed_copy

    monkeypatch.setattr(ingest, "generate_copy", _fake_generate)

    # 6. render_to_jpg → write a 1-byte placeholder at dst.
    async def _fake_render(props, output_path: Path, *, template_name: str):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"x")

    monkeypatch.setattr(ingest, "render_to_jpg", _fake_render)

    # ---- run -------------------------------------------------------
    asyncio.run(ingest.process_detail_page(dp_id))

    # ---- session lifecycle ----------------------------------------
    # commits: 1) status→processing  2) success path
    assert session.commit_count >= 2
    assert session.closed is True

    # ---- DetailPage was finalised ---------------------------------
    assert detail_page.status == "done"
    assert detail_page.failure_reason is None
    assert detail_page.image_path == f"{dp_id}/page.jpg"
    # Title is truncated to ≤200 chars.
    assert detail_page.title_ko == fixed_copy["title_ko"]

    # ---- props contract -------------------------------------------
    props = detail_page.props
    assert isinstance(props, dict)
    assert set(props.keys()) == {
        "title_ko",
        "highlight",
        "main_image_url",
        "aida",
        "spec_table",
        "gallery",
        "options",
    }
    assert props["title_ko"] == fixed_copy["title_ko"]
    assert props["highlight"] == fixed_copy["highlight"]
    assert props["aida"] == fixed_copy["aida"]
    assert props["spec_table"] == fixed_copy["spec_table"]

    # main_image_url is the public path of the first downloaded main img.
    assert props["main_image_url"].startswith(f"/generated/{dp_id}/raw/main_")
    # gallery has the (single) detail image, kept as-is because ratio=0.
    assert len(props["gallery"]) == 1
    assert props["gallery"][0].startswith(f"/generated/{dp_id}/raw/detail_")
    # option_props re-pairs name+image_url.
    assert props["options"] == [
        {
            "name": "Red",
            "image_url": f"/generated/{dp_id}/raw/option_0.jpg",
        }
    ]

    # ---- the rendered JPG actually exists --------------------------
    output_jpg = tmp_path / "generated" / str(dp_id) / "page.jpg"
    assert output_jpg.exists()
    assert output_jpg.read_bytes() == b"x"


def test_process_detail_page_marks_failed_when_pipeline_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Any exception inside the pipeline → status=failed + traceback persisted."""
    monkeypatch.chdir(tmp_path)

    dp_id = 99
    detail_page = _make_detail_page(dp_id=dp_id, source_id=1)
    source = _make_source_product(source_id=1)
    store: dict[tuple[type, int], object] = {
        (DetailPage, dp_id): detail_page,
        (SourceProduct, 1): source,
    }
    session = _StubSession(store)
    monkeypatch.setattr(ingest, "SessionLocal", lambda: session)

    # download_image errors are swallowed by ``asyncio.gather`` inside
    # the orchestrator (partial success is OK). Pick a stage whose
    # exception genuinely propagates: ``generate_copy``.
    async def _fake_download(url: str, dest: Path) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")
        return True

    monkeypatch.setattr(ingest, "download_image", _fake_download)
    monkeypatch.setattr(ingest, "detect_chinese_ratio", lambda p: 0.0)

    async def _boom_copy(*a, **kw):
        raise RuntimeError("gemini exploded")

    async def _noop_render(*a, **kw):  # pragma: no cover
        return None

    monkeypatch.setattr(ingest, "generate_copy", _boom_copy)
    monkeypatch.setattr(ingest, "render_to_jpg", _noop_render)

    asyncio.run(ingest.process_detail_page(dp_id))

    assert detail_page.status == "failed"
    assert detail_page.failure_reason
    # Traceback should mention the deliberate failure message.
    assert "gemini exploded" in detail_page.failure_reason
    assert session.closed is True


def test_process_detail_page_no_op_when_id_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Unknown id → return cleanly without touching the rest of the pipeline."""
    monkeypatch.chdir(tmp_path)

    session = _StubSession({})  # nothing stored
    monkeypatch.setattr(ingest, "SessionLocal", lambda: session)

    # If any stage actually ran, these would explode.
    def _explode(*a, **kw):  # pragma: no cover - must not be called
        raise AssertionError("pipeline ran for unknown id")

    monkeypatch.setattr(ingest, "download_image", _explode)
    monkeypatch.setattr(ingest, "detect_chinese_ratio", _explode)
    monkeypatch.setattr(ingest, "generate_copy", _explode)
    monkeypatch.setattr(ingest, "render_to_jpg", _explode)

    asyncio.run(ingest.process_detail_page(123_456))
    assert session.closed is True
