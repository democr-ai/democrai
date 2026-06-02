from types import SimpleNamespace

from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QApplication

from clients.qtdesktop.ui.renderers.domains.data.diagram import (
    DiagramRenderer,
    _parse_mermaid_flowchart,
    _build_edge_path,
    layout_diagram,
)


def test_layout_diagram_renders_positions_edges_and_fallback():
    graph = layout_diagram(
        {
            "nodes": [
                {"id": "capture", "label": "Capture Request"},
                {"id": "review", "label": "Review Inputs"},
                {"id": "publish", "label": "Publish Update"},
            ],
            "edges": [
                {"source": "capture", "target": "review", "label": "validate"},
                {"source": "review", "target": "publish"},
                {"source": "missing", "target": "publish"},
            ],
            "direction": "LR",
            "height": 260,
        }
    )

    assert [node["id"] for node in graph["nodes"]] == ["capture", "review", "publish"]
    assert len(graph["edges"]) == 2
    assert "missing" not in {edge["source"] for edge in graph["edges"]}
    assert graph["positions"]["review"].x() > graph["positions"]["capture"].x()
    assert graph["scene_rect"].height() >= 260

    path, label_pos = _build_edge_path(
        graph["positions"]["capture"],
        graph["positions"]["review"],
        source_width=graph["node_sizes"]["capture"][0],
        source_height=graph["node_sizes"]["capture"][1],
        target_width=graph["node_sizes"]["review"][0],
        target_height=graph["node_sizes"]["review"][1],
        direction=graph["direction"],
    )
    assert path.elementCount() >= 3
    assert label_pos.y() < graph["positions"]["review"].y() + graph["node_height"]

    empty_graph = layout_diagram({"nodes": [], "edges": []})
    assert empty_graph["nodes"] == []
    assert empty_graph["scene_rect"].width() == 480.0


def test_diagram_renderer_attaches_scene_to_view():
    app = QApplication.instance() or QApplication([])
    renderer = DiagramRenderer()
    widget = renderer.render(
        {
            "title": "Flow",
            "nodes": [{"id": "a", "label": "Start"}, {"id": "b", "label": "End"}],
            "edges": [{"source": "a", "target": "b", "label": "next"}],
            "height": 280,
        },
        "main",
        SimpleNamespace(),
        comp_id="diagram",
    )

    view = widget.layout().itemAt(1).widget()
    if isinstance(view, QQuickWidget):
        assert view.rootObject() is not None
    else:
        assert view.scene() is not None
        assert len(view.scene().items()) > 0
    app.processEvents()


def test_layout_diagram_separates_parallel_branches():
    graph = layout_diagram(
        {
            "nodes": [
                {"id": "root", "label": "Root"},
                {"id": "left", "label": "Left Branch"},
                {"id": "right", "label": "Right Branch"},
                {"id": "left_done", "label": "Left Done"},
                {"id": "right_done", "label": "Right Done"},
            ],
            "edges": [
                {"source": "root", "target": "left"},
                {"source": "root", "target": "right"},
                {"source": "left", "target": "left_done"},
                {"source": "right", "target": "right_done"},
            ],
            "direction": "LR",
            "height": 320,
        }
    )

    assert graph["positions"]["left"].x() == graph["positions"]["right"].x()
    assert graph["positions"]["left"].y() != graph["positions"]["right"].y()
    assert graph["positions"]["left_done"].y() != graph["positions"]["right_done"].y()


def test_layout_diagram_honors_explicit_lanes():
    graph = layout_diagram(
        {
            "nodes": [
                {"id": "root", "label": "Root", "lane": "core"},
                {"id": "approve", "label": "Approve", "lane": "approval"},
                {"id": "model", "label": "Model", "lane": "models"},
                {"id": "publish", "label": "Publish", "lane": "ui"},
            ],
            "edges": [
                {"source": "root", "target": "approve"},
                {"source": "root", "target": "model"},
                {"source": "approve", "target": "publish"},
                {"source": "model", "target": "publish"},
            ],
            "direction": "LR",
            "height": 320,
        }
    )

    assert graph["positions"]["approve"].y() != graph["positions"]["model"].y()
    assert graph["positions"]["publish"].y() != graph["positions"]["root"].y()


def test_layout_diagram_accepts_mermaid_flowchart():
    graph = layout_diagram(
        {
            "mermaid": """
flowchart LR
    start((Start)) --> gate{Check}
    gate -->|ok| done[Done]
    gate -->|retry| start
""",
            "height": 260,
        }
    )

    assert [node["id"] for node in graph["nodes"]] == ["start", "gate", "done"]
    assert graph["direction"] == "LR"
    assert len(graph["edges"]) == 3
    assert graph["edges"][1]["label"] == "ok"
    assert _parse_mermaid_flowchart("graph TB\nA-->B")["direction"] == "TB"
