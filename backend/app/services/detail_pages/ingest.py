"""Detail-page background processing pipeline.

Entry point: :func:`process_detail_page` — invoked by the API router
(Module B) as a FastAPI ``BackgroundTask`` after a successful
``POST /detail-pages/ingest`` insertion.

Pipeline stages:
    1. Mark the row as ``processing``.
    2. Download main + detail + option images into
       ``generated/{id}/raw/``.
    3. OCR-filter detail images (drop ones dominated by Chinese text).
    4. Ask Gemini for Korean copy (title, hook, AIDA, spec_table).
    5. Build the ``props`` dict the renderer template expects.
    6. Render → JPG at ``generated/{id}/page.jpg``.
    7. Persist ``image_path`` + ``status='done'``.

Any exception → ``status='failed'`` with the last 2KB of the traceback
written to ``failure_reason`` for debugging.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from pathlib import Path
from typing import Any

from app.db.session import SessionLocal
from app.models import DetailPage, SourceProduct

from .copywriter import generate_copy
from .image_processor import (
    detect_chinese_ratio,
    download_image,
    mask_chinese_regions,
)
from .renderer import render_to_jpg

logger = logging.getLogger(__name__)


# Mount root used by the FastAPI StaticFiles handler. Resolved relative
# to the backend working directory (Docker: ``/app/generated``).
GENERATED_ROOT: Path = Path("generated")

# --- Chinese-text handling thresholds for detail images -------------
#
# We tier detail images by Chinese-character density (see
# ``detect_chinese_ratio``) instead of a single hard cutoff:
#
#   ratio >= HEAVY_CHINESE_RATIO  → drop entirely. The image is mostly
#       marketing copy; even after masking there's nothing useful left.
#   ratio >= MASK_CHINESE_RATIO   → keep but paint white rectangles
#       over each detected CJK token (``mask_chinese_regions``). These
#       are real product photos with a few Chinese labels we can hide.
#   ratio <  MASK_CHINESE_RATIO   → use as-is (incidental noise / no
#       text). OCR isn't free, so we skip masking when the gain is low.
HEAVY_CHINESE_RATIO: float = 0.50
MASK_CHINESE_RATIO: float = 0.05


# ---- helpers --------------------------------------------------------


def _generated_dir(detail_page_id: int) -> Path:
    return GENERATED_ROOT / str(detail_page_id)


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _safe_option_list(value: Any) -> list[dict[str, str]]:
    """Coerce raw_payload['option_images'] into ``[{name, url}, ...]``."""
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        out.append({"name": name, "url": url})
    return out


async def _download_many(
    urls: list[str], dest_dir: Path, prefix: str
) -> list[Path]:
    """Download URLs concurrently; return successful local paths in order.

    Failed downloads are silently skipped (already logged inside
    ``download_image``) — partial success is better than aborting the
    whole pipeline because one CDN URL 404'd.
    """
    if not urls:
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    tasks = []
    for idx, url in enumerate(urls):
        # Use ``.jpg`` regardless of source ext — we don't validate the
        # actual MIME until optimize_image re-encodes anyway.
        dest = dest_dir / f"{prefix}_{idx}.jpg"
        paths.append(dest)
        tasks.append(download_image(url, dest))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    kept: list[Path] = []
    for path, ok in zip(paths, results):
        if isinstance(ok, Exception):
            logger.warning("download error for %s: %s", path, ok)
            continue
        if ok and path.exists():
            kept.append(path)
    return kept


def _public_path(detail_page_id: int, local: Path) -> str:
    """Convert a local generated/{id}/... path to the public URL path."""
    try:
        rel = local.relative_to(GENERATED_ROOT)
    except ValueError:
        rel = Path(str(detail_page_id)) / local.name
    return f"/generated/{rel.as_posix()}"


# ---- main entry point ----------------------------------------------


async def process_detail_page(detail_page_id: int) -> None:
    """Run the full pipeline for ``detail_page_id``.

    Always commits before returning — caller (BackgroundTask) doesn't
    own a session. Never raises: failures are persisted as
    ``status='failed'``.
    """
    session = SessionLocal()
    try:
        detail_page = session.get(DetailPage, detail_page_id)
        if detail_page is None:
            logger.warning(
                "process_detail_page: id=%s not found", detail_page_id
            )
            return
        source = session.get(SourceProduct, detail_page.source_product_id)
        if source is None:
            detail_page.status = "failed"
            detail_page.failure_reason = (
                f"source_product id={detail_page.source_product_id} not found"
            )
            session.commit()
            return

        detail_page.status = "processing"
        detail_page.failure_reason = None
        session.commit()

        try:
            await _run_pipeline(detail_page, source)
            session.commit()
        except Exception:  # noqa: BLE001 — capture everything
            tb = traceback.format_exc()
            logger.exception(
                "process_detail_page failed for id=%s", detail_page_id
            )
            # Re-fetch in case the session lost the object.
            dp = session.get(DetailPage, detail_page_id)
            if dp is not None:
                dp.status = "failed"
                dp.failure_reason = tb[-2000:]
                session.commit()
    finally:
        session.close()


async def _run_pipeline(detail_page: DetailPage, source: SourceProduct) -> None:
    payload: dict[str, Any] = source.raw_payload or {}
    detail_page_id = detail_page.id

    title_zh = str(payload.get("title_zh") or "")
    category_path = _safe_str_list(payload.get("category_path"))
    specs_raw = payload.get("specs") or {}
    specs: dict[str, str] = {
        str(k): str(v) for k, v in specs_raw.items() if k is not None
    } if isinstance(specs_raw, dict) else {}

    main_urls = _safe_str_list(payload.get("main_images"))
    detail_urls = _safe_str_list(payload.get("detail_images"))
    options = _safe_option_list(payload.get("option_images"))
    option_urls = [opt["url"] for opt in options]

    # 1. download images concurrently across the three buckets
    raw_dir = _generated_dir(detail_page_id) / "raw"
    main_paths_task = _download_many(main_urls, raw_dir, "main")
    detail_paths_task = _download_many(detail_urls, raw_dir, "detail")
    option_paths_task = _download_many(option_urls, raw_dir, "option")
    main_paths, detail_paths, option_paths = await asyncio.gather(
        main_paths_task, detail_paths_task, option_paths_task
    )

    # 2. tier detail images by Chinese-text density: drop heavy ones,
    #    mask moderate ones, keep light ones unchanged. Masked variants
    #    are written next to the originals as ``masked_<filename>`` so
    #    the raw downloads stay around for debugging.
    gallery_paths: list[Path] = []
    for path in detail_paths:
        ratio = detect_chinese_ratio(path)
        if ratio >= HEAVY_CHINESE_RATIO:
            logger.info(
                "detail image dropped (chinese_ratio=%.2f >= %.2f): %s",
                ratio, HEAVY_CHINESE_RATIO, path,
            )
            continue
        if ratio >= MASK_CHINESE_RATIO:
            masked_path = path.with_name(f"masked_{path.name}")
            try:
                regions = mask_chinese_regions(path, masked_path)
            except Exception as exc:  # noqa: BLE001 — never fail the pipeline on masking
                logger.warning(
                    "mask_chinese_regions failed for %s: %s; using original",
                    path, exc,
                )
                gallery_paths.append(path)
                continue
            logger.info(
                "detail image masked (chinese_ratio=%.2f, regions=%d): %s",
                ratio, regions, path,
            )
            gallery_paths.append(
                masked_path if masked_path.exists() else path
            )
        else:
            gallery_paths.append(path)

    # 3. LLM copy
    copy = await generate_copy(title_zh, category_path, specs)

    # 4. build template props
    main_image_url = (
        _public_path(detail_page_id, main_paths[0]) if main_paths else ""
    )
    gallery = [_public_path(detail_page_id, p) for p in gallery_paths]

    # Re-pair option metadata with the locally-downloaded images. We
    # rely on positional alignment — option_paths preserves input order,
    # but a failed download drops out, so we re-derive by filename idx.
    option_props: list[dict[str, str]] = []
    for opt, path in zip(options, option_paths):
        if path is None or not path.exists():
            continue
        option_props.append(
            {
                "name": opt.get("name") or "",
                "image_url": _public_path(detail_page_id, path),
            }
        )

    props: dict[str, Any] = {
        "title_ko": copy.get("title_ko") or "",
        "highlight": copy.get("highlight") or "",
        "main_image_url": main_image_url,
        "aida": copy.get("aida") or {},
        "spec_table": copy.get("spec_table") or [],
        "gallery": gallery,
        "options": option_props,
    }

    detail_page.props = props
    detail_page.title_ko = (props["title_ko"] or "")[:200] or None

    # 5. render
    output_jpg = _generated_dir(detail_page_id) / "page.jpg"
    await render_to_jpg(
        props,
        output_jpg,
        template_name=detail_page.template_name,
    )

    # 6. mark done
    detail_page.image_path = f"{detail_page_id}/page.jpg"
    detail_page.status = "done"
    detail_page.failure_reason = None
