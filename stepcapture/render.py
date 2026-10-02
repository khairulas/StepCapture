"""Turn a raw screenshot plus edits (blur, marker, crop) into the final image."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from .annotate import draw_click_marker

BORDER_COLOR = (200, 200, 200)


def marker_scale(img: Image.Image) -> float:
    """Ring size grows with very large screenshots (4K, Retina)."""
    return max(1.0, img.width / 1920)


def pixelate(img: Image.Image, box, block: int = 14) -> None:
    """Pixelate a region in place. Coarse blocks make text unreadable (safer than a soft blur)."""
    x0, y0, x1, y1 = clamp_box(box, img.size)
    w, h = x1 - x0, y1 - y0
    if w < 2 or h < 2:
        return
    region = img.crop((x0, y0, x1, y1))
    small = region.resize((max(1, w // block), max(1, h // block)), Image.BILINEAR)
    img.paste(small.resize((w, h), Image.NEAREST), (x0, y0))


def clamp_box(box, size):
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    w, h = size
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def render_step(image_path: Optional[Path], step: dict, *, apply_crop: bool = True,
                border: bool = False) -> Optional[Image.Image]:
    """raw -> blur -> click marker -> crop (-> border). Returns None for text-only steps."""
    if image_path is None:
        return None
    img = Image.open(image_path).convert("RGB")

    for box in step.get("blurs") or []:
        pixelate(img, box)

    x, y = step.get("image_x"), step.get("image_y")
    if step.get("show_marker", True) and x is not None and y is not None:
        img = draw_click_marker(img, x, y, scale=marker_scale(img),
                                double=step.get("type") == "double_click")

    crop = step.get("crop")
    if apply_crop and crop:
        box = clamp_box(crop, img.size)
        if box[2] - box[0] > 4 and box[3] - box[1] > 4:
            img = img.crop(box)

    if border:
        img = ImageOps.expand(img, border=1, fill=BORDER_COLOR)
    return img


def crop_around_click(step: dict, size, fraction: float = 0.55):
    """A crop box centred on the click, `fraction` of the screen in each direction."""
    w, h = size
    cw, ch = int(w * fraction), int(h * fraction)
    x = step.get("image_x")
    y = step.get("image_y")
    if x is None or y is None:
        x, y = w // 2, h // 2
    x0 = min(max(0, x - cw // 2), w - cw)
    y0 = min(max(0, y - ch // 2), h - ch)
    return [x0, y0, x0 + cw, y0 + ch]
