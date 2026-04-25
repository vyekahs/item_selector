"""Catalog of detail-page Jinja2 templates the operator may pick from.

The list is the single source of truth for:
  - schema validation (``IngestRequest.template_name``)
  - router-side validation (``regenerate`` body)
  - the ``GET /detail-pages/templates`` endpoint that the frontend
    populates its dropdown with.

All templates share the same Jinja2 props contract documented at the
top of each ``backend/templates/detail_page_*.html`` file. Adding a new
template = drop the file in ``backend/templates/``, append an entry
here, done — no other code changes required.
"""
from __future__ import annotations

from typing import Final


TEMPLATES: Final[list[dict[str, str]]] = [
    {
        "name": "detail_page_v1.html",
        "label": "기본",
        "description": "여백 균형, 레드 CTA 강조",
    },
    {
        "name": "detail_page_v2_minimal.html",
        "label": "미니멀",
        "description": "흰 여백 위주, 청색 단일 액센트",
    },
    {
        "name": "detail_page_v3_storytelling.html",
        "label": "스토리텔링",
        "description": "히어로 풀블리드 + 좌우 교차 AIDA",
    },
]

#: Set of valid template filenames for fast membership checks.
TEMPLATE_NAMES: Final[frozenset[str]] = frozenset(t["name"] for t in TEMPLATES)

#: Default template applied when the operator doesn't pick one.
DEFAULT_TEMPLATE: Final[str] = "detail_page_v1.html"
