"""Tests for the static detail-page template catalog.

The catalog is the single source of truth that the API schema, the
router validator and the frontend dropdown all depend on. These tests
pin the invariants:

* every entry has a corresponding HTML file on disk;
* every template renders cleanly with the shared sample-props contract
  (so adding a new template can't silently break the props shape).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

from app.services.detail_pages.templates import (
    DEFAULT_TEMPLATE,
    TEMPLATE_NAMES,
    TEMPLATES,
)


# Template files live at ``backend/templates/`` — three levels above
# the templates module (``app/services/detail_pages/templates.py``).
_TEMPLATES_DIR: Path = (
    Path(__import__("app.services.detail_pages.templates", fromlist=["__file__"]).__file__)
    .resolve()
    .parent.parent.parent.parent
    / "templates"
)


def test_template_names_set_matches_catalog():
    assert TEMPLATE_NAMES == frozenset(t["name"] for t in TEMPLATES)


def test_default_template_is_in_catalog():
    assert DEFAULT_TEMPLATE in TEMPLATE_NAMES


def test_each_template_html_file_exists():
    for entry in TEMPLATES:
        path = _TEMPLATES_DIR / entry["name"]
        assert path.is_file(), f"missing template file: {path}"


def test_each_catalog_entry_has_label_and_description():
    """Frontend dropdown depends on these fields being non-empty."""
    for entry in TEMPLATES:
        assert entry.get("label"), f"missing label: {entry}"
        assert entry.get("description"), f"missing description: {entry}"


@pytest.fixture(scope="module")
def sample_props() -> dict:
    sample_path = _TEMPLATES_DIR / "detail_page_v1_sample_props.json"
    assert sample_path.is_file(), f"sample props file missing: {sample_path}"
    with sample_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def test_each_template_renders_with_sample_props_without_jinja_error(
    sample_props: dict,
):
    """Every template must accept the documented props contract.

    Uses ``StrictUndefined`` so a typo'd variable name in a template
    raises immediately rather than silently rendering as the empty
    string.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
    )
    for entry in TEMPLATES:
        template = env.get_template(entry["name"])
        html = template.render(**sample_props)
        assert isinstance(html, str)
        assert html.strip(), f"empty render for {entry['name']}"
        # The Korean title from the sample should appear in every
        # rendered page (sanity that props really got bound).
        assert sample_props["title_ko"] in html, (
            f"title_ko not present in rendered {entry['name']}"
        )
