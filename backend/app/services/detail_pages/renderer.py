"""Render a detail-page HTML template to a JPG via headless Chromium.

Pipeline: ``props`` dict → Jinja2 → HTML string → Playwright loads it
in headless Chromium with a 860px-wide viewport → full-page PNG
screenshot → re-encoded to optimised JPG via
:func:`image_processor.optimize_image`.

Both Jinja2 and Playwright are imported lazily so this module is
import-safe in CI/dev environments that don't have the Chromium binary
installed.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# --- optional dep imports (deferred-friendly) -----------------------

try:  # noqa: SIM105
    from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore
    _HAVE_JINJA2 = True
except ImportError:  # pragma: no cover
    Environment = None  # type: ignore[assignment]
    FileSystemLoader = None  # type: ignore[assignment]
    select_autoescape = None  # type: ignore[assignment]
    _HAVE_JINJA2 = False
    logger.warning("jinja2 not installed; render_to_jpg will fail at call time")

try:  # noqa: SIM105
    from playwright.async_api import async_playwright  # type: ignore
    _HAVE_PLAYWRIGHT = True
except ImportError:  # pragma: no cover
    async_playwright = None  # type: ignore[assignment]
    _HAVE_PLAYWRIGHT = False
    logger.warning(
        "playwright not installed; render_to_jpg will fail at call time"
    )


# --- paths ----------------------------------------------------------

# ``backend/app/services/detail_pages/renderer.py`` → ``backend/templates/``
_TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "templates"
)

VIEWPORT_WIDTH: int = 860
VIEWPORT_INITIAL_HEIGHT: int = 100  # Playwright still captures full_page=True


def _render_html(props: dict[str, Any], template_name: str) -> str:
    if not _HAVE_JINJA2:
        raise RuntimeError(
            "render_to_jpg requires jinja2; install with `pip install jinja2`"
        )
    if not _TEMPLATES_DIR.exists():
        raise RuntimeError(
            f"templates directory not found: {_TEMPLATES_DIR}. "
            "Module D (detail_page_v1.html) is expected to create it."
        )
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_name)
    return template.render(**props)


async def render_to_jpg(
    props: dict[str, Any],
    output_path: Path,
    *,
    template_name: str = "detail_page_v1.html",
) -> None:
    """Render ``props`` → ``output_path`` (JPG, 860px wide).

    Strategy: screenshot to a temp PNG, then run our standard
    Pillow-based JPG re-encoder so the output matches the rest of the
    pipeline (no separate quality knob to keep in sync).
    """
    if not _HAVE_PLAYWRIGHT:
        raise RuntimeError(
            "render_to_jpg requires playwright; "
            "install with `pip install playwright && playwright install chromium`"
        )

    # Local import — image_processor itself raises if Pillow is missing.
    from .image_processor import optimize_image

    html = _render_html(props, template_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = Path(tmpdir) / "page.png"
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={
                            "width": VIEWPORT_WIDTH,
                            "height": VIEWPORT_INITIAL_HEIGHT,
                        },
                        device_scale_factor=2,  # crisp at 2x for retina displays
                    )
                    page = await context.new_page()
                    await page.set_content(html, wait_until="networkidle")
                    await page.screenshot(
                        path=str(png_path),
                        full_page=True,
                        type="png",
                    )
                finally:
                    await browser.close()
        except Exception as exc:  # noqa: BLE001 - surface a clean message
            # Most common failure: chromium binary not installed.
            raise RuntimeError(
                f"playwright render failed: {exc}. "
                "Did you run `playwright install chromium`?"
            ) from exc

        if not png_path.exists():
            raise RuntimeError("playwright did not produce a screenshot")

        optimize_image(png_path, output_path, max_width=VIEWPORT_WIDTH)
