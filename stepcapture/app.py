"""Floating Start/Stop toolbar (tkinter) that drives the recorder."""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path

from . import __version__
from .platform_utils import IS_MAC, enable_dpi_awareness, exclude_window_from_capture, open_folder
from .recorder import Recorder
from .session import Session

BG = "#1f2328"
FG = "#e6edf3"
MUTED = "#8b949e"
RED = "#e5484d"
GREEN = "#3fb950"
BTN = "#30363d"
BTN_ACTIVE = "#484f58"

HOTKEY_TOGGLE = "<ctrl>+<shift>+r"
HOTKEY_SNAP = "<ctrl>+<shift>+s"


class ToolbarApp:
    def __init__(self, output_dir: Path, dedupe: bool = True, hotkeys: bool = True):
        self.output_dir = output_dir
        self.dedupe = dedupe

        enable_dpi_awareness()                      # before Tk exists
        self.root = tk.Tk()
        self.root.title(f"StepCapture {__version__}")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.work_q: queue.Queue = queue.Queue()    # to worker thread
        self.ui_q: queue.Queue = queue.Queue()      # to Tk thread
        self.rect = (0, 0, 0, 0)                     # toolbar area, screen coords
        self.session_dir: Path | None = None
        self.step_count = 0
        self.skipped = 0

        self._build_ui()
        self.recorder = Recorder(
            on_capture=lambda cap: self.work_q.put(("capture", cap)),
            on_double_click=lambda: self.work_q.put(("double",)),
            should_ignore=self._inside_toolbar,
        )
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

        self.root.update_idletasks()
        self.hidden_from_capture = exclude_window_from_capture(self.root)
        self._place_top_right()
        self._set_status("Ready. Press Start, then click through your task."
                         + ("" if self.hidden_from_capture else
                            "\nNote: this toolbar may appear in screenshots."))

        self.hotkeys = None
        if hotkeys:
            self._start_hotkeys()

        self.root.after(100, self._poll)

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        pad = {"padx": 6, "pady": 6}
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 2))

        self.dot = tk.Label(bar, text="●", fg=MUTED, bg=BG, font=("Segoe UI", 14))
        self.dot.pack(side="left")

        def button(text, cmd, **kw):
            b = tk.Button(bar, text=text, command=cmd, bg=BTN, fg=FG, relief="flat",
                          activebackground=BTN_ACTIVE, activeforeground=FG,
                          font=("Segoe UI", 10, "bold"), cursor="hand2", bd=0, **kw)
            b.pack(side="left", **pad)
            return b

        self.btn_toggle = button("Start", self.toggle, width=7)
        self.btn_snap = button("Snap", self.snap, width=6, state="disabled")
        self.btn_review = button("Review", self.review)
        self.btn_folder = button("Open folder", self.open_session, state="disabled")

        self.lbl_count = tk.Label(bar, text="0 steps", fg=FG, bg=BG, font=("Segoe UI", 10))
        self.lbl_count.pack(side="left", padx=(6, 4))

        self.lbl_status = tk.Label(self.root, text="", fg=MUTED, bg=BG, justify="left",
                                   anchor="w", font=("Segoe UI", 9), wraplength=420)
        self.lbl_status.pack(fill="x", padx=12, pady=(0, 8))

    def _place_top_right(self):
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        x = self.root.winfo_screenwidth() - w - 40
        self.root.geometry(f"+{max(x, 0)}+40")

    def _set_status(self, text, color=MUTED):
        self.lbl_status.config(text=text, fg=color)

    def _refresh_count(self):
        extra = f" ({self.skipped} duplicate{'s' if self.skipped != 1 else ''} skipped)" if self.skipped else ""
        self.lbl_count.config(text=f"{self.step_count} step{'s' if self.step_count != 1 else ''}{extra}")

    # -------------------------------------------------------------- actions
    def toggle(self):
        if self.recorder.running:
            self.stop()
        else:
            self.start()

    def start(self):
        self.step_count = self.skipped = 0
        self._refresh_count()
        self.work_q.put(("start",))
        self.recorder.start()
        self.dot.config(fg=RED)
        self.btn_toggle.config(text="Stop", bg=RED, activebackground=RED)
        self.btn_snap.config(state="normal")
        self._set_status("Recording… every click is a step. "
                         "Ctrl+Shift+S = manual snap, Ctrl+Shift+R = stop.", RED)

    def stop(self):
        self.recorder.stop()
        self.work_q.put(("stop",))
        self.dot.config(fg=MUTED)
        self.btn_toggle.config(text="Start", bg=BTN, activebackground=BTN_ACTIVE)
        self.btn_snap.config(state="disabled")
        self._set_status("Saving…")

    def snap(self):
        if not self.recorder.running:
            return
        try:
            self.work_q.put(("capture", self.recorder.snapshot()))
        except Exception as exc:
            self._set_status(f"Snap failed: {exc}", RED)

    def open_session(self):
        if self.session_dir:
            open_folder(self.session_dir)

    def review(self):
        """Open the editor on the last session (or let the user pick one)."""
        from .editor import Editor
        from .project import latest_session
        if self.recorder.running:
            self.stop()
        folder = self.session_dir or latest_session(self.output_dir)
        Editor(self.root, folder, default_dir=self.output_dir)

    def quit(self):
        if self.recorder.running:
            self.stop()
        self.work_q.put(("quit",))
        self.worker.join(timeout=10)
        if self.hotkeys:
            self.hotkeys.stop()
        self.root.destroy()

    # --------------------------------------------------------------- hotkeys
    def _start_hotkeys(self):
        try:
            from pynput import keyboard
            self.hotkeys = keyboard.GlobalHotKeys({
                HOTKEY_TOGGLE: lambda: self.ui_q.put(("toggle",)),
                HOTKEY_SNAP: lambda: self.ui_q.put(("snap",)),
            })
            self.hotkeys.start()
        except Exception as exc:
            self.hotkeys = None
            print(f"[StepCapture] hotkeys unavailable: {exc}")

    # ------------------------------------------------------- thread plumbing
    def _inside_toolbar(self, x: int, y: int) -> bool:
        left, top, right, bottom = self.rect
        return left - 4 <= x <= right + 4 and top - 4 <= y <= bottom + 4

    def _poll(self):
        """Runs on the Tk thread: refresh toolbar rect, apply worker/hotkey messages."""
        try:
            x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
            # include the title bar area above the client region
            self.rect = (x, y - 40, x + self.root.winfo_width(), y + self.root.winfo_height())
        except tk.TclError:
            return
        while True:
            try:
                msg = self.ui_q.get_nowait()
            except queue.Empty:
                break
            kind = msg[0]
            if kind == "toggle":
                self.toggle()
            elif kind == "snap":
                self.snap()
            elif kind == "started":
                self.session_dir = msg[1]
                self.btn_folder.config(state="normal")
            elif kind == "step":
                self.step_count = msg[1]
                self._refresh_count()
            elif kind == "skipped":
                self.skipped = msg[1]
                self._refresh_count()
            elif kind == "stopped":
                path, n = msg[1], msg[2]
                self._set_status(f"Saved {n} step{'s' if n != 1 else ''} to:\n{path}\n"
                                 "Press Review to edit and export.", GREEN)
            elif kind == "error":
                self._set_status(msg[1], RED)
        self.root.after(150, self._poll)

    def _worker(self):
        """Owns the Session: saves images and metadata off the UI/hook threads."""
        session: Session | None = None
        while True:
            msg = self.work_q.get()
            kind = msg[0]
            try:
                if kind == "start":
                    session = Session(self.output_dir, dedupe=self.dedupe)
                    self.ui_q.put(("started", session.dir))
                elif kind == "capture" and session:
                    step = session.add_capture(msg[1])
                    if step:
                        self.ui_q.put(("step", len(session.steps)))
                    else:
                        self.ui_q.put(("skipped", session.skipped))
                elif kind == "double" and session:
                    session.mark_last_double_click()
                elif kind == "stop" and session:
                    path = session.finish()
                    self.ui_q.put(("stopped", path, len(session.steps)))
                    session = None
                elif kind == "quit":
                    if session:
                        session.finish()
                    return
            except Exception as exc:
                self.ui_q.put(("error", f"Error: {exc}"))

    def run(self):
        self.root.mainloop()


def main(argv=None):
    from .cli import main as cli_main
    cli_main(argv)


if __name__ == "__main__":
    main()
