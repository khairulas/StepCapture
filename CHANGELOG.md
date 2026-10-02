# Changelog

## 1.0.0 — 2 October 2026

First release.

**Recorder**
- Floating Start/Stop toolbar with Snap, Review and Open folder; hotkeys `Ctrl+Shift+R` and `Ctrl+Shift+S`.
- One screenshot per click, of the monitor under the cursor, with a red ring at the click point.
- Double-clicks merged into one step; repeated clicks on an unchanged screen skipped.
- Toolbar clicks ignored; toolbar hidden from screenshots on Windows 10 (2004+) and 11.
- High-DPI and multi-monitor aware; `steps.json` saved after every step.

**Review editor**
- Thumbnail list with drag-and-drop reordering, delete and undo.
- Crop (drag or *Crop around click*), blur sensitive areas, hide the click ring.
- Instruction text per step with `**bold**`, tutorial title and introduction, text-only steps.
- Non-destructive: original screenshots are never modified.

**Export**
- Word (.docx, A4), Markdown (+ images folder) and self-contained HTML.
- Headless export: `python run.py --export <session> --format all`.

**Planned for version 2**
- AI step writer using the Claude API (optional).
- Chrome extension that records the clicked element's label.
- Arrow and text callouts in the editor.
