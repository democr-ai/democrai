from democrai.sdk.components.domains.media.qr_code import QRCode

def test_qr_code_component_initialization():
    qr = QRCode("test_qr", "https://example.com", size=300, border=5, fill_color="#000000", back_color="#ffffff")
    assert qr.id == "test_qr"
    props = qr.props
    assert props["content"] == {"literalString": "https://example.com"}
    assert props["size"] == 300
    assert props["border"] == 5
    assert props["fill_color"] == "#000000"
    assert props["back_color"] == "#ffffff"

def test_qr_code_component_defaults():
    qr = QRCode("test_qr", "https://example.com")
    props = qr.props
    assert props["content"] == {"literalString": "https://example.com"}
    assert props["size"] == 220
    assert props["border"] == 4
    assert props["fill_color"] == "#111111"
    assert props["back_color"] == "#ffffff"
