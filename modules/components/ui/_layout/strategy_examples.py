from __future__ import annotations


def value_examples(
    sdk,
    *,
    component: str,
    prop: str,
    type_: str,
    value: str,
    direct: str | None,
) -> dict:
    path = f"/components_layout/{component}/{prop}"
    data_path = f"components_layout/{component}/{prop}"
    return {
        "property": prop,
        "type": type_,
        "page_store": (
            f"{prop}: {{type: store, scope: page, path: {path}}}\n"
            f'stateUpdate(scope="page", values={{"{path}": {value}}})'
        ),
        "global_store": (
            f"{prop}: {{type: store, scope: global, path: {path}}}\n"
            f'stateUpdate(scope="global", values={{"{path}": {value}}})'
        ),
        "data": (
            f'{prop}: "@data/{data_path}"\n'
            f'dataModelUpdate({{"components_layout": {{"{component}": {{"{prop}": {value}}}}}}})'
        ),
        "direct": direct or sdk.i18n.t("components.layout.strategy.not_incremental"),
    }


def collection_examples(sdk, *, component: str, prop: str, type_: str) -> dict:
    path = f"/components_layout/{component}/{prop}"
    data_path = f"components_layout/{component}/{prop}"
    value = "[item_dict]"
    return {
        "property": prop,
        "type": type_,
        "page_store": (
            f"{prop}: {{type: store, scope: page, path: {path}}}\n"
            f'stateUpdate(scope="page", values={{"{path}": {value}}})'
        ),
        "global_store": (
            f"{prop}: {{type: store, scope: global, path: {path}}}\n"
            f'stateUpdate(scope="global", values={{"{path}": {value}}})'
        ),
        "data": (
            f'{prop}: "@data/{data_path}"\n'
            f'dataModelUpdate({{"components_layout": {{"{component}": {{"{prop}": {value}}}}}}})'
        ),
        "direct": f'ui_collection_append/remove("component_id", "{prop}", item_dict)',
    }


def static_examples(sdk, *, prop: str, type_: str) -> dict:
    note = sdk.i18n.t("components.layout.strategy.static_only")
    return {
        "property": prop,
        "type": type_,
        "page_store": note,
        "global_store": note,
        "data": note,
        "direct": note,
    }
