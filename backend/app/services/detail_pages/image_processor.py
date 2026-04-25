"""Image utilities for the detail-page generator.

Three concerns, intentionally kept side-effect-free where possible:

1. ``download_image`` — fetch a remote image to disk with size/timeout
   guards.
2. ``detect_chinese_ratio`` / ``filter_clean_images`` — drop detail
   images dominated by Chinese marketing text (we want clean visuals).
3. ``optimize_image`` — resize + JPG re-encode to keep the final
   detail-page asset under e-commerce platform limits.

Heavy optional deps (Pillow, pytesseract) are imported lazily so the
backend test suite still runs in a slim Docker image / CI without
``tesseract-ocr`` or ``Pillow`` installed. Module-level functions raise
a clear error at *call time* if the dep is missing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# --- optional dep imports (deferred-friendly) -----------------------

try:  # noqa: SIM105 — explicit fallback log
    from PIL import Image  # type: ignore
    _HAVE_PIL = True
except ImportError:  # pragma: no cover - exercised only without Pillow
    Image = None  # type: ignore[assignment]
    _HAVE_PIL = False
    logger.warning(
        "Pillow not installed; image_processor.optimize_image will fail at call time"
    )

try:  # noqa: SIM105
    import pytesseract  # type: ignore
    from pytesseract import Output  # type: ignore
    _HAVE_TESSERACT = True
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]
    Output = None  # type: ignore[assignment]
    _HAVE_TESSERACT = False
    logger.warning(
        "pytesseract not installed; detect_chinese_ratio will return 0.0 (no filtering)"
    )

try:  # noqa: SIM105 — ImageDraw is a Pillow submodule we import lazily
    from PIL import ImageDraw  # type: ignore
    _HAVE_IMAGEDRAW = True
except ImportError:  # pragma: no cover
    ImageDraw = None  # type: ignore[assignment]
    _HAVE_IMAGEDRAW = False


# --- tunables --------------------------------------------------------

DOWNLOAD_TIMEOUT_SECONDS: float = 10.0
MAX_DOWNLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MB hard cap
DEFAULT_MAX_CHINESE_RATIO: float = 0.30
DEFAULT_MAX_WIDTH: int = 860  # Korean e-commerce convention
DEFAULT_JPG_QUALITY: int = 80


# --- download --------------------------------------------------------


async def download_image(url: str, dest_path: Path) -> bool:
    """Stream-download ``url`` to ``dest_path``.

    Returns True on success, False on any non-fatal failure (HTTP error,
    too large, timeout). Network errors are logged, not raised — the
    caller can keep going with whatever images did succeed.
    """
    if not url or not url.startswith(("http://", "https://")):
        logger.warning("download_image: refusing non-http(s) URL: %r", url)
        return False

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    logger.warning(
                        "download_image: HTTP %s for %s", resp.status_code, url
                    )
                    return False
                total = 0
                with dest_path.open("wb") as fp:
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            logger.warning(
                                "download_image: %s exceeded %d bytes, aborting",
                                url, MAX_DOWNLOAD_BYTES,
                            )
                            fp.close()
                            try:
                                dest_path.unlink(missing_ok=True)
                            except OSError:
                                pass
                            return False
                        fp.write(chunk)
        return True
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("download_image: %s failed: %s", url, exc)
        try:
            dest_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


# --- OCR-based filtering --------------------------------------------


def detect_chinese_ratio(image_path: Path) -> float:
    """Return rough ratio of Chinese-character density in the image.

    Implementation note: a true ratio would compare the bounding-box
    area of detected Chinese glyphs to the image area. That requires
    tesseract's hOCR/TSV output and noticeably more processing. For our
    "is this image dominated by marketing copy?" use-case, a simple
    proxy works: ``len(chars) / 100`` clipped to ``[0, 1]``. A poster
    with ≥100 Chinese chars already counts as "fully covered" for our
    filtering threshold.

    Returns 0.0 (no chars detected) when pytesseract is unavailable, so
    filtering becomes a no-op in dev/CI without the binary.
    """
    if not _HAVE_TESSERACT:
        return 0.0
    if not image_path.exists():
        return 0.0
    try:
        # Pillow is required by pytesseract.image_to_string anyway.
        if _HAVE_PIL:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang="chi_sim")
        else:
            text = pytesseract.image_to_string(str(image_path), lang="chi_sim")
    except Exception as exc:  # noqa: BLE001 — tesseract missing/binary errors
        logger.warning("detect_chinese_ratio: OCR failed for %s: %s", image_path, exc)
        return 0.0

    chinese_chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    ratio = len(chinese_chars) / 100.0
    return max(0.0, min(1.0, ratio))


def filter_clean_images(
    paths: list[Path],
    max_chinese_ratio: float = DEFAULT_MAX_CHINESE_RATIO,
) -> list[Path]:
    """Keep images whose Chinese-character ratio is *below* the threshold."""
    kept: list[Path] = []
    for p in paths:
        ratio = detect_chinese_ratio(p)
        if ratio < max_chinese_ratio:
            kept.append(p)
        else:
            logger.info(
                "filter_clean_images: dropping %s (chinese_ratio=%.2f >= %.2f)",
                p, ratio, max_chinese_ratio,
            )
    return kept


# --- OCR-based masking ----------------------------------------------


def _copy_file(src: Path, dst: Path) -> None:
    """Byte-copy ``src`` to ``dst`` without requiring Pillow."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as r, dst.open("wb") as w:
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            w.write(chunk)


