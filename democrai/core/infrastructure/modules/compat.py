from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from democrai.core.infrastructure.modules.constants import CURRENT_ARCH, CURRENT_PLATFORM
from democrai.core.platform.utils.env import SDK_VERSION


def parse_cron_field(field: str, minimum: int, maximum: int) -> set[int]:
    values: set[int] = set()
    for raw_part in field.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if part == "*":
            values.update(range(minimum, maximum + 1))
            continue

        step = 1
        if "/" in part:
            part, step_part = part.split("/", 1)
            step = max(1, int(step_part))

        if part == "*":
            start, end = minimum, maximum
        elif "-" in part:
            start_part, end_part = part.split("-", 1)
            start, end = int(start_part), int(end_part)
        else:
            start = end = int(part)

        start = max(minimum, start)
        end = min(maximum, end)
        values.update(range(start, end + 1, step))

    if not values:
        raise ValueError("empty cron field")
    return values


def cron_matches(expr: str, dt: datetime) -> bool:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron expressions must have 5 fields")

    minute, hour, day, month, weekday = parts
    cron_weekday = (dt.weekday() + 1) % 7
    weekday_values = {0 if value == 7 else value for value in parse_cron_field(weekday, 0, 7)}
    return (
        dt.minute in parse_cron_field(minute, 0, 59)
        and dt.hour in parse_cron_field(hour, 0, 23)
        and dt.day in parse_cron_field(day, 1, 31)
        and dt.month in parse_cron_field(month, 1, 12)
        and cron_weekday in weekday_values
    )


def next_cron_run(expr: str, now: datetime) -> datetime:
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    deadline = candidate + timedelta(days=366)
    while candidate <= deadline:
        if cron_matches(expr, candidate):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError(f"unable to resolve next run for cron '{expr}'")


def resolve_module_resource(module_path: str, resource: str) -> str:
    if not resource or not isinstance(resource, str):
        return resource

    if "." in resource and not resource.startswith(("http", "ric.", "<svg")):
        potential = os.path.abspath(os.path.join(module_path, resource))
        if os.path.exists(potential):
            return potential
    return resource


def module_version_match(current: str, required: str) -> bool:
    if not required.startswith(">="):
        return True

    req_val = required[2:]
    try:
        curr_parts = [int(p) for p in current.split(".")]
        req_parts = [int(p) for p in req_val.split(".")]
        max_len = max(len(curr_parts), len(req_parts))
        curr_parts.extend([0] * (max_len - len(curr_parts)))
        req_parts.extend([0] * (max_len - len(req_parts)))
        return curr_parts >= req_parts
    except ValueError:
        return current >= req_val


def validate_compatibility(module) -> bool:
    core_req = module.requirements.get("core")
    if core_req and not module._version_match(SDK_VERSION, core_req):
        module.error_message = f"Requires SDK {core_req}, but current is {SDK_VERSION}"
        return False

    py_req = module.requirements.get("python")
    if py_req:
        current_py = f"{sys.version_info.major}.{sys.version_info.minor}"
        if not module._version_match(current_py, py_req):
            module.error_message = f"Requires Python {py_req}, but current is {current_py}"
            return False

    if module.type == "extension":
        if CURRENT_PLATFORM not in module.platforms:
            module.error_message = f"Module does not support platform: {CURRENT_PLATFORM}"
            return False

        plat_info = module.platforms[CURRENT_PLATFORM]
        supported_archs = plat_info.get("arch", [])
        if CURRENT_ARCH not in supported_archs:
            module.error_message = f"Module does not support architecture: {CURRENT_ARCH}"
            return False

        abi = plat_info.get("abi")
        current_abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
        if abi and abi != current_abi:
            module.error_message = f"ABI mismatch: module is {abi}, core is {current_abi}"
            return False

    return True
