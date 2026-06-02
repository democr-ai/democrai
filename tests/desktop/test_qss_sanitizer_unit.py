from clients.qtdesktop.ui.qss_sanitizer import qss_for_widget_style, sanitize_qss_style


def test_sanitize_qss_style_keeps_qt_properties_and_drops_web_css():
    style = (
        "color: red; flex-shrink: 0; background-color: #fff; "
        "display: flex; padding: 4px; gap: 8px;"
    )

    assert sanitize_qss_style(style) == (
        "color: red; background-color: #fff; padding: 4px;"
    )


def test_sanitize_qss_style_preserves_selectors_with_remaining_properties():
    style = (
        "QPushButton:hover { color: white; transition: color .2s; } "
        "QLabel { flex-shrink: 0; }"
    )

    assert sanitize_qss_style(style) == "QPushButton:hover { color: white; }"


def test_qss_for_widget_style_scopes_declaration_blocks():
    style = "font-size: 13px; white-space: nowrap; border-radius: 4px;"

    assert qss_for_widget_style(style, "title") == (
        "#title { font-size: 13px; border-radius: 4px; }"
    )


def test_sanitize_qss_style_preserves_qproperty_case():
    assert sanitize_qss_style("qproperty-wordWrap: true;") == (
        "qproperty-wordWrap: true;"
    )
