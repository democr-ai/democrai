from __future__ import annotations

import re
from pathlib import Path

import yaml

from democrai.core.application.access_policy.manifest import parse_access_manifest_rules
from democrai.core.platform.agents.models import SkillMetadata

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def module_skill_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    if not root.exists() or not root.is_dir():
        return dirs
    for module_dir in sorted(root.iterdir()):
        candidate = module_dir / "skills"
        if candidate.exists() and candidate.is_dir():
            dirs.append(candidate)
    return dirs


def _discover_files(root: Path) -> tuple[str, ...]:
    if not root.exists() or not root.is_dir():
        return ()
    discovered: list[str] = []
    for candidate in sorted(root.rglob("*")):
        if candidate.is_file():
            discovered.append(candidate.relative_to(root).as_posix())
    return tuple(discovered)


def discover_assets(skill_root: Path) -> tuple[str, ...]:
    return _discover_files(skill_root / "assets")


def discover_scripts(skill_root: Path) -> tuple[str, ...]:
    return _discover_files(skill_root / "scripts")


def parse_skill_document(
    raw: str,
    path: Path,
    *,
    module_name: str = "",
) -> tuple[SkillMetadata, str]:
    frontmatter: dict = {}
    body = raw.strip()
    match = _FRONTMATTER_RE.match(raw)
    if match:
        try:
            loaded_frontmatter = yaml.safe_load(match.group(1))
        except Exception:
            loaded_frontmatter = {}
        frontmatter = loaded_frontmatter if isinstance(loaded_frontmatter, dict) else {}
        body = match.group(2).strip()

    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    name = normalize_text(frontmatter.get("name")) or (
        title_match.group(1).strip() if title_match else path.parent.name
    )
    description = normalize_text(frontmatter.get("description"))
    if not description:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        for line in lines:
            if not line.startswith("#"):
                description = line
                break

    def _tuple(key: str) -> tuple[str, ...]:
        raw_items = frontmatter.get(key)
        if not isinstance(raw_items, list):
            return ()
        values: list[str] = []
        for item in raw_items:
            text = normalize_text(item)
            if text:
                values.append(text)
        return tuple(values)

    metadata = SkillMetadata(
        name=name,
        description=description,
        title=normalize_text(frontmatter.get("title")) or name,
        summary=normalize_text(frontmatter.get("summary")),
        tags=_tuple("tags"),
        input_hint=normalize_text(frontmatter.get("input_hint")),
        usage=normalize_text(frontmatter.get("usage")),
        examples=_tuple("examples"),
        constraints=_tuple("constraints"),
        outputs=_tuple("outputs"),
        version=normalize_text(frontmatter.get("version")),
        author=normalize_text(frontmatter.get("author")),
        homepage=normalize_text(frontmatter.get("homepage")),
        allowed_tools=_tuple("allowed_tools"),
        asset_paths=discover_assets(path.parent),
        script_paths=discover_scripts(path.parent),
        module_name=normalize_text(module_name),
        path=str(path),
        access=list(
            parse_access_manifest_rules(
                frontmatter,
                subject_type="skill",
                subject_name=name,
            )
        ),
        metadata={
            key: value
            for key, value in frontmatter.items()
            if key
            not in {
                "name", "title", "description", "summary", "tags", "input_hint", "usage",
                "examples", "constraints", "outputs", "version", "author", "homepage", "allowed_tools",
                "access",
            }
        },
    )
    return metadata, body
