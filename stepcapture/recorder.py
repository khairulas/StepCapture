"""Global mouse listener that grabs the screen on every click."""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import mss
from pynput import mouse

from .platform_utils import window_title_at
from .session import Capture


class Recorder:
    """Listens for clicks system-wide and hands raw captures to callbacks.

    Callbacks run on the listener thread, so they must be quick (e.g. put
    the capture on a queue). Heavy work — PNG encoding, markers — happens
    elsewhere.
    """

    def __init__(self,
                 on_capture: Callable[[Capture], None],
                 on_double_click: Callable[[], None],
                 should_ignore: Callable[[int, int], bool] = lambda x, y: False,
                 double_click_s: float = 0.4,
                 double_click_px: int = 6):
        self.on_capture = on_capture
        self.on_double_click = on_double_click
        self.should_ignore = should_ignore
        self.double_click_s = double_click_s
        self.double_click_px = double_click_px

        self._listener: Optional[mouse.Listener] = None
        self._local = threading.local()      # one mss instance per thread
        self._last_click = None              # (t, x, y, button)

    # ------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return self._listener is not None

    def start(self) -> None:
        if self._listener:
            return
        self._last_click = None
        self._listener = mouse.Listener(on_click=self._on_click)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    # -------------------------------------------------------------- capture
    def snapshot(self) -> Capture:
        """Manual capture of the monitor under the cursor, without a marker."""
        x, y = mouse.Controller().position
        return self._grab(int(x), int(y), kind="manual", button=None)

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        x, y = int(x), int(y)
        if self.should_ignore(x, y):
            return

        now = time.monotonic()
        name = getattr(button, "name", str(button))
        last = self._last_click
        if (last and now - last[0] <= self.double_click_s and last[3] == name
                and math.hypot(x - last[1], y - last[2]) <= self.double_click_px):
            self._last_click = None          # a third click starts a new step
            self.on_double_click()
            return
        self._last_click = (now, x, y, name)

        try:
            self.on_capture(self._grab(x, y, kind="click", button=name))
        except Exception as exc:             # never let an error kill the hook
            print(f"[StepCapture] capture failed: {exc}")

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            factory = getattr(mss, "MSS", None) or mss.mss   # newer mss renamed it
            sct = self._local.sct = factory()
        return sct

    def _grab(self, x: int, y: int, *, kind: str, button: Optional[str]) -> Capture:
        sct = self._sct()
        index, mon = monitor_at(sct.monitors, x, y)
        shot = sct.grab(mon)
        return Capture(
            kind=kind,
            button=button,
            screen_x=x if kind == "click" else None,
            screen_y=y if kind == "click" else None,
            timestamp=datetime.now().astimezone(),
            monitor=index,
            monitor_rect={k: mon[k] for k in ("left", "top", "width", "height")},
            size=shot.size,
            bgra=bytes(shot.bgra),
            window_title=window_title_at(x, y),
        )


def monitor_at(monitors: list, x: int, y: int):
    """Return (1-based index, monitor dict) of the monitor containing (x, y).

    monitors[0] in mss is the virtual 'all screens' area, so it is skipped.
    Falls back to the primary monitor.
    """
    for i, m in enumerate(monitors[1:], start=1):
        if m["left"] <= x < m["left"] + m["width"] and m["top"] <= y < m["top"] + m["height"]:
            return i, m
    return 1, monitors[1]
