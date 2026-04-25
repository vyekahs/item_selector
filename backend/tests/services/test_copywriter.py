"""Tests for the LLM-driven copywriter normaliser.

The Gemini factory is monkey-patched to return a stub that conforms to
``GeminiClientProtocol``. We never hit the network and we don't care
about the exact prompt the copywriter builds — only that whatever the
LLM returns gets coerced into the documented 4-key contract that the
renderer template depends on.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.services.detail_pages import copywriter


def _run(coro):
    return asyncio.run(coro)


class _StubGemini:
    """Test double matching the ``GeminiClientProtocol`` shape."""

    def __init__(self, payload: Any):
        self._payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = True,
        temperature: float = 0.4,
    ) -> Any:
        self.calls.append(
            (prompt, {"json_mode": json_mode, "temperature": temperature})
        )
        return self._payload


def _patch_factory(monkeypatch: pytest.MonkeyPatch, stub: _StubGemini) -> None:
    monkeypatch.setattr(
        "app.services.detail_pages.copywriter.get_gemini_client",
        lambda: stub,
    )


# ---- well-formed payload --------------------------------------------


def test_generate_copy_normalises_well_formed_dict(monkeypatch: pytest.MonkeyPatch):
    perfect = {
        "title_ko": "프리미엄 한국형 상품",
        "highlight": "지금 만나보세요 — 한정 수량",
        "aida": {
            "attention": "스크롤을 멈추게 하는 디자인.",
            "interest": "꼼꼼한 마감과 실용적인 구성.",
            "desire": "오늘부터 일상이 달라집니다.",
            "action": "지금 바로 담아보세요.",
        },
        "spec_table": [
            {"label": "소재", "value": "프리미엄 원단"},
            {"label": "사이즈", "value": "M / L"},
        ],
    }
    stub = _StubGemini(perfect)
    _patch_factory(monkeypatch, stub)

    out = _run(
        copywriter.generate_copy(
            title_zh="可爱的猫咪自动饮水机",
            category_path=["宠物", "猫用品"],
            specs={"무게": "0.5kg"},
        )
    )

    assert out["title_ko"] == perfect["title_ko"]
    assert out["highlight"] == perfect["highlight"]
    assert out["aida"] == perfect["aida"]
    assert out["spec_table"] == perfect["spec_table"]

    # The factory was actually called and the prompt contained both
    # the title and the spec key (sanity that ``_build_prompt`` ran).
    assert len(stub.calls) == 1
    prompt, kwargs = stub.calls[0]
    assert "可爱的猫咪自动饮水机" in prompt
    assert "무게" in prompt
    assert kwargs["json_mode"] is True


# ---- partial payload -------------------------------------------------


def test_generate_copy_normalises_partial_response(monkeypatch: pytest.MonkeyPatch):
    """Missing AIDA keys → defaults to empty strings, not KeyError."""
    partial = {
        "title_ko": "제목만 있음",
        # no highlight, partial aida, no spec_table
        "aida": {"attention": "주목!"},
    }
    _patch_factory(monkeypatch, _StubGemini(partial))

    out = _run(copywriter.generate_copy("title_zh", [], {}))

    assert out["title_ko"] == "제목만 있음"
    assert out["highlight"] == ""
    # All four AIDA keys present, missing ones defaulted to "".
    assert set(out["aida"].keys()) == {"attention", "interest", "desire", "action"}
    assert out["aida"]["attention"] == "주목!"
    assert out["aida"]["interest"] == ""
    assert out["aida"]["desire"] == ""
    assert out["aida"]["action"] == ""
    assert out["spec_table"] == []


def test_generate_copy_drops_malformed_spec_rows(monkeypatch: pytest.MonkeyPatch):
    """Non-dict rows and rows lacking both label+value get filtered out."""
    payload = {
        "title_ko": "x",
        "highlight": "y",
        "aida": {},
        "spec_table": [
            {"label": "용량", "value": "5L"},
            {"label": "", "value": ""},  # dropped: both empty
            "not a dict",                # dropped: wrong type
            {"label": "재질"},            # value missing → coerced to ""
        ],
    }
    _patch_factory(monkeypatch, _StubGemini(payload))

    out = _run(copywriter.generate_copy("t", [], {}))

    assert out["spec_table"] == [
        {"label": "용량", "value": "5L"},
        {"label": "재질", "value": ""},
    ]


# ---- string-encoded JSON --------------------------------------------


def test_generate_copy_normalises_string_response(monkeypatch: pytest.MonkeyPatch):
    """Some models double-encode the JSON as a string; the normaliser
    falls back to ``json.loads`` to recover."""
    inner = {
        "title_ko": "from-string",
        "highlight": "h",
        "aida": {
            "attention": "a",
            "interest": "i",
            "desire": "d",
            "action": "act",
        },
        "spec_table": [{"label": "k", "value": "v"}],
    }
    encoded = json.dumps(inner)
    _patch_factory(monkeypatch, _StubGemini(encoded))

    out = _run(copywriter.generate_copy("t", [], {}))

    assert out["title_ko"] == "from-string"
    assert out["aida"]["attention"] == "a"
    assert out["spec_table"] == [{"label": "k", "value": "v"}]


def test_generate_copy_handles_non_dict_non_string(monkeypatch: pytest.MonkeyPatch):
    """Pathological response (e.g. a bare list) → safe empty defaults."""
    _patch_factory(monkeypatch, _StubGemini(["not", "expected"]))

    out = _run(copywriter.generate_copy("t", [], {}))

    assert out == {
        "title_ko": "",
        "highlight": "",
        "aida": {"attention": "", "interest": "", "desire": "", "action": ""},
        "spec_table": [],
    }
