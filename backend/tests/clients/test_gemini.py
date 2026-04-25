"""Tests for the Gemini Generative Language client.

Covers both the deterministic Mock and the Real client's transport
quirks (key fallback + markdown-fence stripping). All tests run
without any external HTTP — ``respx`` mocks the upstream endpoint.

The async signatures are driven through ``asyncio.run`` so we don't
need to mark each function with ``@pytest.mark.asyncio`` (the project
runs ``asyncio_mode=strict``, matching the convention used in
``tests/clients/test_real_http.py``).
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.clients.base import BaseApiClient
from app.clients.gemini import (
    MockGeminiClient,
    RealGeminiClient,
    get_gemini_client,
)


def _run(coro):
    return asyncio.run(coro)


# ---- env hygiene ----------------------------------------------------


@pytest.fixture()
def _clear_gemini_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure stray env vars from other tests don't leak in."""
    monkeypatch.delenv("USE_MOCK_CLIENTS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_TRANSLATE_API_KEY", raising=False)


# ---- MockGeminiClient -----------------------------------------------


def test_mock_gemini_returns_deterministic_dict():
    """The mock ignores the prompt and returns the documented 4-key shape."""
    out = _run(MockGeminiClient().generate("anything goes here"))

    assert isinstance(out, dict)
    assert set(out.keys()) == {"title_ko", "highlight", "aida", "spec_table"}

    # The aida sub-dict must have all four AIDA fields.
    assert isinstance(out["aida"], dict)
    assert set(out["aida"].keys()) == {"attention", "interest", "desire", "action"}

    # spec_table is a list of {label, value} dicts.
    assert isinstance(out["spec_table"], list)
    assert out["spec_table"], "spec_table must be non-empty in the mock"
    for row in out["spec_table"]:
        assert set(row.keys()) == {"label", "value"}

    # Determinism: a second call returns the same payload.
    again = _run(MockGeminiClient().generate("totally different prompt"))
    assert again == out


def test_mock_gemini_inherits_base_api_client():
    """Sanity: keeps the same nominal-base tag as the rest of the client family."""
    assert isinstance(MockGeminiClient(), BaseApiClient)


# ---- factory ---------------------------------------------------------


def test_get_gemini_client_returns_mock_when_use_mock_clients_true(
    _clear_gemini_env, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("USE_MOCK_CLIENTS", "true")
    client = get_gemini_client()
    assert isinstance(client, MockGeminiClient)


def test_get_gemini_client_returns_real_when_use_mock_clients_false(
    _clear_gemini_env, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("USE_MOCK_CLIENTS", "false")
    # api_key is read at __init__; provide one so factory doesn't need
    # any external env.
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    client = get_gemini_client()
    assert isinstance(client, RealGeminiClient)


# ---- RealGeminiClient: auth/env handling ----------------------------


def test_real_gemini_uses_translate_key_fallback(
    _clear_gemini_env, monkeypatch: pytest.MonkeyPatch
):
    """If GEMINI_API_KEY is unset, fall back to GOOGLE_TRANSLATE_API_KEY."""
    monkeypatch.setenv("GOOGLE_TRANSLATE_API_KEY", "translate-fallback-key")
    client = RealGeminiClient()
    assert client.api_key == "translate-fallback-key"


def test_real_gemini_prefers_gemini_key_over_translate(
    _clear_gemini_env, monkeypatch: pytest.MonkeyPatch
):
    """``GEMINI_API_KEY`` takes precedence when both env vars are set."""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-primary-key")
    monkeypatch.setenv("GOOGLE_TRANSLATE_API_KEY", "translate-fallback-key")
    client = RealGeminiClient()
    assert client.api_key == "gemini-primary-key"


# ---- RealGeminiClient: HTTP behaviour --------------------------------


def _wrap_candidate(text_payload: str) -> dict:
    """Build a minimal Generative Language response envelope."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text_payload}],
                }
            }
        ]
    }


def test_real_gemini_strips_markdown_fence_in_json_mode():
    """Models occasionally wrap JSON in ```json ... ``` fences; tolerate it."""
    fenced = "```json\n{\"title_ko\": \"한국어 제목\", \"x\": 1}\n```"
    client = RealGeminiClient(api_key="dummy")

    with respx.mock(assert_all_called=True) as router:
        route = router.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash:generateContent"
        ).mock(return_value=httpx.Response(200, json=_wrap_candidate(fenced)))

        out = _run(client.generate("write korean copy"))

    assert route.called
    assert out == {"title_ko": "한국어 제목", "x": 1}


def test_real_gemini_parses_clean_json_in_json_mode():
    """Fast-path: well-formed JSON with no fence parses straight through."""
    clean = '{"title_ko": "ok", "spec_table": []}'
    client = RealGeminiClient(api_key="dummy")

    with respx.mock() as router:
        router.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash:generateContent"
        ).mock(return_value=httpx.Response(200, json=_wrap_candidate(clean)))

        out = _run(client.generate("p"))

    assert out == {"title_ko": "ok", "spec_table": []}
