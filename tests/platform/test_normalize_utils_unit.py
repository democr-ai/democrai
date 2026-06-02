from __future__ import annotations

import democrai.sdk.normalize as sdk_normalize
from democrai.core.platform.utils import normalize as normalize_mod


def test_normalize_strings_and_collections():
    assert normalize_mod.normalize_string("  A  ") == "A"
    assert normalize_mod.normalize_string(None, default="x") == "x"
    assert normalize_mod.normalize_key("  A  ") == "a"
    assert normalize_mod.normalize_dict({"a": 1}) == {"a": 1}
    assert normalize_mod.normalize_dict("bad") == {}
    assert normalize_mod.normalize_list([1]) == [1]
    assert normalize_mod.normalize_list(("x",)) == []
    assert normalize_mod.normalize_string_list(" A, ,B ", lower=True) == ["a", "b"]
    assert normalize_mod.normalize_string_list([" A ", None, "B"]) == ["A", "B"]
    assert normalize_mod.qualify_module_registry_name("mod", "action") == "mod.action"
    assert normalize_mod.qualify_module_registry_name("mod", "mod.action") == "mod.action"
    assert normalize_mod.qualify_module_registry_name("core", "action") == "action"
    assert normalize_mod.qualify_module_registry_name("mod", None, fallback_name="fn") == "mod.fn"
    assert normalize_mod.qualify_module_registry_name("mod", "") == ""


def test_normalize_scalars():
    assert normalize_mod.normalize_bool(True) is True
    assert normalize_mod.normalize_bool(" yes ") is True
    assert normalize_mod.normalize_bool(" y ") is True
    assert normalize_mod.normalize_bool(" off ", default=True) is False
    assert normalize_mod.normalize_bool(" n ", default=True) is False
    assert normalize_mod.normalize_bool("unknown", default=True) is True
    assert normalize_mod.normalize_int("7") == 7
    assert normalize_mod.normalize_int(True, default=3) == 3
    assert normalize_mod.normalize_float("1.5") == 1.5
    assert normalize_mod.normalize_float(False, default=2.5) == 2.5


def test_sdk_normalize_reexports_core_helpers():
    assert sdk_normalize.normalize_bool is normalize_mod.normalize_bool
    assert sdk_normalize.normalize_key(" X ") == "x"
