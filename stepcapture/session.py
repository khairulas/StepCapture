"""A recording session: saves images, keeps steps.json current, writes tutorial.md."""
from __future__ import annotations

import json
import math
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image

from .annotate import difference, draw_click_marker, fingerprint

SCHEMA_VERSION = 1


@dataclass
class Capture:
    """Raw data grabbed at click time (kept light so the input hook stays fast)."""
    kind: str                       # "click" or "manual"
    button: Optional[str]           # "left" / "right" / "middle" / None
    screen_x: Optional[int]
    screen_y: Optional[int]
    timestamp: datetime
    monitor: int                    # 1-based mss monitor index
    monitor_rect: dict              # {"left","top","width","height"} in screen coords
    size: tuple                     # (width, height) of the image in pixels
    bgra: bytes                     # raw pixels from mss
    window_title: str = ""

    def image(self) -> Image.Image:
        return Image.frombytes("RGB", self.size, self.bgra, "raw", "BGRX")


@dataclass
class Step:
    index: int
    type: str
    timestamp: str
    elapsed_s: float
    button: Optional[str]
    screen_x: Optional[int]
    screen_y: Optional[int]
    image_x: Optional[int]
    image_y: Optional[int]
    monitor: int
    window_title: str
    image: str
    raw_image: str
    description: str = ""


@dataclass
class Session:
    output_root: Path
    dedupe: bool = True
    dedupe_threshold: float = 0.01   # screens differing by <1% count as "the same"
    dedupe_radius: int = 40          # ...if the click is also this close (px)
    title: str = ""

    dir: Path = field(init=False)
    steps: list = field(init=False, default_factory=list)
    skipped: int = field(init=False, default=0)
    started_at: datetime = field(init=False)
    ended_at: Optional[datetime] = field(init=False, default=None)

    def __post_init__(self):
        self.started_at = datetime.now().astimezone()
        name = f"session_{self.started_at:%Y%m%d_%H%M%S}"
        self.dir = Path(self.output_root).expanduser() / name
        n = 1
        while self.dir.exists():  # two sessions in the same second
            n += 1
            self.dir = Path(self.output_root).expanduser() / f"{name}_{n}"
        (self.dir / "raw").mkdir(parents=True)
        self._last_fp: Optional[Image.Image] = None
        self._last_raw: Optional[Image.Image] = None
        self._last_scale: float = 1.0
        self._write_json()

    # ------------------------------------------------------------------ steps
    def add_capture(self, cap: Capture) -> Optional[Step]:
        """Save a capture as a new step. Returns None if skipped as a duplicate."""
        img = cap.image()
        fp = fingerprint(img)

        # points -> pixels (macOS Retina reports points; Windows/Linux scale is 1.0)
        mr = cap.monitor_rect
        scale = img.width / mr["width"] if mr["width"] else 1.0

        image_x = image_y = None
        if cap.screen_x is not None and cap.screen_y is not None:
            image_x = round((cap.screen_x - mr["left"]) * scale)
            image_y = round((cap.screen_y - mr["top"]) * scale)

        if self._is_duplicate(cap, fp):
            self.skipped += 1
            return None

        index = len(self.steps) + 1
        fname = f"step_{index:03d}.png"
        img.save(self.dir / "raw" / fname, optimize=False)
        marked = (draw_click_marker(img, image_x, image_y, scale=scale)
                  if image_x is not None else img)
        marked.save(self.dir / fname, optimize=False)

        step = Step(
            index=index,
            type=cap.kind,
            timestamp=cap.timestamp.isoformat(timespec="milliseconds"),
            elapsed_s=round((cap.timestamp - self.started_at).total_seconds(), 2),
            button=cap.button,
            screen_x=cap.screen_x, screen_y=cap.screen_y,
            image_x=image_x, image_y=image_y,
            monitor=cap.monitor,
            window_title=cap.window_title,
            image=fname,
            raw_image=f"raw/{fname}",
        )
        self.steps.append(step)
        self._last_fp, self._last_raw, self._last_scale = fp, img, scale
        self._write_json()
        return step

    def mark_last_double_click(self) -> bool:
        """Turn the previous click step into a double-click and redraw its marker."""
        if not self.steps or self._last_raw is None:
            return False
        step = self.steps[-1]
        if step.type != "click" or step.image_x is None:
            return False
        step.type = "double_click"
        draw_click_marker(self._last_raw, step.image_x, step.image_y,
                          scale=self._last_scale, double=True).save(self.dir / step.image)
        self._write_json()
        return True

    def _is_duplicate(self, cap: Capture, fp: Image.Image) -> bool:
        if not self.dedupe or cap.kind != "click" or not self.steps or self._last_fp is None:
            return False
        prev = self.steps[-1]
        if prev.screen_x is None or cap.screen_x is None:
            return False
        dist = math.hypot(cap.screen_x - prev.screen_x, cap.screen_y - prev.screen_y)
        return dist <= self.dedupe_radius and difference(fp, self._last_fp) < self.dedupe_threshold

    # ----------------------------------------------------------------- output
    def finish(self) -> Path:
        self.ended_at = datetime.now().astimezone()
        self._write_json()
        self._write_markdown()
        return self.dir

    def _write_json(self) -> None:
        data = {
            "schema_version": SCHEMA_VERSION,
            "source": "desktop",
            "session_id": self.dir.name,
            "title": self.title,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "ended_at": self.ended_at.isoformat(timespec="seconds") if self.ended_at else None,
            "platform": platform.platform(),
            "skipped_duplicates": self.skipped,
            "steps": [asdict(s) for s in self.steps],
        }
        tmp = self.dir / "steps.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.dir / "steps.json")  # atomic: never a half-written file

    def _write_markdown(self) -> None:
        lines = [
            f"# {self.title or 'Tutorial draft'}",
            "",
            f"Recorded {self.started_at:%d %B %Y, %H:%M} · {len(self.steps)} steps",
            "",
            "> Draft generated by StepCapture. Replace each *Action* line with a clear instruction.",
            "",
        ]
        for s in self.steps:
            lines += [f"## Step {s.index}", "", f"**Action:** {describe(s)}", "",
                      f"![Step {s.index}]({s.image})", ""]
        (self.dir / "tutorial.md").write_text("\n".join(lines), encoding="utf-8")


def describe(step) -> str:
    """Placeholder sentence for a step (a Step or a steps.json dict) until the user writes one."""
    s = asdict(step) if isinstance(step, Step) else step
    title = s.get("window_title") or ""
    where = f" in *{title}*" if title else ""
    kind = s.get("type")
    if kind == "text":
        return "Describe this step."
    if kind == "manual":
        return f"Screenshot{where}."
    verb = {"left": "Click", "right": "Right-click", "middle": "Middle-click"}.get(
        s.get("button") or "left", "Click")
    if kind == "double_click":
        verb = "Double-click"
    return f"{verb} the highlighted area{where}."
