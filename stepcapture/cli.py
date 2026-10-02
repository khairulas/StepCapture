"""Command line: recorder (default), --review editor, or headless --export."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .platform_utils import IS_MAC


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="stepcapture",
        description="Capture a screenshot on every click, for writing software tutorials.")
    parser.add_argument("-o", "--output", type=Path, default=Path.home() / "StepCapture",
                        help="folder for sessions (default: ~/StepCapture)")
    parser.add_argument("--no-dedupe", action="store_true",
                        help="keep repeated clicks on an unchanged screen")
    parser.add_argument("--no-hotkeys", action="store_true",
                        help="disable Ctrl+Shift+R / Ctrl+Shift+S")
    parser.add_argument("--hotkeys", action="store_true",
                        help="force-enable hotkeys (off by default on macOS)")
    parser.add_argument("--review", nargs="?", const="", metavar="SESSION",
                        help="open the review editor (latest session if no folder is given)")
    parser.add_argument("--export", metavar="SESSION",
                        help="export a session without opening any window")
    parser.add_argument("--format", default="docx", choices=["docx", "md", "html", "all"],
                        help="format for --export (default: docx)")
    parser.add_argument("--version", action="version", version=f"StepCapture {__version__}")
    args = parser.parse_args(argv)

    if args.export:
        from .exporters import FORMATS, export
        from .project import Project
        project = Project(args.export)
        for fmt in (FORMATS if args.format == "all" else (args.format,)):
            print(export(project, fmt))
        return

    if args.review is not None:
        from .editor import run_standalone
        from .project import latest_session
        folder = args.review or latest_session(args.output)
        if args.review == "" and folder is None:
            print(f"No sessions found in {args.output}; choose a folder in the editor.")
        run_standalone(folder, default_dir=args.output)
        return

    import tkinter as tk
    from .app import ToolbarApp
    hotkeys = args.hotkeys or (not args.no_hotkeys and not IS_MAC)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        ToolbarApp(args.output, dedupe=not args.no_dedupe, hotkeys=hotkeys).run()
    except tk.TclError as exc:
        sys.exit(f"Cannot open a window: {exc}")


if __name__ == "__main__":
    main()
