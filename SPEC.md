# StepCapture — Specification

**Version:** 1.0 (released 2 October 2026)  
**Author:** Dr. Khairul Anwar Sedek  
**Date:** 2 October 2026

## 1. Purpose

StepCapture records a software walkthrough as a sequence of screenshots instead of a video. The user presses **Start**, works through the task normally, and presses **Stop**. Each mouse click produces one screenshot with the click point marked, plus metadata. The output folder is the raw material for a software tutorial or user manual, written by hand or drafted by AI.

## 2. Goals and non-goals

**Goals**

- One screenshot per meaningful action, with no manual cropping or sorting needed.
- Works with any desktop software (IDE, Docker Desktop, terminal, browser, office apps).
- Output is open and simple: PNG files plus a `steps.json` file that later tools (AI writer, exporter, Chrome extension) share.
- Runs locally. Nothing leaves the computer.

**Non-goals for the MVP**

- Video recording.
- Recording what the user types (privacy risk: passwords, personal data).
- Mobile capture (use the phone's screen recorder; frame extraction is a later option).

## 3. Phases

Version 1.0 ships Phases 1 and 3. Phases 2 and 4 are planned for version 2.

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Desktop recorder: Start/Stop toolbar, click capture, markers, de-duplication, `steps.json`, Markdown draft | **Done (v1.0)** |
| 2 | AI step writer (optional): send each screenshot + metadata to the Claude API (vision) to write one instruction per step | Version 2 |
| 3 | Review editor + exporter: reorder/delete/crop/blur steps, edit text, export to Word (.docx), Markdown, HTML | **Done (v1.0)** |
| 4 | Chrome extension: web-only recorder that also records the clicked element's label, writing the same `steps.json` format | Version 2 |

## 4. Users and use cases

- **Lecturer** writing a lab manual (e.g., "Starting the Hadoop containers in Docker Desktop").
- **Developer** documenting how to use a web system for end users.
- **Student** documenting their FYP system for the user manual chapter of a report.

## 5. Functional requirements (Phase 1)

| ID | Requirement |
|---|---|
| FR-1 | A small, always-on-top floating toolbar with **Start/Stop**, **Snap**, **Open folder**, a step counter, and a status line. |
| FR-2 | **Start** creates a new session folder named `session_YYYYMMDD_HHMMSS` inside the output directory. |
| FR-3 | While recording, every mouse button press anywhere on screen triggers a capture of the monitor under the cursor. On Windows the capture happens inside the low-level mouse hook, before the click is delivered, so the image shows the screen *before* the click takes effect (the state the reader sees when following the step). On Linux and macOS the click is reported asynchronously, so the image may already show the result of a fast-reacting click; the user can delete such a step in the editor or take a manual Snap instead. |
| FR-4 | Clicks on the StepCapture toolbar itself are ignored. |
| FR-5 | Each capture is saved twice: the raw image (`raw/step_NNN.png`) and an annotated copy (`step_NNN.png`) with a red ring at the click point. |
| FR-6 | Two clicks within 0.4 s and 6 px of each other are merged into one **double-click** step (double ring marker); no extra screenshot is saved. |
| FR-7 | De-duplication: a click is skipped when the screen is at least 99% identical to the previous step **and** the click is within 40 px of the previous click. It can be turned off with `--no-dedupe`. |
| FR-8 | **Snap** (button or hotkey) takes a manual screenshot without a click marker, for steps that involve typing or waiting. |
| FR-9 | Global hotkeys: `Ctrl+Shift+R` start/stop, `Ctrl+Shift+S` snap. Can be disabled with `--no-hotkeys`. |
| FR-10 | For each step, record: index, type, timestamp, elapsed seconds, mouse button, screen coordinates, image coordinates, monitor number, and the title of the window under the cursor. |
| FR-11 | `steps.json` is rewritten after every step, so a crash loses at most the step being saved. |
| FR-12 | **Stop** writes `tutorial.md`, a draft with one section per step (action line + image), ready to edit or feed to Phase 2. |
| FR-13 | On Windows, the toolbar is excluded from screenshots using the OS display-affinity setting. On other systems it may appear; the status line says so. |

## 5A. Functional requirements (Phase 3: review editor and export)

All edits are **non-destructive**: the raw screenshots are never changed. Edits are stored in `steps.json` and applied when the editor shows a step or when exporting.

| ID | Requirement |
|---|---|
| ED-1 | Open the editor from the toolbar (**Review**, after a session), from `python run.py --review [folder]` (latest session if omitted), or with **Open…** inside the editor. |
| ED-2 | Left panel: list of steps with thumbnails and their instruction text. |
| ED-3 | Reorder steps by drag-and-drop, the ↑/↓ buttons, or `Alt+↑/↓`. |
| ED-4 | Delete a step (button or `Delete` key). Deleted steps are kept under `deleted_steps` in `steps.json`, never erased from disk. |
| ED-5 | Undo (`Ctrl+Z`) for delete, reorder, crop, blur, marker and insert operations. |
| ED-6 | **Crop**: drag a rectangle on the preview. **Crop around click** sets a crop centred on the click marker (55% of screen size). **Reset crop** removes it. The area outside the crop is dimmed in the preview. |
| ED-7 | **Blur**: drag rectangles over sensitive areas (names, emails, IDs); they are pixelated in the preview and in every export. **Clear blur** removes them. |
| ED-8 | Toggle the click marker per step. |
| ED-9 | Edit each step's instruction in a text box. `**text**` is shown in bold in all exports (e.g., "Click **Save**"). An empty instruction falls back to the auto-generated placeholder. |
| ED-10 | Edit the tutorial **title** and an **introduction** paragraph. |
| ED-11 | Insert a **text-only step** (no image) for actions such as typing a password or waiting for a process. |
| ED-12 | **Save** (`Ctrl+S`) writes `steps.json` (a one-time backup `steps.original.json` is kept). Closing with unsaved changes asks to save. |
| ED-13 | **Export** to Word (.docx), Markdown (.md + images folder) and HTML (one self-contained file), saved in the session's `export/` folder and opened automatically. |
| ED-14 | Exports are also available without the UI: `python run.py --export <folder> --format docx|md|html|all`. |

### Export layout

- Title, date, and introduction, then one section per step: **Step N** heading, instruction, screenshot.
- Images are rendered as: raw → blur → click marker → crop → thin grey border.
- Word: A4, 2 cm margins, images fit the page width (max 19 cm tall), heading and text kept on the same page as their image.
- HTML: single file with embedded images; prints cleanly (no step split across pages).
- To get a PDF, open the Word file and use **Save as PDF**, or print the HTML page to PDF.

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Capture must not noticeably delay the user's click: the click handler only grabs pixels (~20–60 ms); PNG encoding and annotation run on a background worker thread. |
| NFR-2 | High-DPI correct: on Windows the process is per-monitor DPI aware; on macOS the marker position is scaled from points to pixels. |
| NFR-3 | Multi-monitor: only the monitor under the cursor is captured. |
| NFR-4 | Dependencies limited to `mss`, `pynput`, `Pillow`, and the standard library (`tkinter` for the UI). |
| NFR-5 | Packaged as a single Windows `.exe` with PyInstaller for non-technical users. |

## 7. Platform support

| Platform | Support |
|---|---|
| Windows 10 (2004+) / 11 | Primary target. Full support, toolbar hidden from captures. |
| macOS 12+ | Works after granting **Screen Recording** and **Accessibility** permissions to the terminal or app. Hotkeys off by default (pynput keyboard hooks can conflict with Tk on macOS). Window title is the front app name (needs `pyobjc-framework-Cocoa`). |
| Linux (X11) | Works. Window title needs `xdotool`. **Wayland is not supported** (global input hooks and screen grabs are blocked by design). |

## 8. Output format

```
session_20261002_101530/
├── step_001.png          annotated (click ring)
├── step_002.png
├── raw/
│   ├── step_001.png      unmarked original
│   └── step_002.png
├── steps.json            metadata (schema below)
└── tutorial.md           Markdown draft
```

### 8.1 `steps.json` schema (version 1)

This schema is the contract shared by every StepCapture component (desktop recorder, Chrome extension, AI writer, exporter).

```json
{
  "schema_version": 1,
  "source": "desktop",
  "session_id": "session_20261002_101530",
  "title": "",
  "started_at": "2026-10-02T10:15:30+08:00",
  "ended_at": "2026-10-02T10:18:02+08:00",
  "platform": "Windows-11-10.0.22631-SP0",
  "steps": [
    {
      "index": 1,
      "type": "click",
      "timestamp": "2026-10-02T10:15:34.120+08:00",
      "elapsed_s": 4.12,
      "button": "left",
      "screen_x": 812, "screen_y": 455,
      "image_x": 812, "image_y": 455,
      "monitor": 1,
      "window_title": "Docker Desktop",
      "image": "step_001.png",
      "raw_image": "raw/step_001.png",
      "description": ""
    }
  ]
}
```

- `type`: `click`, `double_click`, or `manual`.
- `button`: `left`, `right`, `middle`, or `null` for manual snaps.
- `image_x/image_y`: click position in image pixels (`null` for manual snaps).
- `description`: the instruction text; empty means "use the placeholder". Filled in the editor (or by the optional AI writer).

Fields added by the editor (all optional, so Phase 1 files stay valid):

| Field | Level | Meaning |
|---|---|---|
| `intro` | session | Introduction paragraph |
| `crop` | step | `[x0, y0, x1, y1]` in raw-image pixels |
| `blurs` | step | list of `[x0, y0, x1, y1]` rectangles to pixelate |
| `show_marker` | step | `false` hides the click ring |
| `deleted_steps` | session | steps removed in the editor (kept for recovery) |

A text-only step has `"type": "text"` and `null` image fields.
- The Chrome extension (Phase 4) adds an optional `element` object (`tag`, `text`, `label`, `selector`) and `url`.

## 9. Privacy and safety

- No keystroke content is ever recorded.
- All files stay in the local output folder.
- The red **Recording** status makes it obvious when capture is active.
- Users should close password managers, chats, and email before recording. The editor's blur tool hides anything that slipped through; blur is applied to every export.

## 10. Acceptance criteria (Phase 1)

1. Starting, clicking through 10 distinct screens, and stopping produces 10 annotated PNGs, 10 raw PNGs, a valid `steps.json` with 10 steps, and `tutorial.md`.
2. The red ring is drawn on the clicked spot on a 150%-scaled Windows display and on a second monitor.
3. Double-clicking a desktop icon produces one `double_click` step.
4. Clicking twice on the same unchanged spot produces one step when de-duplication is on, two when off.
5. Clicking the toolbar's buttons produces no steps; on Windows the toolbar is absent from the images.
6. Killing the app mid-session leaves a readable `steps.json` covering all completed steps.

**Phase 3**

7. In the editor, reordering, deleting, cropping, blurring and hiding a marker are reflected in the thumbnail, the preview and every export; `Ctrl+Z` reverses each one.
8. After **Save**, reopening the session shows the same order, text and edits; the raw screenshots are unchanged.
9. A Word export of a 20-step session opens in Microsoft Word with one heading, instruction and screenshot per step, none split across pages, and `**bold**` shown as bold.
10. The HTML export is a single file that displays all images when opened offline.

## 11. Version 2 ideas

- Phase 2 prompt: *"You are writing a software manual. Given this screenshot, the click position marked in red, and the window title, write one short imperative instruction for this step."*
- Arrows and text callouts drawn on screenshots.
- Pause/resume, and a "this step needs typing" annotation.
- Export straight to the course website (GitHub Pages) as Markdown.
