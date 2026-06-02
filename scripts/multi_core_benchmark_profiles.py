import os
import re
from dataclasses import dataclass

PROFILE_RE = re.compile(
    r"RequestProfile\] req=(?P<req>\S+) kind=(?P<kind>\S+) total=(?P<total>[0-9.]+)ms(?P<spans>.*)"
)


@dataclass(frozen=True)
class BenchmarkProfile:
    workers: int
    clients: int
    duration_seconds: int
    cycles: int
    nav_paths: tuple[str, ...]
    think_time_ms: int
    max_messages: int


PROFILE_PRESETS = {
    "stress": BenchmarkProfile(
        workers=16,
        clients=50,
        duration_seconds=30,
        cycles=30,
        nav_paths=("/components/_effects/yaml",),
        think_time_ms=0,
        max_messages=20,
    ),
    "interactive": BenchmarkProfile(
        workers=8,
        clients=12,
        duration_seconds=30,
        cycles=24,
        nav_paths=(
            "/components/_complex/card",
            "/components/_forms/button",
            "/components/_complex/datatable",
            "/components/_forms/model",
            "/components/_effects/yaml",
        ),
        think_time_ms=75,
        max_messages=14,
    ),
}


def parse_profile_line(line):
    match = PROFILE_RE.search(line)
    if not match:
        return None

    spans = {}
    raw_spans = match.group("spans").strip()
    if raw_spans:
        for part in raw_spans.split(","):
            item = part.strip()
            if not item or "=" not in item or not item.endswith("ms"):
                continue
            name, value = item.split("=", 1)
            try:
                spans[name] = float(value[:-2])
            except ValueError:
                continue

    return {
        "req": match.group("req"),
        "kind": match.group("kind"),
        "total_ms": float(match.group("total")),
        "spans": spans,
    }


def summarize_profile_log(log_path, raw_tail=12):
    if not os.path.exists(log_path):
        return "No profile log file found."

    parsed = []
    raw_lines = []
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "RequestProfile" not in line:
                continue
            raw_lines.append(line.rstrip())
            item = parse_profile_line(line)
            if item:
                parsed.append(item)

    if not parsed:
        return "No RequestProfile lines found."

    by_kind = {}
    for item in parsed:
        bucket = by_kind.setdefault(
            item["kind"],
            {"count": 0, "total_ms": 0.0, "spans": {}},
        )
        bucket["count"] += 1
        bucket["total_ms"] += item["total_ms"]
        for name, value in item["spans"].items():
            bucket["spans"][name] = bucket["spans"].get(name, 0.0) + value

    lines = []
    for kind in sorted(by_kind):
        bucket = by_kind[kind]
        count = bucket["count"]
        avg_total = bucket["total_ms"] / count
        lines.append(f"{kind}: count={count}, avg_total={avg_total:.2f}ms")
        top_spans = sorted(bucket["spans"].items(), key=lambda kv: kv[1], reverse=True)[
            :8
        ]
        for name, total in top_spans:
            lines.append(f"  avg_{name}={total / count:.2f}ms")

    if raw_lines:
        lines.append("Recent RequestProfile lines:")
        lines.extend(raw_lines[-raw_tail:])

    return "\n".join(lines)
