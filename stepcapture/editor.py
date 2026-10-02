"""Review editor: reorder, delete, crop, blur and describe steps, then export."""
from __future__ import annotations

import copy
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageTk

from .exporters import export
from .platform_utils import open_folder
from .project import Project
from .render import clamp_box, crop_around_click, render_step
from .session import describe

CANVAS_BG = "#2b2f36"
CROP_COLOR = "#ffd33d"
BLUR_COLOR = "#58a6ff"
TEXT_STEP_BG = (234, 238, 242)
MAX_UNDO = 50


class Editor:
    def __init__(self, master, folder=None, *, on_close=None, auto_open_exports=True,
                 default_dir: Optional[Path] = None):
        self.master = master
        self.on_close = on_close
        self.auto_open = auto_open_exports
        self.default_dir = Path(default_dir or Path.home() / "StepCapture")

        self.win = tk.Toplevel(master)
        self.win.title("StepCapture — Review")
        self.win.geometry("1280x820")
        self.win.minsize(900, 560)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        try:
            ui = max(1.0, float(self.win.tk.call("tk", "scaling")) / 1.3333)
        except Exception:
            ui = 1.0
        self.thumb_size = (int(128 * ui), int(72 * ui))

        self.project: Optional[Project] = None
        self.items: dict[str, dict] = {}        # tree iid -> step dict
        self.thumb_cache: dict[str, ImageTk.PhotoImage] = {}
        self.undo_stack: list = []
        self.dirty = False
        self.current: Optional[str] = None
        self._next_iid = 0
        self._loading = False
        self._full = None                        # (signature, PIL image) of current step
        self._photo = None
        self._geom = None                        # (scale, ox, oy, W, H)
        self._drag = None                        # canvas drag start
        self._drag_rect = None
        self._tree_drag = None                   # [iid, moved]
        self._redraw_job = None

        self._build()
        self._bind()
        if folder:
            self.load(folder)
        else:
            self._status("Open a session folder to start (File: Open…).")

    # ================================================================== UI
    def _build(self):
        style = ttk.Style(self.win)
        style.configure("Steps.Treeview", rowheight=self.thumb_size[1] + 10)

        top = ttk.Frame(self.win, padding=(8, 8, 8, 6))
        top.pack(fill="x")
        ttk.Button(top, text="Open…", command=self.open_dialog).pack(side="left")
        ttk.Button(top, text="Save", command=self.save).pack(side="left", padx=(4, 14))
        ttk.Label(top, text="Title").pack(side="left")
        self.title_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.title_var, width=42).pack(side="left", padx=6)
        self.title_var.trace_add("write", lambda *_: self._mark_dirty())
        ttk.Button(top, text="Introduction…", command=self.edit_intro).pack(side="left")

        for label, fmt in (("HTML", "html"), ("Markdown", "md"), ("Word", "docx")):
            ttk.Button(top, text=label, command=lambda f=fmt: self.export(f)).pack(side="right", padx=2)
        ttk.Label(top, text="Export:").pack(side="right", padx=(14, 4))

        self.status_lbl = ttk.Label(self.win, anchor="w", padding=(10, 2, 10, 6))
        self.status_lbl.pack(side="bottom", fill="x")

        paned = ttk.PanedWindow(self.win, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8)

        # ---- left: step list
        left = ttk.Frame(paned)
        paned.add(left, weight=0)
        btns = ttk.Frame(left)
        btns.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(btns, text="↑", width=3, command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(btns, text="↓", width=3, command=lambda: self.move(1)).pack(side="left", padx=2)
        ttk.Button(btns, text="Delete", command=self.delete).pack(side="left", padx=2)
        ttk.Button(btns, text="+ Text step", command=self.add_text_step).pack(side="left", padx=2)
        ttk.Button(btns, text="Undo", command=self.undo).pack(side="right")

        self.tree = ttk.Treeview(left, show="tree", selectmode="browse", style="Steps.Treeview")
        self.tree.column("#0", width=self.thumb_size[0] + 230, stretch=True)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # ---- right: tools, preview, instruction
        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        paned.add(right, weight=1)

        tools = ttk.Frame(right)
        tools.pack(fill="x", pady=(0, 6))
        ttk.Label(tools, text="Drag on the image to").pack(side="left")
        self.mode = tk.StringVar(value="crop")
        ttk.Radiobutton(tools, text="Crop", variable=self.mode, value="crop").pack(side="left", padx=(6, 2))
        ttk.Radiobutton(tools, text="Blur", variable=self.mode, value="blur").pack(side="left", padx=2)
        ttk.Separator(tools, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(tools, text="Crop around click", command=self.crop_click).pack(side="left")
        ttk.Button(tools, text="Reset crop", command=self.reset_crop).pack(side="left", padx=4)
        ttk.Button(tools, text="Clear blur", command=self.clear_blur).pack(side="left")
        self.marker_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tools, text="Click marker", variable=self.marker_var,
                        command=self.toggle_marker).pack(side="left", padx=12)

        bottom = ttk.Frame(right)
        bottom.pack(side="bottom", fill="x", pady=(6, 4))
        ttk.Label(bottom, text="Instruction   (write **Save** to show Save in bold)").pack(anchor="w")
        self.text = tk.Text(bottom, height=4, wrap="word", undo=True, font=("Segoe UI", 11),
                            padx=8, pady=6, relief="solid", borderwidth=1)
        self.text.pack(fill="x", pady=(2, 0))

        self.canvas = tk.Canvas(right, bg=CANVAS_BG, highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

    def _bind(self):
        t = self.tree
        t.bind("<<TreeviewSelect>>", self._on_select)
        t.bind("<Delete>", lambda e: self.delete())
        t.bind("<Alt-Up>", lambda e: (self.move(-1), "break")[1])
        t.bind("<Alt-Down>", lambda e: (self.move(1), "break")[1])
        t.bind("<ButtonPress-1>", self._tree_press, add="+")
        t.bind("<B1-Motion>", self._tree_motion, add="+")
        t.bind("<ButtonRelease-1>", self._tree_release, add="+")

        c = self.canvas
        c.bind("<ButtonPress-1>", self._canvas_press)
        c.bind("<B1-Motion>", self._canvas_motion)
        c.bind("<ButtonRelease-1>", self._canvas_release)
        c.bind("<Configure>", lambda e: self._schedule_redraw())

        self.text.bind("<KeyRelease>", self._text_changed)
        self.win.bind("<Control-s>", lambda e: (self.save(), "break")[1])
        self.win.bind("<Control-z>", self._undo_key)
        self.win.bind("<Command-s>", lambda e: (self.save(), "break")[1])

    def _status(self, msg: str):
        self.status_lbl.config(text=msg)

    def _mark_dirty(self, value: bool = True):
        if self._loading:
            return
        self.dirty = value
        name = self.project.folder.name if self.project else "Review"
        self.win.title(f"{'● ' if value else ''}StepCapture — {name}")

    # ============================================================ loading
    def open_dialog(self):
        start = self.default_dir if self.default_dir.exists() else Path.home()
        folder = filedialog.askdirectory(parent=self.win, initialdir=str(start),
                                         title="Choose a session folder (contains steps.json)")
        if folder:
            self.load(folder)

    def load(self, folder) -> bool:
        if self.dirty and not self._confirm_discard():
            return False
        try:
            project = Project(folder)
        except Exception as exc:
            messagebox.showerror("Cannot open session", str(exc), parent=self.win)
            return False
        self._loading = True
        self.project = project
        self.undo_stack.clear()
        self.title_var.set(project.title)
        self._rebuild([(self._new_iid(), s) for s in project.steps])
        self._loading = False
        self._mark_dirty(False)
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
        self._status(f"{len(kids)} steps · drag or Alt+↑/↓ to reorder · Delete removes · "
                     f"Ctrl+Z undo · Ctrl+S save")
        return True

    def _new_iid(self) -> str:
        self._next_iid += 1
        return f"s{self._next_iid}"

    def _rebuild(self, pairs, select: Optional[str] = None):
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        for iid, step in pairs:
            self.items[iid] = step
            self.tree.insert("", "end", iid=iid, image=self._thumb(step))
        self._renumber()
        if select and select in self.items:
            self.tree.selection_set(select)
            self.tree.see(select)
        elif not pairs:
            self._show_step(None)

    def _renumber(self):
        for n, iid in enumerate(self.tree.get_children(), start=1):
            self.tree.item(iid, text=self._label(n, self.items[iid]))

    @staticmethod
    def _label(n: int, step: dict) -> str:
        text = Project.instruction(step).replace("\n", " ").replace("**", "").replace("*", "")
        if len(text) > 44:
            text = text[:43] + "…"
        return f"  {n}.  {text}"

    def _signature(self, step: dict) -> str:
        keys = ("raw_image", "image", "crop", "blurs", "show_marker", "type", "image_x", "image_y")
        return json.dumps({k: step.get(k) for k in keys}, sort_keys=True)

    def _thumb(self, step: dict) -> ImageTk.PhotoImage:
        sig = self._signature(step)
        if sig in self.thumb_cache:
            return self.thumb_cache[sig]
        tw, th = self.thumb_size
        canvas = Image.new("RGB", (tw, th), TEXT_STEP_BG)
        img = render_step(self.project.image_path(step), step) if self.project else None
        if img is None:
            d = ImageDraw.Draw(canvas)
            try:
                d.text((tw // 2, th // 2), "Text step", fill=(90, 99, 110), anchor="mm")
            except (ValueError, TypeError):
                d.text((8, th // 2 - 6), "Text step", fill=(90, 99, 110))
        else:
            img.thumbnail((tw, th), Image.BILINEAR)
            canvas.paste(img, ((tw - img.width) // 2, (th - img.height) // 2))
        photo = ImageTk.PhotoImage(canvas, master=self.win)
        self.thumb_cache[sig] = photo
        return photo

    # ========================================================== selection
    def _on_select(self, _e=None):
        sel = self.tree.selection()
        self._show_step(sel[0] if sel else None)

    def _show_step(self, iid: Optional[str]):
        self.current = iid
        self._full = None
        self.text.delete("1.0", "end")
        if iid:
            step = self.items[iid]
            self.text.insert("1.0", Project.instruction(step))
            self.marker_var.set(step.get("show_marker", True))
        self.text.edit_reset()
        self._redraw()

    def _step(self) -> Optional[dict]:
        return self.items.get(self.current) if self.current else None

    # ============================================================ preview
    def _schedule_redraw(self):
        if self._redraw_job:
            self.win.after_cancel(self._redraw_job)
        self._redraw_job = self.win.after(60, self._redraw)

    def _full_image(self, step: dict) -> Optional[Image.Image]:
        sig = self._signature(step)
        if self._full and self._full[0] == sig:
            return self._full[1]
        img = render_step(self.project.image_path(step), step, apply_crop=False)
        self._full = (sig, img)
        return img

    def _redraw(self):
        self._redraw_job = None
        c = self.canvas
        c.delete("all")
        self._geom = None
        step = self._step()
        cw, ch = c.winfo_width(), c.winfo_height()
        if step is None or cw < 20 or ch < 20:
            return
        full = self._full_image(step)
        if full is None:
            c.create_text(cw // 2, ch // 2, fill="#c9d1d9", font=("Segoe UI", 14),
                          text="Text-only step (no screenshot).\nWrite the instruction below.",
                          justify="center")
            return

        img = full
        crop = step.get("crop")
        if crop:
            box = clamp_box(crop, full.size)
            img = ImageEnhance.Brightness(full).enhance(0.35)
            img.paste(full.crop(box), box[:2])

        s = min((cw - 24) / img.width, (ch - 24) / img.height, 1.0)
        w, h = max(1, int(img.width * s)), max(1, int(img.height * s))
        ox, oy = (cw - w) // 2, (ch - h) // 2
        self._photo = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS), master=self.win)
        c.create_image(ox, oy, image=self._photo, anchor="nw")
        self._geom = (s, ox, oy, full.width, full.height)

        def rect(box, color, dash):
            x0, y0, x1, y1 = clamp_box(box, full.size)
            c.create_rectangle(ox + x0 * s, oy + y0 * s, ox + x1 * s, oy + y1 * s,
                               outline=color, width=2, dash=dash)
        if crop:
            rect(crop, CROP_COLOR, (8, 4))
        for b in step.get("blurs") or []:
            rect(b, BLUR_COLOR, (4, 3))

    # ---- drag a rectangle on the preview
    def _canvas_press(self, e):
        if not self._geom:
            return
        self._drag = (e.x, e.y)
        color = CROP_COLOR if self.mode.get() == "crop" else BLUR_COLOR
        self._drag_rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline=color,
                                                       width=2, dash=(6, 3))

    def _canvas_motion(self, e):
        if self._drag_rect:
            self.canvas.coords(self._drag_rect, *self._drag, e.x, e.y)

    def _canvas_release(self, e):
        if not self._drag_rect or not self._geom:
            return
        self.canvas.delete(self._drag_rect)
        self._drag_rect = None
        s, ox, oy, W, H = self._geom
        (sx, sy), self._drag = self._drag, None
        box = clamp_box(((sx - ox) / s, (sy - oy) / s, (e.x - ox) / s, (e.y - oy) / s), (W, H))
        if box[2] - box[0] < 12 or box[3] - box[1] < 12:
            return                                   # a stray click, not a drag
        step = self._step()
        self._push_undo()
        if self.mode.get() == "crop":
            step["crop"] = list(box)
        else:
            step.setdefault("blurs", []).append(list(box))
        self._changed()

    # ============================================================== edits
    def _changed(self, iid: Optional[str] = None):
        iid = iid or self.current
        if iid:
            self.tree.item(iid, image=self._thumb(self.items[iid]))
        self._mark_dirty()
        self._redraw()

    def crop_click(self):
        step = self._step()
        full = self._full_image(step) if step else None
        if full is None:
            return
        self._push_undo()
        step["crop"] = crop_around_click(step, full.size)
        self._changed()

    def reset_crop(self):
        step = self._step()
        if step and step.get("crop"):
            self._push_undo()
            step.pop("crop", None)
            self._changed()

    def clear_blur(self):
        step = self._step()
        if step and step.get("blurs"):
            self._push_undo()
            step.pop("blurs", None)
            self._changed()

    def toggle_marker(self):
        step = self._step()
        if not step:
            return
        self._push_undo()
        step["show_marker"] = bool(self.marker_var.get())
        self._changed()

    def _text_changed(self, _e=None):
        step = self._step()
        if not step:
            return
        content = self.text.get("1.0", "end-1c").strip()
        new = "" if content == describe(step) else content
        if new != (step.get("description") or ""):
            step["description"] = new
            self.tree.item(self.current, text=self._label(self.tree.index(self.current) + 1, step))
            self._mark_dirty()

    def move(self, delta: int):
        iid = self.current
        if not iid:
            return
        idx = self.tree.index(iid)
        new = idx + delta
        if not 0 <= new < len(self.tree.get_children()):
            return
        self._push_undo()
        self.tree.move(iid, "", new)
        self.tree.see(iid)
        self._renumber()
        self._mark_dirty()

    def delete(self):
        iid = self.current
        if not iid:
            return
        self._push_undo()
        idx = self.tree.index(iid)
        self.project.deleted.append(self.items.pop(iid))
        self.tree.delete(iid)
        self._renumber()
        kids = self.tree.get_children()
        if kids:
            nxt = kids[min(idx, len(kids) - 1)]
            self.tree.selection_set(nxt)
            self.tree.focus(nxt)
        else:
            self._show_step(None)
        self._mark_dirty()
        self._status(f"Step deleted ({len(kids)} left). Ctrl+Z to undo.")

    def add_text_step(self):
        if not self.project:
            return
        self._push_undo()
        step = Project.new_text_step()
        iid = self._new_iid()
        self.items[iid] = step
        pos = self.tree.index(self.current) + 1 if self.current else "end"
        self.tree.insert("", pos, iid=iid, image=self._thumb(step))
        self._renumber()
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self._mark_dirty()
        self._status("Text step added. Type the instruction below.")
        self.win.after(50, self._focus_text)

    def _focus_text(self):
        self.text.focus_set()
        self.text.tag_add("sel", "1.0", "end-1c")

    # ---- drag-and-drop in the list
    def _tree_press(self, e):
        iid = self.tree.identify_row(e.y)
        self._tree_drag = [iid, False] if iid else None

    def _tree_motion(self, e):
        if not self._tree_drag:
            return
        iid, moved = self._tree_drag
        target = self.tree.identify_row(e.y)
        if target and target != iid:
            if not moved:
                self._push_undo()
                self._tree_drag[1] = True
            self.tree.move(iid, "", self.tree.index(target))
            self._renumber()
            self._mark_dirty()

    def _tree_release(self, _e):
        if self._tree_drag and self._tree_drag[1]:
            iid = self._tree_drag[0]
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        self._tree_drag = None

    # ---- undo
    def _push_undo(self):
        snap = ([(i, copy.deepcopy(self.items[i])) for i in self.tree.get_children()],
                copy.deepcopy(self.project.deleted), self.current)
        self.undo_stack.append(snap)
        del self.undo_stack[:-MAX_UNDO]

    def _undo_key(self, e):
        if isinstance(e.widget, (tk.Text, tk.Entry, ttk.Entry)):
            return None                      # let text boxes undo their own typing
        self.undo()
        return "break"

    def undo(self):
        if not self.undo_stack:
            self._status("Nothing to undo.")
            return
        pairs, deleted, current = self.undo_stack.pop()
        self.project.deleted = deleted
        self._rebuild(pairs, select=current)
        self._show_step(current if current in self.items else None)
        self._mark_dirty()
        self._status("Undone.")

    # ===================================================== intro, save, export
    def edit_intro(self):
        if not self.project:
            return
        dlg = tk.Toplevel(self.win)
        dlg.title("Introduction")
        dlg.transient(self.win)
        ttk.Label(dlg, text="Shown under the title, before step 1:",
                  padding=(10, 10, 10, 4)).pack(anchor="w")
        box = tk.Text(dlg, width=70, height=10, wrap="word", font=("Segoe UI", 11), padx=8, pady=6)
        box.pack(fill="both", expand=True, padx=10)
        box.insert("1.0", self.project.intro)
        row = ttk.Frame(dlg, padding=10)
        row.pack(fill="x")

        def ok():
            new = box.get("1.0", "end-1c").strip()
            if new != self.project.intro:
                self.project.intro = new
                self._mark_dirty()
            dlg.destroy()
        ttk.Button(row, text="OK", command=ok).pack(side="right")
        ttk.Button(row, text="Cancel", command=dlg.destroy).pack(side="right", padx=6)
        box.focus_set()
        dlg.grab_set()

    def _sync(self):
        self.project.steps = [self.items[i] for i in self.tree.get_children()]
        self.project.title = self.title_var.get()

    def save(self) -> bool:
        if not self.project:
            return False
        self._sync()
        try:
            self.project.save()
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.win)
            return False
        self._mark_dirty(False)
        self._status(f"Saved {len(self.project.steps)} steps.")
        return True

    def export(self, fmt: str) -> Optional[Path]:
        if not self.project:
            return None
        self._sync()
        self._status("Exporting…")
        self.win.config(cursor="watch")
        self.win.update_idletasks()
        try:
            path = export(self.project, fmt)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc), parent=self.win)
            self._status("Export failed.")
            return None
        finally:
            self.win.config(cursor="")
        self._status(f"Exported {path.name} to {path.parent}")
        if self.auto_open:
            open_folder(path)
        return path

    def _confirm_discard(self) -> bool:
        ans = messagebox.askyesnocancel("Unsaved changes", "Save your changes first?",
                                        parent=self.win)
        if ans is None:
            return False
        return self.save() if ans else True

    def close(self):
        if self.dirty and not self._confirm_discard():
            return
        self.win.destroy()
        if self.on_close:
            self.on_close()


def run_standalone(folder=None, default_dir=None):
    """Open the editor on its own (python run.py --review)."""
    from .platform_utils import enable_dpi_awareness
    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    Editor(root, folder, on_close=root.destroy, default_dir=default_dir)
    root.mainloop()
