"""OS-specific helpers: DPI awareness, window titles, capture exclusion, opening folders."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

if IS_WIN:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    _user32.WindowFromPoint.argtypes = [_POINT]
    _user32.WindowFromPoint.restype = wintypes.HWND
    _user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND
    _user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.SetWindowDisplayAffinity.restype = wintypes.BOOL

    _GA_ROOT = 2
    _WDA_EXCLUDEFROMCAPTURE = 0x11


def enable_dpi_awareness() -> None:
    """Make Windows report real pixels so clicks, screenshots and Tk agree.

    Must be called before the Tk window is created.
    """
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _win_title(hwnd) -> str:
    if not hwnd:
        return ""
    length = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_title_at(x: int, y: int) -> str:
    """Title of the top-level window under (x, y); falls back to the active window."""
    try:
        if IS_WIN:
            hwnd = _user32.WindowFromPoint(_POINT(int(x), int(y)))
            root = _user32.GetAncestor(hwnd, _GA_ROOT) if hwnd else None
            return _win_title(root or _user32.GetForegroundWindow())
        if IS_MAC:
            from AppKit import NSWorkspace  # type: ignore  (pyobjc-framework-Cocoa)

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return str(app.localizedName()) if app else ""
        out = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=0.5,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def exclude_window_from_capture(tk_root) -> bool:
    """Hide the toolbar from screenshots (Windows 10 2004+). Returns True on success."""
    if not IS_WIN:
        return False
    try:
        hwnd = _user32.GetParent(tk_root.winfo_id()) or tk_root.winfo_id()
        return bool(_user32.SetWindowDisplayAffinity(hwnd, _WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


def open_folder(path) -> None:
    path = str(path)
    try:
        if IS_WIN:
            os.startfile(path)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
