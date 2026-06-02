from democrai.sdk.effects import Effects

def test_effect_copy_to_clipboard():
    effect = Effects(sdk=None).copy_to_clipboard("test text")
    assert effect == {
        "type": "window_action",
        "op": "copy_to_clipboard",
        "text": "test text"
    }
