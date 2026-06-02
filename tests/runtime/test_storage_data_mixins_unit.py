from __future__ import annotations

from democrai.core.infrastructure.storage.data import mixins as mixins_mod


def test_storage_data_mixins_contract():
    assert mixins_mod.module_table_name("demo", "items") == "p_demo_items"
    assert mixins_mod.UserMixin.user_id is not None
    assert mixins_mod.UserMixin.organization_id is not None
    assert mixins_mod.UserMixin.created_at is not None
    assert mixins_mod.UserMixin.updated_at is not None
