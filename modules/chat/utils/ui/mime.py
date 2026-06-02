from __future__ import annotations


def attachment_accept(module_sdk) -> str:
    values = module_sdk.extractors.list_ingestible_mime_types()
    mimes = sorted(values)
    return ",".join(mimes)
