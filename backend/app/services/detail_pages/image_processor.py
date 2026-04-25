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
    _HAVE_TESSERACT = True
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]
    _HAVE_TESSERACT = False
    logger.warning(
        "pytesseract not installed; detect_chinese_ratio will return 0.0 (no filtering)"
    )


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
