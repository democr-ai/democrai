from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QScrollArea

from clients.qtdesktop.ui.renderers.domains.data.gantt import GanttRenderer, build_gantt_model


def test_build_gantt_model_normalizes_rows_and_range():
    model = build_gantt_model(
        {
            "items": [
                {
                    "id": "sdk",
                    "label": "SDK contract",
                    "group": "platform",
                    "start": "2026-03-10",
                    "end": "2026-03-15",
                    "status": "active",
                    "progress": 45,
                },
                {
                    "id": "docs",
                    "label": "Docs",
                    "start": "2026-03-14",
                    "end": "2026-03-20",
                    "status": "planned",
                },
            ],
            "start": "2026-03-09",
            "end": "2026-03-22",
        }
    )

    assert len(model["rows"]) == 2
    assert model["rows"][0].progress == 45
    assert model["rows"][0].color == "#38BDF8"
    assert model["start"].date().isoformat() == "2026-03-09"
    assert model["end"].date().isoformat() == "2026-03-22"
    assert len(model["ticks"]) == 14


def test_gantt_renderer_mounts_scroll_canvas():
    app = QApplication.instance() or QApplication([])
    renderer = GanttRenderer()
    widget = renderer.render(
        {
            "title": "Roadmap",
            "items": [
                {"id": "sdk", "label": "SDK", "start": "2026-03-10", "end": "2026-03-12", "status": "done"},
                {"id": "ui", "label": "UI", "start": "2026-03-13", "end": "2026-03-18", "status": "active"},
            ],
            "height": 340,
        },
        "main",
        SimpleNamespace(),
        comp_id="gantt",
    )

    scroll = widget.layout().itemAt(1).widget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.widget() is not None
    assert scroll.widget().minimumWidth() > 400
    app.processEvents()


def test_build_gantt_model_accepts_mermaid_gantt():
    model = build_gantt_model(
        {
            "mermaid": """
gantt
    title Delivery
    dateFormat YYYY-MM-DD
    section Core
    API contract :done, api, 2026-03-10, 3d
    UI polish    :active, ui, after api, 4d
""",
        }
    )

    assert model["title"] == "Delivery"
    assert len(model["rows"]) == 2
    assert model["rows"][0].id == "api"
    assert model["rows"][1].status == "active"
    assert model["rows"][1].start > model["rows"][0].end
