# StepCapture 1.0

Click-triggered screenshots for writing software tutorials and manuals.

Press **Start**, do the task as usual, press **Stop**. Every click becomes one step: a screenshot with a red ring where you clicked. Then press **Review** to reorder, crop, blur and describe the steps, and export the tutorial to **Word**, **Markdown** or **HTML**.

See [SPEC.md](SPEC.md) for the full specification and roadmap.

## Install

Requires Python 3.10+ with tkinter (included in the python.org installer for Windows and macOS).

```bash
cd stepcapture
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

## Run

```bash
python run.py
```

A small toolbar appears at the top-right of the screen.

| Control | What it does |
|---|---|
| **Start / Stop** (`Ctrl+Shift+R`) | Begin or end a session |
| **Snap** (`Ctrl+Shift+S`) | Manual screenshot without a click marker, e.g. after typing |
| **Review** | Open the editor on the last session |
| **Open folder** | Open the current session folder |

Options:

```
python run.py --output D:\Manuals\captures   # where sessions are saved (default ~/StepCapture)
python run.py --no-dedupe                    # keep repeated clicks on an unchanged screen
python run.py --no-hotkeys                   # turn off the global hotkeys
python run.py --review                       # open the editor on the latest session
python run.py --review path\to\session        # ...or on a specific one
python run.py --export path\to\session --format all   # docx, md and html, no window
```

## Review and export

| Action | How |
|---|---|
| Reorder | Drag a step in the list, the ↑/↓ buttons, or `Alt+↑/↓` |
| Delete | **Delete** button or `Delete` key (kept in `steps.json` under `deleted_steps`) |
| Undo | **Undo** or `Ctrl+Z` |
| Crop | Choose **Crop**, drag a box on the image; or **Crop around click**; **Reset crop** to undo it |
| Hide private details | Choose **Blur**, drag over names, emails, IDs; **Clear blur** removes them |
| Click ring | Untick **Click marker** to hide it on a step |
| Instruction | Type in the box under the image; `**Save**` becomes **Save** in the export |
| Title / introduction | **Title** box and **Introduction…** button at the top |
| Step without screenshot | **+ Text step** (e.g. "Type your password and press **Enter**") |
| Save | **Save** or `Ctrl+S` (the first save keeps `steps.original.json` as a backup) |
| Export | **Word**, **Markdown** or **HTML**; the file opens automatically |

Editing never changes the original screenshots, so you can always reset a crop or blur. Exports go to the session's `export/` folder:

- **Word (.docx)**: A4, one heading per step, screenshots sized to the page. Use Word's *Save as PDF* for a PDF.
- **Markdown**: `.md` file plus an `images/` folder, ready for GitHub or GitHub Pages.
- **HTML**: a single file with the images inside, easy to email or upload; prints cleanly to PDF.

## What you get

```
~/StepCapture/session_20261002_101530/
├── step_001.png ...   screenshots with the click ring
├── raw/               the same screenshots, unmarked
├── steps.json         metadata and your edits
├── tutorial.md        first draft, written when you press Stop
└── export/            Word, Markdown and HTML exports
```

Behaviour worth knowing:

- Only the monitor under the cursor is captured.
- A double-click is saved as one step with a double ring.
- Clicking again in the same spot on an unchanged screen is skipped as a duplicate (the counter shows how many).
- Clicks on the toolbar are ignored. On Windows 10 (2004+) and 11 the toolbar is also hidden from the screenshots.
- `steps.json` is saved after every step, so a crash keeps everything captured so far.
- Nothing you type is recorded.

## Platform notes

- **Windows**: main target, fully supported, captures the screen just *before* each click lands.
- **macOS**: grant **Screen Recording** and **Accessibility** permission to Terminal (or the built app) in System Settings → Privacy & Security, then restart it. Hotkeys are off by default on macOS; enable with `--hotkeys`. Install `pyobjc-framework-Cocoa` for window names. Screenshots may show the screen just *after* a click.
- **Linux**: X11 only (not Wayland). Install `xdotool` for window titles. Screenshots may show the screen just *after* a click.

## Build a Windows .exe

Double-click `build_exe.bat` (or run it from the activated venv). It installs PyInstaller and builds `dist\StepCapture.exe`, a single file that runs on Windows PCs without Python. Copy it anywhere, e.g. the Desktop.

The equivalent command, if you prefer to run it yourself:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name StepCapture --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 --collect-data docx run.py
```

The `--hidden-import` and `--collect-data` options matter: without them the exe starts but recording (pynput) or Word export (python-docx template) fails.

If the repository is on GitHub, pushing a tag such as `v1.0.0` runs `.github/workflows/build-windows.yml`, which builds the exe and attaches it to a GitHub Release.

## Tests

```bash
cd tests
python test_session.py
python test_export.py
```

## Version 2 roadmap (build it with Claude Code)

Open this folder in Claude Code and give it `SPEC.md` as context. Suggested prompts:

1. **AI step writer (Phase 2, optional; uses the paid Claude API)**: *"Add `stepcapture/writer.py`: read a session's steps.json, send each rendered screenshot plus its window title and click type to the Claude API, and fill `description` with one short imperative instruction. Add a 'Write with AI' button in the editor. Read the API key from the ANTHROPIC_API_KEY environment variable."*
2. **Callouts**: *"Add an Arrow and a Text-label tool to the editor, stored non-destructively in steps.json like crop and blurs, and rendered in every export."*
3. **Chrome extension (Phase 4)**: *"Create a Manifest V3 Chrome extension that records clicks with chrome.tabs.captureVisibleTab and writes the same steps.json schema (SPEC.md §8.1), adding the clicked element's text and label, so the editor can open its sessions."*
