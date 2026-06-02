from __future__ import annotations

from enum import StrEnum


class ResourceType(StrEnum):
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    SYSTEM_DEPENDENCY = "system_dependency"


class AccessOperation(StrEnum):
    CONNECT = "connect"
    RECEIVE = "receive"
    SEND = "send"
    READ = "read"
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    EXECUTE = "execute"


_RESOURCE_ALIASES = {
    "url": ResourceType.NETWORK,
    "network": ResourceType.NETWORK,
    "filesystem": ResourceType.FILESYSTEM,
    "file": ResourceType.FILESYSTEM,
    "path": ResourceType.FILESYSTEM,
    "system_dependency": ResourceType.SYSTEM_DEPENDENCY,
    "dependency": ResourceType.SYSTEM_DEPENDENCY,
}

_NETWORK_OPERATIONS = {
    AccessOperation.CONNECT,
    AccessOperation.RECEIVE,
    AccessOperation.SEND,
}

_FILESYSTEM_OPERATIONS = {
    AccessOperation.READ,
    AccessOperation.CREATE,
    AccessOperation.MODIFY,
    AccessOperation.DELETE,
    AccessOperation.EXECUTE,
}


def verify_resource_type(value: str | ResourceType) -> ResourceType:
    if isinstance(value, ResourceType):
        return value
    resource_type = _RESOURCE_ALIASES.get(value)
    if resource_type is None:
        raise ValueError(f"unsupported_access_resource_type:{value}")
    return resource_type


def verify_operation(value: str | AccessOperation) -> AccessOperation:
    if isinstance(value, AccessOperation):
        return value
    try:
        return AccessOperation(value)
    except ValueError as exc:
        raise ValueError(f"unsupported_access_operation:{value}") from exc


def validate_operation_for_resource(
    resource_type: str | ResourceType,
    operation: str | AccessOperation,
) -> AccessOperation:
    resolved_resource_type = verify_resource_type(resource_type)
    resolved_operation = verify_operation(operation)
    if resolved_resource_type == ResourceType.NETWORK:
        if resolved_operation not in _NETWORK_OPERATIONS:
            raise ValueError(
                "invalid_access_operation_for_resource:"
                f"{resolved_resource_type}:{resolved_operation}",
            )
        return resolved_operation
    if resolved_resource_type == ResourceType.FILESYSTEM:
        if resolved_operation not in _FILESYSTEM_OPERATIONS:
            raise ValueError(
                "invalid_access_operation_for_resource:"
                f"{resolved_resource_type}:{resolved_operation}",
            )
        return resolved_operation
    if resolved_resource_type == ResourceType.SYSTEM_DEPENDENCY:
        if resolved_operation != AccessOperation.EXECUTE:
            raise ValueError(
                "invalid_access_operation_for_resource:"
                f"{resolved_resource_type}:{resolved_operation}",
            )
        return resolved_operation
    raise ValueError(f"unsupported_access_resource_type:{resolved_resource_type}")


def operation_for_http_method(method: str) -> AccessOperation:
    normalized = method.strip().upper() if isinstance(method, str) else ""
    if normalized in {"GET", "HEAD", "OPTIONS"}:
        return AccessOperation.RECEIVE
    if normalized in {"POST", "PUT", "PATCH", "DELETE"}:
        return AccessOperation.SEND
    raise ValueError(f"unsupported_http_access_method:{normalized}")
