"""Google Gemini Generative Language API adapter.

Used by the detail-page generator (Module C) to produce Korean SEO copy
from a Chinese source product (title + category + spec table).

Auth reuses the same Google Cloud API key family as the translation
client. We prefer ``GEMINI_API_KEY`` if set, falling back to
``GOOGLE_TRANSLATE_API_KEY`` (same GCP project assumed — the Generative
Language API just needs to be *enabled* on it).

Mock mode (``USE_MOCK_CLIENTS=true``) returns a deterministic Korean
copy stub so the rest of the ingest pipeline can run end-to-end on a
developer laptop without any external calls.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

import httpx

from .base import ApiError, AuthError, BaseApiClient, use_mock_clients

logger = logging.getLogger(__name__)

# Default model — flash is fast/cheap and adequate for short JSON copy.
DEFAULT_MODEL: str = "gemini-2.0-flash"


class GeminiClientProtocol(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = True,
        temperature: float = 0.4,
    ) -> dict[str, Any]:
        ...


class MockGeminiClient(BaseApiClient):
    """Deterministic Korean-copy stub for offline/dev/test runs."""

    async def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = True,
        temperature: float = 0.4,
    ) -> dict[str, Any]:
        # The prompt is ignored; we return a fixed shape that matches the
        # detail-page copywriter contract so downstream code can be tested.
        return {
            "title_ko": "프리미엄 한국형 상품 (테스트)",
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
                {"label": "원산지", "value": "수입"},
            ],
        }


class RealGeminiClient(BaseApiClient):
    """Calls the Generative Language v1beta REST endpoint."""

    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    _TIMEOUT_SECONDS: float = 30.0

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ):
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_TRANSLATE_API_KEY")
        )
        self.model = model

    async def generate(
        self,
        prompt: str,
        *,
        json_mode: bool = True,
        temperature: float = 0.4,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise AuthError(
                "GEMINI_API_KEY (or GOOGLE_TRANSLATE_API_KEY fallback) env var required"
            )
        if not prompt or not prompt.strip():
            raise ApiError("gemini: empty prompt")

        generation_config: dict[str, Any] = {"temperature": float(temperature)}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"

        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        url = f"{self._BASE_URL}/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
            resp = await client.post(
                url,
                params={"key": self.api_key},
                json=body,
            )

        if resp.status_code in (401, 403):
            raise AuthError(
                f"gemini auth/enable failed ({resp.status_code}): {resp.text[:300]}"
            )
        if resp.status_code >= 400:
            raise ApiError(
                f"gemini HTTP {resp.status_code}: {resp.text[:300]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise ApiError(f"gemini: non-JSON response: {resp.text[:200]}") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            raise ApiError(f"gemini: no candidates returned: {str(data)[:300]}")
        parts = (
            (candidates[0].get("content") or {}).get("parts") or []
        )
        if not parts:
            raise ApiError(f"gemini: no parts in candidate: {str(candidates[0])[:300]}")
        text = parts[0].get("text") or ""
        if not text.strip():
            raise ApiError("gemini: empty text in candidate part")

        if not json_mode:
            return {"text": text}

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            # Common failure mode: model wraps JSON in markdown fences.
            stripped = text.strip()
            if stripped.startswith("```"):
                # strip ```json ... ``` fences
                stripped = stripped.strip("`")
                if stripped.lower().startswith("json"):
                    stripped = stripped[4:]
                stripped = stripped.strip()
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass
            raise ApiError(
                f"gemini: response was not valid JSON: {text[:300]}"
            ) from exc


def get_gemini_client() -> GeminiClientProtocol:
    """Factory honouring ``USE_MOCK_CLIENTS`` like all other clients."""
    if use_mock_clients():
        return MockGeminiClient()
    return RealGeminiClient()
