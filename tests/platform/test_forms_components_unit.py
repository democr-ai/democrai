from democrai.sdk.components.domains.forms.textarea import TextArea
from democrai.sdk.components.domains.forms.attachment import Attachment
from democrai.sdk.components.domains.forms.editable_list import EditableList
from democrai.sdk.components.domains.forms.select import Select
from democrai.sdk.components.domains.forms.radio_group import RadioGroup
from democrai.sdk.components.domains.forms.tags_input import TagsInput

def test_textarea_initialization():
    ta = TextArea("ta1", label="Bio", value="Hello", placeholder="Type here", rows=5, auto_resize=False)
    d = ta.to_dict()
    props = d["component"]["TextArea"]
    assert props["label"] == {"literalString": "Bio"}
    assert props["value"] == "Hello"
    assert props["placeholder"] == "Type here"
    assert props["rows"] == 5
    assert props["auto_resize"] is False

def test_textarea_on_change():
    ta = TextArea("ta1")
    ta.set_on_change_action("save_bio", {"user_id": 123}, mode="remote")
    props = ta.to_dict()["component"]["TextArea"]
    assert props["onChangeAction"] == {"name": "save_bio", "context": {"user_id": 123}}
    assert props["onChangeMode"] == "remote"

def test_attachment_initialization():
    at = Attachment("at1", label="Upload", accept=".pdf", multiple=True)
    d = at.to_dict()
    props = d["component"]["Attachment"]
    assert props["label"] == {"literalString": "Upload"}
    assert props["accept"] == ".pdf"
    assert props["multiple"] is True
    assert props["value"] == []

def test_attachment_set_action():
    at = Attachment("at1")
    at.set_action("upload_finished", {"folder": "docs"})
    props = at.to_dict()["component"]["Attachment"]
    assert props["action"] == {"name": "upload_finished", "context": {"folder": "docs"}}

def test_select_dynamic_options():
    s = Select(
        "s1", 
        label="Country", 
        options_action="get_countries", 
        options_store="/data/countries",
        options_plain=[{"label": "Italy", "value": "it"}]
    )
    props = s.to_dict()["component"]["Select"]
    assert props["optionsAction"] == {"name": "get_countries", "context": {}}
    assert props["optionsStore"] == "/data/countries"
    assert props["options"] == [{"label": "Italy", "value": "it"}]

def test_radio_group_dynamic_options():
    rg = RadioGroup(
        "rg1", 
        label="Size", 
        options_action="get_sizes", 
        options_store="/ui/sizes"
    )
    props = rg.to_dict()["component"]["RadioGroup"]
    assert props["optionsAction"] == {"name": "get_sizes", "context": {}}
    assert props["optionsStore"] == "/ui/sizes"

def test_tags_input_initialization():
    tags = TagsInput(
        "tags1",
        label="Mime types",
        value=["image/png"],
        placeholder="image/jpeg",
        add_label="Add mime",
        item_schema={"type": "text"},
    )
    props = tags.to_dict()["component"]["TagsInput"]
    assert props["label"] == {"literalString": "Mime types"}
    assert props["value"] == ["image/png"]
    assert props["placeholder"] == "image/jpeg"
    assert props["add_label"] == {"literalString": "Add mime"}
    assert props["item_schema"] == {"type": "text"}

def test_tags_input_requires_item_schema():
    try:
        TagsInput("tags1")
    except ValueError as exc:
        assert str(exc) == "TagsInput item_schema is required"
    else:
        raise AssertionError("TagsInput without item_schema must fail")

def test_editable_list_initialization():
    editable = EditableList(
        "editable1",
        value=["chat"],
        item_label="Capabilities",
        add_label="Add capability",
        remove_label="Remove",
        submit_label="Save",
        item_schema={"type": "select", "options": [{"label": "Chat", "value": "chat"}]},
    )
    props = editable.to_dict()["component"]["EditableList"]
    assert props["value"] == ["chat"]
    assert props["item_label"] == {"literalString": "Capabilities"}
    assert props["add_label"] == {"literalString": "Add capability"}
    assert props["remove_label"] == {"literalString": "Remove"}
    assert props["submit_label"] == {"literalString": "Save"}
    assert props["item_schema"] == {"type": "select", "options": [{"label": "Chat", "value": "chat"}]}

def test_editable_list_requires_item_schema():
    try:
        EditableList("editable1")
    except ValueError as exc:
        assert str(exc) == "EditableList item_schema is required"
    else:
        raise AssertionError("EditableList without item_schema must fail")
