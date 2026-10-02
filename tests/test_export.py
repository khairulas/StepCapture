"""Tests for rendering, the editor's data model and exporters (no display needed)."""
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stepcapture.exporters import FORMATS, export, inline_parts  # noqa: E402
from stepcapture.project import Project, latest_session  # noqa: E402
from stepcapture.render import crop_around_click, render_step  # noqa: E402
from stepcapture.session import Session  # noqa: E402
from test_session import fake_capture  # noqa: E402


def make_session(root: Path) -> Path:
    s = Session(root, dedupe=False)
    s.add_capture(fake_capture(100, 100, (0, 0, 120)))
    s.add_capture(fake_capture(600, 400, (120, 0, 0)))
    return s.finish()


def test_render_blur_marker_crop():
    with tempfile.TemporaryDirectory() as d:
        folder = make_session(Path(d))
        p = Project(folder)
        step = p.steps[0]
        raw = Image.open(p.image_path(step)).convert("RGB")

        step.update(blurs=[[60, 60, 290, 190]], show_marker=False)
        img = render_step(p.image_path(step), step)
        assert img.size == raw.size
        assert img.getpixel((124, 100)) == (255, 255, 255)        # marker hidden
        step["blurs"] = []
        step["crop"] = [50, 50, 450, 350]
        assert render_step(p.image_path(step), step).size == (400, 300)
        assert render_step(p.image_path(step), step, border=True).size == (402, 302)
        assert crop_around_click({"image_x": 790, "image_y": 590}, (800, 600)) == [360, 270, 800, 600]


def test_project_save_and_exports():
    with tempfile.TemporaryDirectory() as d:
        folder = make_session(Path(d))
        assert latest_session(Path(d)) == folder
        p = Project(folder)
        p.title, p.intro = "My Guide", "Intro with **bold**."
        p.steps[0]["description"] = "Click **Save**."
        p.steps.insert(1, Project.new_text_step())
        p.deleted.append(p.steps.pop())                              # delete the last step
        p.save()

        data = json.loads((folder / "steps.json").read_text())
        assert [s["index"] for s in data["steps"]] == [1, 2]
        assert data["steps"][1]["type"] == "text" and len(data["deleted_steps"]) == 1
        assert (folder / "steps.original.json").exists()

        p = Project(folder)
        outs = {f: export(p, f) for f in FORMATS}
        assert all(o.exists() for o in outs.values())
        html = outs["html"].read_text()
        assert html.count("<img ") == 1 and "<strong>Save</strong>" in html
        md = outs["md"].read_text()
        assert "Click **Save**." in md and "Describe this step." in md

        from docx import Document
        doc = Document(outs["docx"])
        assert len(doc.inline_shapes) == 1
        bold = [r.text for para in doc.paragraphs for r in para.runs if r.bold]
        assert "Save" in bold and "bold" in bold


def test_inline_parts():
    assert inline_parts("Click **Save** in *Word*") == [
        ("Click ", False, False), ("Save", True, False), (" in ", False, False), ("Word", False, True)]
    assert inline_parts("2 * 3 = 6") == [("2 * 3 = 6", False, False)]


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
