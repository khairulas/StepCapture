"""Load and save an edited session (steps.json) for the editor and exporters."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .session import describe


class Project:
    """A session folder opened for editing. Steps are plain dicts from steps.json."""

    def __init__(self, folder):
        self.folder = Path(folder).expanduser().resolve()
        path = self.folder / "steps.json"
        if not path.exists():
            raise FileNotFoundError(f"No steps.json in {self.folder}")
        self.data: dict = json.loads(path.read_text(encoding="utf-8"))
        self.steps: list[dict] = list(self.data.get("steps", []))
        self.deleted: list[dict] = list(self.data.get("deleted_steps", []))

    # ------------------------------------------------------------- properties
    @property
    def title(self) -> str:
        return self.data.get("title") or ""

    @title.setter
    def title(self, value: str):
        self.data["title"] = value.strip()

    @property
    def intro(self) -> str:
        return self.data.get("intro") or ""

    @intro.setter
    def intro(self, value: str):
        self.data["intro"] = value.strip()

    @property
    def recorded_on(self) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self.data.get("started_at"))
        except (TypeError, ValueError):
            return None

    def display_title(self) -> str:
        return self.title or "Tutorial"

    # ------------------------------------------------------------------ steps
    def image_path(self, step: dict) -> Optional[Path]:
        rel = step.get("raw_image") or step.get("image")
        if not rel:
            return None
        p = self.folder / rel
        return p if p.exists() else None

    @staticmethod
    def instruction(step: dict) -> str:
        return (step.get("description") or "").strip() or describe(step)

    @staticmethod
    def new_text_step() -> dict:
        return {
            "index": 0, "type": "text", "timestamp": datetime.now().astimezone().isoformat(
                timespec="milliseconds"),
            "elapsed_s": None, "button": None, "screen_x": None, "screen_y": None,
            "image_x": None, "image_y": None, "monitor": None, "window_title": "",
            "image": None, "raw_image": None, "description": "",
        }

    # ------------------------------------------------------------------- save
    def save(self) -> Path:
        for i, s in enumerate(self.steps, start=1):
            s["index"] = i
        self.data["steps"] = self.steps
        self.data["deleted_steps"] = self.deleted
        self.data["edited_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

        path = self.folder / "steps.json"
        backup = self.folder / "steps.original.json"
        if not backup.exists():
            shutil.copy2(path, backup)
        tmp = self.folder / "steps.json.tmp"
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return path


def latest_session(root) -> Optional[Path]:
    """Most recent session folder (by name) under the output root."""
    root = Path(root).expanduser()
    sessions = sorted(p for p in root.glob("session_*") if (p / "steps.json").exists())
    return sessions[-1] if sessions else None
