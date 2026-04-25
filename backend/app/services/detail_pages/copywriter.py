"""LLM-driven Korean copywriting for detail pages.

Takes the (Chinese title, category breadcrumb, spec dict) extracted by
the Chrome Extension and asks Gemini for the four template fields:

    {
      "title_ko":   "...",   # ≤ 50 chars
      "highlight":  "...",   # ≤ 30 chars
      "aida": { "attention": "...", "interest": "...",
                "desire":    "...", "action":   "..." },
      "spec_table": [ { "label": "...", "value": "..." }, ... ]
    }

The shape is enforced by the renderer template, so we do best-effort
validation here and let any malformed response bubble up to the
ingest pipeline (which marks the DetailPage as ``failed``).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.clients.gemini import get_gemini_client

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """\
당신은 한국 e-commerce(스마트스토어, 쿠팡) 상세페이지 카피라이터입니다.
아래 중국 1688/타오바오 상품 정보를 바탕으로 한국 소비자에게 어필할
SEO 친화적이고 매력적인 한국어 카피를 작성하세요.

[입력]
- 원제목 (중국어): {title_zh}
- 카테고리: {category_path}
- 사양:
{specs_block}

[요청]
다음 JSON 형식으로만 응답하세요. 다른 설명, 마크다운, 코드 펜스 금지.

{{
  "title_ko": "한국어 SEO 제목 (50자 이내, 핵심 키워드 포함)",
  "highlight": "한 줄 후킹 카피 (30자 이내, 강한 베네핏 어필)",
  "aida": {{
    "attention": "시선을 사로잡는 한 문장",
    "interest": "제품의 흥미로운 특징/스토리 한 문장",
    "desire": "구매 욕구를 자극하는 한 문장",
    "action": "지금 구매를 유도하는 한 문장"
  }},
  "spec_table": [
    {{"label": "한국어 항목명", "value": "한국어 값"}}
  ]
}}

규칙:
- 모든 값은 한국어. 중국어/번체 사용 금지.
- 과장된 의료·효능 표현 금지 (식약처 가이드 준수).
- spec_table 은 입력 사양을 한국어로 번역/정리한 것이며 4-8개 항목.
- title_ko 는 50자, highlight 는 30자를 초과하지 마세요.
"""


def _format_specs(specs: dict[str, str]) -> str:
    if not specs:
        return "  (없음)"
    lines = []
    for k, v in specs.items():
        if k is None:
            continue
        lines.append(f"  - {k}: {v}")
    return "\n".join(lines) if lines else "  (없음)"


def _build_prompt(
    title_zh: str,
    category_path: list[str],
    specs: dict[str, str],
) -> str:
    cat = " > ".join(category_path) if category_path else "(미분류)"
    return _PROMPT_TEMPLATE.format(
        title_zh=title_zh or "(제목 없음)",
        category_path=cat,
        specs_block=_format_specs(specs or {}),
    )


def _normalise(payload: Any) -> dict[str, Any]:
    """Coerce the LLM response into the contract shape.

    Be lenient: missing keys get safe defaults rather than raising,
    because partial copy is still usable in the rendered page.
    """
    if not isinstance(payload, dict):
        # Some models occasionally double-encode as a JSON string.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = {}

    title_ko = str(payload.get("title_ko") or "").strip()
    highlight = str(payload.get("highlight") or "").strip()

    aida_in = payload.get("aida") or {}
    if not isinstance(aida_in, dict):
        aida_in = {}
    aida = {
        key: str(aida_in.get(key) or "").strip()
        for key in ("attention", "interest", "desire", "action")
    }

    spec_in = payload.get("spec_table") or []
    spec_table: list[dict[str, str]] = []
    if isinstance(spec_in, list):
        for row in spec_in:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            value = str(row.get("value") or "").strip()
            if not label and not value:
                continue
            spec_table.append({"label": label, "value": value})

    return {
        "title_ko": title_ko,
        "highlight": highlight,
        "aida": aida,
        "spec_table": spec_table,
    }


async def generate_copy(
    title_zh: str,
    category_path: list[str],
    specs: dict[str, str],
) -> dict[str, Any]:
    """Generate Korean copy for a detail page.

    Returns a dict with keys ``title_ko``, ``highlight``, ``aida``,
    ``spec_table`` (see module docstring for shape).
    """
    client = get_gemini_client()
    prompt = _build_prompt(title_zh, category_path, specs)
    logger.debug("gemini copywrite prompt length=%d", len(prompt))
    raw = await client.generate(prompt, json_mode=True, temperature=0.4)
    return _normalise(raw)