def mask_chinese_regions(
    src: Path,
    dst: Path,
    *,
    padding_px: int = 4,
    min_confidence: float = 30.0,
) -> int:
    """Paint white rectangles over detected Chinese text bboxes.

    Returns the number of regions masked. Writes to ``dst`` (PNG/JPG
    per src extension). When pytesseract is unavailable or no text is
    detected, copies src→dst unmodified and returns 0.
    """
    if not src.exists():
        raise FileNotFoundError(f"mask_chinese_regions: source not found: {src}")

    # Degrade gracefully when optional deps aren't installed (dev/CI).
    if not _HAVE_TESSERACT or not _HAVE_PIL or not _HAVE_IMAGEDRAW:
        logger.warning(
            "mask_chinese_regions: optional deps missing "
            "(tesseract=%s pil=%s draw=%s); copying %s unmodified",
            _HAVE_TESSERACT, _HAVE_PIL, _HAVE_IMAGEDRAW, src,
        )
        _copy_file(src, dst)
        return 0

    try:
        img = Image.open(src)
        # OCR is most reliable in RGB; some inputs are CMYK/P/etc.
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        data = pytesseract.image_to_data(
            img, lang="chi_sim", output_type=Output.DICT
        )
    except Exception as exc:  # noqa: BLE001 — tesseract binary failures, etc.
        logger.warning(
            "mask_chinese_regions: OCR failed for %s: %s; copying unmodified",
            src, exc,
        )
        _copy_file(src, dst)
        return 0

    texts = data.get("text") or []
    confs = data.get("conf") or []
    lefts = data.get("left") or []
    tops = data.get("top") or []
    widths = data.get("width") or []
    heights = data.get("height") or []

    masked = 0
    draw = ImageDraw.Draw(img)
    img_w, img_h = img.size

    for idx, text in enumerate(texts):
        if not isinstance(text, str) or not text.strip():
            continue
        # Require at least one CJK Unified Ideograph in the token.
        if not any("\u4e00" <= c <= "\u9fff" for c in text):
            continue
        # ``conf`` is a string like "-1" / "94" depending on tesseract build.
        try:
            conf = float(confs[idx])
        except (TypeError, ValueError, IndexError):
            continue
        if conf < min_confidence:
            continue
        try:
            x = int(lefts[idx])
            y = int(tops[idx])
            w = int(widths[idx])
            h = int(heights[idx])
        except (TypeError, ValueError, IndexError):
            continue
        if w <= 0 or h <= 0:
            continue
        x0 = max(0, x - padding_px)
        y0 = max(0, y - padding_px)
        x1 = min(img_w, x + w + padding_px)
        y1 = min(img_h, y + h + padding_px)
        if x1 <= x0 or y1 <= y0:
            continue
        draw.rectangle((x0, y0, x1, y1), fill="white")
        masked += 1

    if masked == 0:
        # Nothing to paint — preserve original bytes/format.
        img.close()
        _copy_file(src, dst)
        return 0

    dst.parent.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    save_kwargs: dict[str, Any] = {}
    if ext in (".jpg", ".jpeg"):
        save_kwargs["format"] = "JPEG"
        save_kwargs["quality"] = 90
        if img.mode != "RGB":
            img = img.convert("RGB")
    elif ext == ".png":
        save_kwargs["format"] = "PNG"
    else:
        # Fall back to source extension's implicit format; if Pillow
        # can't infer it (rare), force JPEG.
        try:
            img.save(dst)
            img.close()
            return masked
        except (OSError, ValueError):
            save_kwargs["format"] = "JPEG"
            save_kwargs["quality"] = 90
            if img.mode != "RGB":
                img = img.convert("RGB")

    img.save(dst, **save_kwargs)
    img.close()
    return masked


# --- optimisation ---------------------------------------------------


def optimize_image(
    src: Path,
    dst: Path,
    max_width: int = DEFAULT_MAX_WIDTH,
    jpg_quality: int = DEFAULT_JPG_QUALITY,
) -> None:
    """Resize ``src`` to ``max_width`` (preserving aspect) and re-encode as JPG.

    Raises :class:`RuntimeError` if Pillow isn't installed. Callers
    higher up the pipeline should catch this and mark the work item as
    failed with a clear ``failure_reason``.
    """
    if not _HAVE_PIL:
        raise RuntimeError(
            "optimize_image requires Pillow; install with `pip install Pillow`"
        )
    if not src.exists():
        raise FileNotFoundError(f"optimize_image: source not found: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        # JPG can't represent alpha — flatten on white if needed.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        if img.width > max_width:
            new_height = int(img.height * (max_width / img.width))
            # ``LANCZOS`` is the modern alias for high-quality downscaling.
            resample = getattr(Image, "Resampling", Image).LANCZOS
            img = img.resize((max_width, new_height), resample)

        img.save(
            dst,
            format="JPEG",
            quality=int(jpg_quality),
            optimize=True,
            progressive=True,
        )
