from clients.qtdesktop.ui.devtools import DevToolsInspector


class _Geom:
    def x(self):
        return 1

    def y(self):
        return 2

    def width(self):
        return 300

    def height(self):
        return 120


class _Widget:
    def objectName(self):
        return "demo-widget"

    def geometry(self):
        return _Geom()

    def isVisible(self):
        return True

    def isEnabled(self):
        return True

    def parentWidget(self):
        return None

    def dynamicPropertyNames(self):
        return [b"broken_prop"]

    def property(self, _name):
        raise RuntimeError("Can't find converter for 'std::shared_ptr<char>'.")

    def styleSheet(self):
        return ""


class _TextSink:
    def __init__(self):
        self.value = ""

    def setPlainText(self, value):
        self.value = value

    def toPlainText(self):
        return self.value


class _LabelSink:
    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value


class _StyleWidget(_Widget):
    def __init__(self):
        self._style = "color: red;"

    def styleSheet(self):
        return self._style

    def setStyleSheet(self, value):
        self._style = value


class _AppStub:
    def __init__(self, stylesheet: str = ""):
        self._stylesheet = stylesheet
        self._clipboard = _ClipboardStub()

    def styleSheet(self):
        return self._stylesheet

    def clipboard(self):
        return self._clipboard


class _ClipboardStub:
    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value


class _LineEditStub:
    def __init__(self, value: str = ""):
        self._value = value

    def text(self):
        return self._value


class _ListItemStub:
    def __init__(self, text: str):
        self._text = text

    def text(self):
        return self._text


class _ListStub:
    def __init__(self, item_text: str = ""):
        self._item = _ListItemStub(item_text) if item_text else None

    def currentItem(self):
        return self._item


def test_widget_dump_handles_unavailable_dynamic_property_values():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    inspector._app = _AppStub(
        "#demo-widget { color: #fff; }\nQPushButton { color: #333; }"
    )
    output = inspector._widget_dump(_Widget())
    assert "broken_prop" in output
    assert "<unavailable: RuntimeError" in output
    assert "style_source: app_global_only" in output
    assert "matched_global_rules:" in output
    assert "#demo-widget { color: #fff; }" in output
    assert "QPushButton { color: #333; }" not in output


def test_refresh_does_not_raise_when_widget_dump_fails():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    inspector._selected = _Widget()
    inspector._selected_label = _LabelSink()
    inspector._details = _TextSink()
    inspector._style_editor = _TextSink()
    inspector._original_styles = {}
    inspector._widget_dump = lambda widget: (_ for _ in ()).throw(RuntimeError("boom"))

    inspector.refresh()

    assert inspector._selected_label.value.startswith("Selected:")
    assert "Inspector error while dumping selected widget:" in inspector._details.value
    assert "RuntimeError: boom" in inspector._details.value


def test_apply_and_reset_style_for_selected_widget():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    widget = _StyleWidget()
    inspector._selected = widget
    inspector._details = _TextSink()
    inspector._style_editor = _TextSink()
    inspector._original_styles = {}

    inspector._style_editor.setPlainText("background: #222;")
    inspector.apply_style()
    assert widget.styleSheet() == "background: #222;"

    inspector.reset_style()
    assert widget.styleSheet() == "color: red;"
    assert inspector._style_editor.toPlainText() == "color: red;"


def test_widget_dump_marks_widget_override_style_source():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    inspector._app = _AppStub(
        "_StyleWidget[variant='default'] { color: #fff; }\nQDialog { color: #000; }"
    )
    widget = _StyleWidget()
    widget._variant = "default"
    widget.property = lambda name: widget._variant if name == "variant" else None
    output = inspector._widget_dump(widget)
    assert "style_source: widget_override + app_global" in output
    assert "_StyleWidget[variant='default'] { color: #fff; }" in output


def test_widget_dump_with_no_matching_global_rules_marks_none():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    inspector._app = _AppStub("QPushButton { color: #fff; }")
    output = inspector._widget_dump(_StyleWidget())
    assert "style_source: widget_override + app_global" in output
    assert "matched_global_rules:" in output
    assert "  (none)" in output


def test_widget_dump_orders_matched_rules_by_specificity():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    inspector._app = _AppStub(
        "_Widget { color: #111; }\n"
        "_StyleWidget[variant='default'] { color: #222; }\n"
        "#demo-widget { color: #333; }"
    )
    widget = _StyleWidget()
    widget._variant = "default"
    widget.property = lambda name: widget._variant if name == "variant" else None
    output = inspector._widget_dump(widget)
    id_pos = output.find("#demo-widget { color: #333; }")
    attr_pos = output.find("_StyleWidget[variant='default'] { color: #222; }")
    type_pos = output.find("_Widget { color: #111; }")
    assert id_pos != -1 and attr_pos != -1 and type_pos != -1
    assert id_pos < attr_pos < type_pos


def test_widget_dump_applies_rules_filter_query():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    inspector._app = _AppStub(
        "_StyleWidget[variant='default'] { color: #222; }\n"
        "_StyleWidget[shape='round'] { border-radius: 999px; }"
    )
    inspector._rules_filter = _LineEditStub("variant=default")
    widget = _StyleWidget()
    widget._variant = "default"
    widget.property = lambda name: widget._variant if name == "variant" else None
    output = inspector._widget_dump(widget)
    assert "rules_filter: variant=default" in output
    assert "_StyleWidget[variant='default'] { color: #222; }" in output
    assert "_StyleWidget[shape='round'] { border-radius: 999px; }" not in output


def test_copy_snapshot_json_exports_selected_widget_state():
    inspector = DevToolsInspector.__new__(DevToolsInspector)
    app = _AppStub("_StyleWidget[variant='default'] { color: #222; }")
    app._clipboard = _ClipboardStub()
    inspector._app = app
    inspector._rules_filter = _LineEditStub("variant=default")
    inspector._rules_list = _ListStub("_StyleWidget[variant='default'] { color: #222; }")
    widget = _StyleWidget()
    widget._variant = "default"
    widget.property = lambda name: widget._variant if name == "variant" else None
    inspector._selected = widget

    inspector.copy_snapshot_json()

    assert '"class": "_StyleWidget"' in app._clipboard.value
    assert '"filter_query": "variant=default"' in app._clipboard.value
    assert '"selected_rule": "_StyleWidget[variant=\'default\'] { color: #222; }"' in app._clipboard.value
