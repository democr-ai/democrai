from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QGraphicsView, QLabel, QLineEdit, QPushButton, QTabWidget, QWidget

from clients.qtdesktop.ui.renderers.domains.data.workflow import WorkflowRenderer


def test_workflow_renderer_builds_canvas_and_property_panel():
    app = QApplication.instance() or QApplication([])
    renderer = WorkflowRenderer()
    ui_widgets: dict[str, QWidget] = {}
    surface_components: dict[str, list[dict]] = {}
    widget_surface: dict[str, str] = {}

    class _DrawerSurfaces:
        def handle_surface_update(self, update: dict) -> None:
            surface_id = str(update.get("surfaceId") or "main")
            surface_components[surface_id] = list(update.get("components") or [])

        def handle_begin_rendering(self, cmd: dict) -> None:
            surface_id = str(cmd.get("surfaceId") or "main")
            for comp_id in [cid for cid, sid in list(widget_surface.items()) if sid == surface_id]:
                ui_widgets.pop(comp_id, None)
                widget_surface.pop(comp_id, None)

            for comp_def in surface_components.get(surface_id, []):
                comp_id = str(comp_def.get("id") or "")
                component = comp_def.get("component") or {}
                if not comp_id or not isinstance(component, dict) or not component:
                    continue
                c_type = list(component.keys())[0]
                props = component.get(c_type) or {}
                if c_type == "Button":
                    widget = QPushButton(str((props.get("label") or {}).get("literalString") or ""))
                    widget.setObjectName(comp_id)
                    ui_widgets[comp_id] = widget
                    widget_surface[comp_id] = surface_id
                    continue
                if c_type == "TextField":
                    widget = QLineEdit(str(props.get("value") or ""))
                    widget.setObjectName(comp_id)
                    ui_widgets[comp_id] = widget
                    widget_surface[comp_id] = surface_id
                    continue
                if c_type == "Select":
                    frame = QWidget()
                    frame.setObjectName(comp_id)
                    combo = QComboBox(frame)
                    combo.setObjectName(f"{comp_id}__input")
                    for opt in list(props.get("options") or []):
                        if not isinstance(opt, dict):
                            continue
                        combo.addItem(str(opt.get("label") or ""), opt.get("value"))
                    selected = props.get("value")
                    for idx in range(combo.count()):
                        if combo.itemData(idx) == selected:
                            combo.setCurrentIndex(idx)
                            break
                    ui_widgets[comp_id] = frame
                    widget_surface[comp_id] = surface_id
                    continue
                if c_type == "Tabs":
                    tabs = QTabWidget()
                    tabs.setObjectName(comp_id)
                    for tab in list(props.get("tabs") or []):
                        label = str((tab or {}).get("label") or "Tab")
                        tabs.addTab(QWidget(), label)
                    ui_widgets[comp_id] = tabs
                    widget_surface[comp_id] = surface_id
                    continue
                if c_type == "Dialog":
                    dialog = QDialog()
                    dialog.setObjectName(comp_id)
                    ui_widgets[comp_id] = dialog
                    widget_surface[comp_id] = surface_id
                    continue
                if c_type in {"Text", "Markdown"}:
                    text = props.get("text") or {}
                    widget = QLabel(str(text.get("literalString") or ""))
                    widget.setObjectName(comp_id)
                    ui_widgets[comp_id] = widget
                    widget_surface[comp_id] = surface_id

        def handle_delete_surface(self, update: dict) -> None:
            surface_id = str(update.get("surfaceId") or "main")
            for comp_id in [cid for cid, sid in list(widget_surface.items()) if sid == surface_id]:
                ui_widgets.pop(comp_id, None)
                widget_surface.pop(comp_id, None)

    app_instance = SimpleNamespace(
        _surfaces=_DrawerSurfaces(),
        _get_widget_by_id=lambda cid: ui_widgets.get(cid),
    )
    widget = renderer.render(
        {
            "title": "Workflow Preview",
            "nodes": [
                {
                    "id": "start",
                    "label": "Start",
                    "nodeType": "trigger",
                    "status": "ready",
                    "config": {"path": "/hook"},
                    "outputs": [{"id": "payload", "params": ["body"]}],
                },
                {
                    "id": "end",
                    "label": "End",
                    "nodeType": "action",
                    "status": "ready",
                    "input": {"params": ["body"]},
                    "outputs": [{"id": "done", "params": ["id"]}],
                },
                {
                    "id": "gate",
                    "label": "Evaluator",
                    "nodeType": "evaluator",
                    "status": "ready",
                    "input": {"params": ["body"]},
                    "outputs": [{"id": "pass", "params": ["body"]}],
                },
            ],
            "edges": [
                {
                    "source": "start",
                    "target": "gate",
                    "sourceOutput": "payload",
                    "label": "next",
                    "mapping": {"body": "body"},
                }
            ],
            "componentCatalog": [
                {
                    "id": "http_request",
                    "label": "HTTP Request",
                    "nodeType": "http",
                    "input": {"params": ["url"]},
                    "outputs": [{"id": "response", "params": ["status", "body"]}],
                    "allowAddOutput": False,
                },
                {
                    "id": "json_transform",
                    "label": "JSON Transform",
                    "nodeType": "transform",
                    "input": {"params": ["payload"]},
                    "outputs": [{"id": "result", "params": ["body"]}],
                    "allowAddOutput": True,
                    "cascadeDeleteConnected": True,
                },
            ],
            "height": 420,
        },
        "main",
        app_instance,
        comp_id="workflow",
    )

    view = widget.findChild(QGraphicsView, "workflow_view")
    assert view is not None
    scene = view.scene()
    assert scene is not None
    assert len(scene.items()) > 0

    selected_node = next(
        item for item in scene.items() if hasattr(item, "node") and isinstance(item.node, dict)
    )
    scene.clearSelection()
    selected_node.setSelected(True)
    app.processEvents()

    node_id = ui_widgets.get("workflow_prop_id")
    node_cfg = ui_widgets.get("workflow_prop_config")
    assert node_id is not None
    assert node_cfg is not None
    assert isinstance(node_id, QLabel)
    assert isinstance(node_cfg, QLabel)
    assert node_id.text().startswith("ID:")
    assert node_id.text() != "ID: -"
    assert "```json" in node_cfg.text()

    add_component_btn = widget.findChild(QPushButton, "wf_toolbar_add_component_btn")
    assert widget.findChild(QPushButton, "workflow_add_output_btn") is None
    assert add_component_btn is not None

    before_nodes = len(
        [item for item in scene.items() if hasattr(item, "node") and isinstance(item.node, dict)]
    )
    add_component_btn.click()
    app.processEvents()

    modal_tabs = ui_widgets.get("workflow_add_modal_tabs")
    modal_components = ui_widgets.get("workflow_add_modal_components_select")
    modal_confirm = ui_widgets.get("workflow_add_modal_confirm_btn")
    assert isinstance(modal_tabs, QTabWidget)
    assert isinstance(modal_components, QWidget)
    assert isinstance(modal_confirm, QPushButton)
    modal_tabs.setCurrentIndex(1)
    modal_combo = modal_components.findChild(QComboBox, "workflow_add_modal_components_select__input")
    assert modal_combo is not None
    for idx in range(modal_combo.count()):
        if modal_combo.itemData(idx) == "components::json_transform":
            modal_combo.setCurrentIndex(idx)
            break
    modal_confirm.click()
    app.processEvents()

    node_items = [item for item in scene.items() if hasattr(item, "node") and isinstance(item.node, dict)]
    after_nodes = len(node_items)
    assert after_nodes == before_nodes + 1
    created_node = next(item.node for item in node_items if str(item.node.get("id", "")).startswith("json_transform_"))
    assert created_node["nodeType"] == "transform"
    assert created_node["label"] == "JSON Transform"

    created_node_item = next(item for item in node_items if str(item.node.get("id", "")).startswith("json_transform_"))

    edges_before = [
        item for item in scene.items() if hasattr(item, "edge") and isinstance(item.edge, dict)
    ]

    source_anchor_scene = created_node_item.out_anchor("result")
    target_node_item = next(item for item in node_items if item.node.get("id") == "end")
    target_center_scene = target_node_item.mapToScene(target_node_item.rect().center())
    source_anchor_view = view.mapFromScene(source_anchor_scene)
    target_center_view = view.mapFromScene(target_center_scene)

    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, source_anchor_view)
    QTest.mouseMove(view.viewport(), target_center_view)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target_center_view)
    app.processEvents()

    edges_after = [
        item for item in scene.items() if hasattr(item, "edge") and isinstance(item.edge, dict)
    ]
    assert len(edges_after) == len(edges_before) + 1
    added_edge = next(
        item.edge
        for item in edges_after
        if str(item.edge.get("source", "")).startswith("json_transform_")
        and item.edge.get("target") == "end"
    )
    assert added_edge.get("sourceOutput") == "result"
    assert added_edge.get("mapping") == {"body": "body"}

    edge_item = next(
        item for item in scene.items() if hasattr(item, "edge") and isinstance(item.edge, dict)
    )
    scene.clearSelection()
    edge_item.setSelected(True)
    app.processEvents()

    mapping_edit = ui_widgets.get("workflow_edge_mapping")
    apply_mapping_btn = ui_widgets.get("workflow_apply_mapping_btn")
    assert mapping_edit is not None
    assert apply_mapping_btn is not None
    assert isinstance(mapping_edit, QLineEdit)
    assert isinstance(apply_mapping_btn, QPushButton)
    mapping_edit.setText('{"body":"payload.body","trace_id":"meta.trace_id"}')
    apply_mapping_btn.click()
    app.processEvents()
    assert edge_item.edge.get("mapping") == {
        "body": "payload.body",
        "trace_id": "meta.trace_id",
    }

    evaluator_item = next(
        item
        for item in node_items
        if item.node.get("id") == "gate"
    )
    scene.clearSelection()
    evaluator_item.setSelected(True)
    app.processEvents()

    output_id_input = ui_widgets.get("workflow_new_output_id")
    output_mode_widget = ui_widgets.get("workflow_new_output_mode")
    output_value1_input = ui_widgets.get("workflow_new_output_value1")
    output_operator_widget = ui_widgets.get("workflow_new_output_operator")
    output_value2_input = ui_widgets.get("workflow_new_output_value2")
    add_output_btn = ui_widgets.get("workflow_add_conditional_output_btn")
    assert isinstance(output_id_input, QLineEdit)
    assert isinstance(output_mode_widget, QWidget)
    assert isinstance(output_value1_input, QLineEdit)
    assert isinstance(output_operator_widget, QWidget)
    assert isinstance(output_value2_input, QLineEdit)
    assert isinstance(add_output_btn, QPushButton)

    output_mode_combo = output_mode_widget.findChild(QComboBox, "workflow_new_output_mode__input")
    output_operator_combo = output_operator_widget.findChild(QComboBox, "workflow_new_output_operator__input")
    assert output_mode_combo is not None
    assert output_operator_combo is not None
    output_id_input.setText("high")
    for idx in range(output_mode_combo.count()):
        if output_mode_combo.itemData(idx) == "AND":
            output_mode_combo.setCurrentIndex(idx)
            break
    output_value1_input.setText("payload.score")
    for idx in range(output_operator_combo.count()):
        if output_operator_combo.itemData(idx) == ">":
            output_operator_combo.setCurrentIndex(idx)
            break
    output_value2_input.setText("80")
    add_output_btn.click()
    app.processEvents()

    gate_outputs = list(evaluator_item.node.get("outputs") or [])
    assert len(gate_outputs) == 2
    added_output = next(out for out in gate_outputs if str(out.get("id") or "") == "high")
    assert added_output.get("when") == {
        "operator": "AND",
        "conditions": [
            {
                "value1": "payload.score",
                "operator": ">",
                "value2": "80",
            }
        ],
    }

    scene.clearSelection()
    created_node_item.setSelected(True)
    app.processEvents()
    view.setFocus()
    QTest.keyClick(view, Qt.Key_Delete)
    app.processEvents()
    remaining_node_ids = {
        str(item.node.get("id") or "")
        for item in scene.items()
        if hasattr(item, "node") and isinstance(item.node, dict)
    }
    assert "start" in remaining_node_ids
    assert "end" not in remaining_node_ids
    assert not any(node_id.startswith("json_transform_") for node_id in remaining_node_ids)


def test_workflow_renderer_uses_fallback_flow_when_input_is_empty():
    app = QApplication.instance() or QApplication([])
    renderer = WorkflowRenderer()
    widget = renderer.render({}, "main", SimpleNamespace(), comp_id="workflow_fallback")
    view = widget.findChild(QGraphicsView, "workflow_fallback_view")
    assert view is not None
    scene = view.scene()
    assert scene is not None
    assert len(scene.items()) > 0
    app.processEvents()
