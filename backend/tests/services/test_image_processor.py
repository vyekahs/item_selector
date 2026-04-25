"""Tests for the image-processing helpers used by the detail-page pipeline.

The optional deps (Pillow + pytesseract) are imported lazily by the
module under test, and several tests here intentionally exercise the
"missing optional dep" code paths. Tests that *require* Pillow are
gated behind a ``pytest.importorskip`` so the file works in slim CI
images that don't ship Pillow.
"""
from __future__ import annotations

import importlib
import importlib.util

import pytest

from app.services.detail_pages import image_processor


# ---- pytesseract-missing fallbacks ----------------------------------


def test_detect_chinese_ratio_returns_zero_when_pytesseract_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
):
    """Without tesseract installed (or with the gate disabled), the
    function returns 0.0 instead of raising."""
    monkeypatch.setattr(image_processor, "_HAVE_TESSERACT", False)

    # Create a real file so the path-existence check passes; even then
    # the missing-dep guard should short-circuit before reading it.
    fake = tmp_path / "fake.jpg"
    fake.write_bytes(b"not a real image, but exists")

    assert image_processor.detect_chinese_ratio(fake) == 0.0


def test_detect_chinese_ratio_returns_zero_for_missing_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
):
    """Even when tesseract is "available", a non-existent path → 0.0."""
    monkeypatch.setattr(image_processor, "_HAVE_TESSERACT", True)
    missing = tmp_path / "does-not-exist.jpg"
    assert image_processor.detect_chinese_ratio(missing) == 0.0


def test_mask_chinese_regions_no_op_when_pytesseract_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
):
    """When optional deps are missing, copy ``src`` → ``dst`` byte-for-byte
    and return 0 (no regions masked)."""
    monkeypatch.setattr(image_processor, "_HAVE_TESSERACT", False)
    # Force the other guards too so we hit the early-return branch
    # regardless of what's actually installed locally.
    monkeypatch.setattr(image_processor, "_HAVE_PIL", False)
    monkeypatch.setattr(image_processor, "_HAVE_IMAGEDRAW", False)

    src = tmp_path / "src.jpg"
    payload = b"\xff\xd8\xff some bytes that are not really a JPEG \x00\x01\x02"
    src.write_bytes(payload)

    dst = tmp_path / "out" / "dst.jpg"
    masked = image_processor.mask_chinese_regions(src, dst)

    assert masked == 0
    assert dst.exists()
    assert dst.read_bytes() == payload


def test_mask_chinese_regions_raises_for_missing_source(tmp_path):
    """Missing source file is a programmer error, not a graceful
    degrade case — surface it loudly."""
    missing = tmp_path / "nope.jpg"
    dst = tmp_path / "dst.jpg"
    with pytest.raises(FileNotFoundError):
        image_processor.mask_chinese_regions(missing, dst)


# ---- Pillow-required tests ------------------------------------------


# Module-level guard: tests below need a real PIL image. We can't use
# ``pytest.importorskip`` at module scope because that would skip the
# Pillow-free tests above too; instead each test calls ``skipif``.
_HAS_PIL = importlib.util.find_spec("PIL") is not None
_pil_required = pytest.mark.skipif(
    not _HAS_PIL, reason="Pillow not installed in this env"
)


def _make_jpeg(path, *, width: int, height: int, color=(180, 30, 30)) -> None:
    """Write a solid-colour JPEG of the requested dimensions."""
    from PIL import Image as _Image  # noqa: PLC0415 — gated by skipif

    img = _Image.new("RGB", (width, height), color)
    img.save(path, format="JPEG", quality=85)


@_pil_required
def test_optimize_image_resizes_to_max_width_and_writes_jpg(tmp_path):
    """Source 1600px wide → resized to ≤860px, format JPEG."""
    # Reload the module so the now-importable Pillow is picked up by
    # the optional-dep gate (some CI matrices may have toggled it).
    importlib.reload(image_processor)
    if not image_processor._HAVE_PIL:  # pragma: no cover - defensive
        pytest.skip("Pillow gate is False even though import succeeded")

    src = tmp_path / "src.jpg"
    _make_jpeg(src, width=1600, height=1200)
    dst = tmp_path / "out" / "dst.jpg"

    image_processor.optimize_image(src, dst, max_width=860)

    assert dst.exists()
    from PIL import Image as _Image

    with _Image.open(dst) as out:
        assert out.format == "JPEG"
        assert out.width <= 860
        # Aspect ratio preserved within rounding (1200/1600 = 0.75).
        assert abs(out.height - int(860 * 0.75)) <= 2


@_pil_required
def test_optimize_image_passes_through_when_already_small(tmp_path):
    """A 400px-wide source must not be upscaled — keep its width."""
    importlib.reload(image_processor)
    if not image_processor._HAVE_PIL:  # pragma: no cover
        pytest.skip("Pillow gate is False even though import succeeded")

    src = tmp_path / "small.jpg"
    _make_jpeg(src, width=400, height=300)
    dst = tmp_path / "small_out.jpg"

    image_processor.optimize_image(src, dst, max_width=860)

    from PIL import Image as _Image

    with _Image.open(dst) as out:
        assert out.format == "JPEG"
        assert out.width == 400  # unchanged, not enlarged


@_pil_required
def test_optimize_image_raises_for_missing_source(tmp_path):
    importlib.reload(image_processor)
    if not image_processor._HAVE_PIL:  # pragma: no cover
        pytest.skip("Pillow gate is False even though import succeeded")
    with pytest.raises(FileNotFoundError):
        image_processor.optimize_image(
            tmp_path / "nope.jpg", tmp_path / "out.jpg"
        )
