from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalMediaRequest:
    module_name: str
    url: str
    client_generation: int = 0
    force_refresh: bool = False


def parse_external_media_request(
    payload: object,
    *,
    include_force_refresh: bool = False,
) -> ExternalMediaRequest:
    if not isinstance(payload, dict):
        raise ValueError("invalid_media_request")

    module_name = payload.get("module_name")
    url = payload.get("url")
    if not isinstance(module_name, str) or not isinstance(url, str):
        raise ValueError("invalid_media_request")
    if not module_name or not url:
        raise ValueError("invalid_media_request")

    client_generation = payload.get("client_generation", 0)
    if client_generation is None:
        client_generation = 0
    if not isinstance(client_generation, int) or isinstance(client_generation, bool):
        raise ValueError("invalid_media_request")

    force_refresh = False
    if include_force_refresh:
        force_refresh = payload.get("force_refresh", False)
        if not isinstance(force_refresh, bool):
            raise ValueError("invalid_media_request")
    return ExternalMediaRequest(
        module_name=module_name,
        url=url,
        client_generation=client_generation,
        force_refresh=force_refresh,
    )


def build_external_media_error(
    *,
    error: str,
    module_name: str,
    url: str,
    client_generation: int = 0,
    error_code: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "error": error,
        "module_name": module_name,
        "url": url,
        "client_generation": client_generation,
    }
    if error_code:
        payload["error_code"] = error_code
    return payload
