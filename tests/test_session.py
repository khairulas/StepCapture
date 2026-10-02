"""Unit tests for Session (no display needed). Run: python -m pytest tests  (or python tests/test_session.py)"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stepcapture.session import Capture, Session  # noqa: E402

MON = {"left": 0, "top": 0, "width": 800, "height": 600}


def fake_capture(x, y, color, kind="click", rect=MON, size=(800, 600), button="left"):
    img = Image.new("RGB", size, color)
    ImageDraw.Draw(img).rectangle([50, 50, 300, 200], fill=(255, 255, 255))
    bgra = img.convert("RGBA").tobytes("raw", "BGRA")
    return Capture(kind=kind, button=button if kind == "click" else None,
                   screen_x=x if kind == "click" else None, screen_y=y if kind == "click" else None,
                   timestamp=datetime.now().astimezone(), monitor=1, monitor_rect=rect,
                   size=size, bgra=bgra, window_title="Test Window")


def test_steps_dedupe_double_and_outputs():
    with tempfile.TemporaryDirectory() as d:
        s = Session(Path(d))
        assert (s.dir / "steps.json").exists()                       # written at start

        assert s.add_capture(fake_capture(100, 100, (0, 0, 120))) is not None
        assert s.add_capture(fake_capture(105, 102, (0, 0, 120))) is None   # same screen, close: skip
        assert s.add_capture(fake_capture(500, 400, (0, 0, 120))) is not None  # same screen, far: keep
        assert s.add_capture(fake_capture(500, 400, (120, 0, 0))) is not None  # screen changed: keep
        assert s.mark_last_double_click()
        assert s.add_capture(fake_capture(0, 0, (0, 0, 0), kind="manual")) is not None

        data = json.loads((s.dir / "steps.json").read_text())       # crash-safe mid-session
        assert len(data["steps"]) == 4 and data["skipped_duplicates"] == 1

        out = s.finish()
        data = json.loads((out / "steps.json").read_text())
        assert data["schema_version"] == 1 and data["ended_at"]
        types = [st["type"] for st in data["steps"]]
        assert types == ["click", "click", "double_click", "manual"], types
        for st in data["steps"]:
            assert (out / st["image"]).exists() and (out / st["raw_image"]).exists()
        assert data["steps"][3]["image_x"] is None

        # marker is drawn on the annotated image, raw image is untouched
        marked = Image.open(out / "step_001.png").convert("RGB")
        raw = Image.open(out / "raw" / "step_001.png").convert("RGB")
        ring = (100 + 24, 100)                                       # point on the ring
        r, g, b = marked.getpixel(ring)
        assert r > 200 and g < 80 and b < 80, (r, g, b)
        assert raw.getpixel(ring) == (255, 255, 255)

        md = (out / "tutorial.md").read_text()
        assert md.count("## Step") == 4 and "Double-click" in md and "Test Window" in md


def test_retina_scaling_and_second_monitor():
    with tempfile.TemporaryDirectory() as d:
        s = Session(Path(d), dedupe=False)
        # monitor at x=1920 reported in points (800x600) but image is 2x pixels
        rect = {"left": 1920, "top": 0, "width": 800, "height": 600}
        st = s.add_capture(fake_capture(1920 + 100, 50, (0, 90, 0), rect=rect, size=(1600, 1200)))
        assert (st.image_x, st.image_y) == (200, 100)


def test_dedupe_off_keeps_repeats():
    with tempfile.TemporaryDirectory() as d:
        s = Session(Path(d), dedupe=False)
        s.add_capture(fake_capture(100, 100, (0, 0, 120)))
        assert s.add_capture(fake_capture(100, 100, (0, 0, 120))) is not None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
