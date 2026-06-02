from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def _load_module(module_name: str, relative_path: str):
    root = Path(__file__).resolve().parents[2]
    path = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


visibility_mod = _load_module(
    "test_visibility_mod", "democrai/core/application/knowledge/visibility.py"
)
hierarchy_mod = _load_module(
    "test_hierarchy_mod", "democrai/core/application/knowledge/service_helper/hierarchy.py"
)


def _item(item_id: str, **metadata):
    return SimpleNamespace(id=item_id, metadata_json=json.dumps(metadata))


def test_visibility_helpers_full_matrix():
    assert visibility_mod.is_strict_user_kind("chat_turn")
    assert not visibility_mod.is_strict_user_kind("  AGENT_MESSAGE ")
    assert visibility_mod.is_strict_user_kind("agent_message")
    assert not visibility_mod.is_strict_user_kind("document")

    assert visibility_mod.normalize_public_flag(kind="chat_turn", is_public=True) is False
    assert visibility_mod.normalize_public_flag(kind="document", is_public=True) is True
    assert visibility_mod.normalize_public_flag(kind="document", is_public=False) is False

    org_scope = visibility_mod.public_organization_scope_id(7)
    assert org_scope < 0
    assert visibility_mod.public_super_scope_id() < 0

    # Not public -> no inherited scopes.
    assert (
        visibility_mod.inherited_visibility_scopes(
            owner_access_level=visibility_mod.ROLE_LEVEL_USER,
            organization_id=7,
            is_public=False,
            kind="document",
        )
        == ()
    )

    # User-level owner -> org + global.
    user_public = visibility_mod.inherited_visibility_scopes(
        owner_access_level=visibility_mod.ROLE_LEVEL_USER,
        organization_id=7,
        is_public=True,
        kind="document",
    )
    assert user_public == (
        (visibility_mod.public_organization_scope_id(7), 7),
        (visibility_mod.public_super_scope_id(), None),
    )

    # User-level without org -> global only.
    assert visibility_mod.inherited_visibility_scopes(
        owner_access_level=visibility_mod.ROLE_LEVEL_USER,
        organization_id=None,
        is_public=True,
        kind="document",
    ) == ((visibility_mod.public_super_scope_id(), None),)

    # Organization-level owner -> global only.
    assert visibility_mod.inherited_visibility_scopes(
        owner_access_level=visibility_mod.ROLE_LEVEL_ORGANIZATION,
        organization_id=7,
        is_public=True,
        kind="document",
    ) == ((visibility_mod.public_super_scope_id(), None),)

    # Super-level owner -> no inherited scopes.
    assert (
        visibility_mod.inherited_visibility_scopes(
            owner_access_level=visibility_mod.ROLE_LEVEL_SUPER,
            organization_id=7,
            is_public=True,
            kind="document",
        )
        == ()
    )

    user_chain = visibility_mod.retrieval_scope_chain(
        user_id=10,
        organization_id=7,
        access_level=visibility_mod.ROLE_LEVEL_USER,
    )
    assert user_chain == ((10, 7),)

    org_chain = visibility_mod.retrieval_scope_chain(
        user_id=10,
        organization_id=7,
        access_level=visibility_mod.ROLE_LEVEL_ORGANIZATION,
    )
    assert org_chain == (
        (10, 7),
        (visibility_mod.public_organization_scope_id(7), 7),
    )

    super_chain = visibility_mod.retrieval_scope_chain(
        user_id=10,
        organization_id=7,
        access_level=visibility_mod.ROLE_LEVEL_SUPER,
    )
    assert super_chain == (
        (10, 7),
        (visibility_mod.public_organization_scope_id(7), 7),
        (visibility_mod.public_super_scope_id(), None),
    )

    org_chain_no_org = visibility_mod.retrieval_scope_chain(
        user_id=10,
        organization_id=None,
        access_level=visibility_mod.ROLE_LEVEL_ORGANIZATION,
    )
    assert org_chain_no_org == ((10, None),)


def test_hierarchy_helpers_and_edges_with_focus():
    states = [
        _item("doc", item_scope="document", item_position=1),
        _item("sum", item_scope="summary", item_position=2),
        _item("c1", item_scope="chapter", chapter_index=1, item_position=3),
        _item(
            "p1",
            item_scope="paragraph",
            chapter_index=1,
            paragraph_index=1,
            item_position=4,
        ),
        _item(
            "p2",
            item_scope="paragraph",
            chapter_index=1,
            paragraph_index=2,
            item_position=5,
        ),
        _item(
            "k1",
            item_scope="chunk",
            chapter_index=1,
            paragraph_index=1,
            chunk_index=1,
            item_position=6,
        ),
        _item("raw", item_scope="raw", chapter_index=2, item_position=7),
        _item("t1", item_scope="transcript", source_kind="audio", item_position=8),
        _item(
            "s1",
            item_scope="segment",
            source_kind="audio",
            chapter_index=0,
            paragraph_index=0,
            item_position=9,
        ),
        _item(
            "s2",
            item_scope="segment",
            source_kind="audio",
            chapter_index=0,
            paragraph_index=0,
            item_position=10,
        ),
        _item("msg", item_scope="message", item_position=11),
        _item("custom", item_scope="custom", item_position=12),
    ]

    all_edges = hierarchy_mod.build_hierarchy_edges(
        items=states,
        metadata_load=json.loads,
    )
    edge_keys = {(edge.src_item_id, edge.dst_item_id, edge.edge_type) for edge in all_edges}

    assert ("doc", "c1", "HAS_CHILD") in edge_keys
    assert ("c1", "p1", "HAS_CHILD") in edge_keys
    assert ("p1", "k1", "HAS_CHILD") in edge_keys
    assert ("doc", "raw", "HAS_CHILD") in edge_keys
    assert ("s1", "s2", "NEXT") in edge_keys
    assert ("s2", "s1", "PREVIOUS") in edge_keys
    assert ("doc", "msg", "HAS_CHILD") not in edge_keys
    assert ("doc", "custom", "HAS_CHILD") not in edge_keys

    focus_chapter = hierarchy_mod.build_hierarchy_edges(
        items=states,
        metadata_load=json.loads,
        focus_item_id="c1",
    )
    focus_chapter_keys = {
        (edge.src_item_id, edge.dst_item_id, edge.edge_type) for edge in focus_chapter
    }
    assert ("c1", "p1", "HAS_CHILD") in focus_chapter_keys
    assert ("p1", "c1", "CHILD_OF") in focus_chapter_keys

    focus_segment = hierarchy_mod.build_hierarchy_edges(
        items=states,
        metadata_load=json.loads,
        focus_item_id="s1",
    )
    focus_segment_keys = {
        (edge.src_item_id, edge.dst_item_id, edge.edge_type) for edge in focus_segment
    }
    assert ("s1", "s2", "NEXT") in focus_segment_keys
    assert ("s2", "s1", "PREVIOUS") in focus_segment_keys

    bad_meta_item = SimpleNamespace(id="bad", metadata_json="ignored")
    state = hierarchy_mod._state_for_item(bad_meta_item, lambda _payload: "not-a-dict")
    assert state.scope == "raw"
    assert state.source_kind == "document"
    assert state.item_position is None

    assert hierarchy_mod._int_or_none("") is None
    assert hierarchy_mod._int_or_none("3") == 3
    assert hierarchy_mod._int_or_none(object()) is None
