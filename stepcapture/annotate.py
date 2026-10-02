"""Image helpers: click markers and screen-similarity checks."""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageStat

MARKER_COLOR = (230, 30, 30)


def draw_click_marker(img: Image.Image, x: int, y: int, *, scale: float = 1.0,
                      double: bool = False) -> Image.Image:
    """Return a copy of img with a red ring (two rings for a double-click) at (x, y)."""
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    r = int(24 * scale)
    w = max(3, int(4 * scale))
    # soft translucent halo so the ring is visible on any background
    d.ellipse([x - r - w, y - r - w, x + r + w, y + r + w], fill=(*MARKER_COLOR, 40))
    d.ellipse([x - r, y - r, x + r, y + r], outline=(*MARKER_COLOR, 255), width=w)
    if double:
        r2 = int(r * 0.6)
        d.ellipse([x - r2, y - r2, x + r2, y + r2], outline=(*MARKER_COLOR, 255), width=w)
    dot = max(2, int(3 * scale))
    d.ellipse([x - dot, y - dot, x + dot, y + dot], fill=(*MARKER_COLOR, 255))

    return Image.alpha_composite(base, overlay).convert("RGB")


def fingerprint(img: Image.Image) -> Image.Image:
    """Small grayscale thumbnail used to compare screens quickly."""
    return img.convert("L").resize((128, 72), Image.BILINEAR)


def difference(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute pixel difference between two fingerprints, 0.0 (same) to 1.0."""
    diff = ImageChops.difference(a, b)
    return ImageStat.Stat(diff).mean[0] / 255.0
