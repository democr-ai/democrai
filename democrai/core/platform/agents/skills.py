from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable

from democrai.core.platform.agents.models import SkillDefinition
from democrai.core.platform.agents.models import SkillMetadata
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import get_builtin_skills_dir
from democrai.core.runtime.foundation.paths import get_runtime_module_dirs
from democrai.core.runtime.foundation.paths import get_user_skills_dir
from democrai.core.platform.agents.skills_io import (
    normalize_text as _normalize_text,
    parse_skill_document,
    module_skill_dirs as _module_skill_dirs,
)

# Retained for compatibility with callers importing this regex constant.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class SkillLoader:
    """Loads skills stored in the common `skill-name/SKILL.md` filesystem format."""

    def __init__(
        self,
        skill_dirs: Iterable[str | Path] | None = None,
        *,
        include_default_dirs: bool = True,
    ):
        self.skill_dirs = tuple(
            self.default_skill_dirs(skill_dirs)
            if include_default_dirs
            else self._dedupe_dirs([] if skill_dirs is None else skill_dirs)
        )

    @staticmethod
    def default_skill_dirs(
        extra_dirs: Iterable[str | Path] | None = None,
    ) -> list[Path]:
        roots: list[Path] = [
            Path(get_builtin_skills_dir()),
            Path(get_user_skills_dir()),
        ]
        for modules_dir in get_runtime_module_dirs():
            roots.extend(_module_skill_dirs(Path(modules_dir)))

        ctx = app_ctx()
        cfg = getattr(ctx, "config", None)
        configured = cfg.get("agents.skills.paths", []) if cfg else []
        if isinstance(configured, str):
            configured = [configured]
        configured_dirs = configured if isinstance(configured, list) else []
        for raw in configured_dirs:
            roots.append(Path(str(raw)).expanduser())

        extra_dir_values = [] if extra_dirs is None else extra_dirs
        for raw in extra_dir_values:
            roots.append(Path(str(raw)).expanduser())

        deduped: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            _append_deduped(deduped, seen, root)
        return deduped

    @staticmethod
    def _dedupe_dirs(dirs: Iterable[str | Path]) -> list[Path]:
        deduped: list[Path] = []
        seen: set[Path] = set()
        for root in dirs:
            _append_deduped(deduped, seen, Path(root).expanduser())
        return deduped

    def discover(self) -> list[SkillDefinition]:
        discovered: list[SkillDefinition] = []
        for root in self.skill_dirs:
            if not root.exists() or not root.is_dir():
                continue
            for candidate in sorted(root.iterdir()):
                skill_md = candidate / "SKILL.md"
                if candidate.is_dir() and skill_md.exists():
                    skill = self.load_from_path(skill_md)
                    if skill is not None:
                        discovered.append(skill)
        return discovered

    def load_from_path(self, skill_md_path: str | Path) -> SkillDefinition | None:
        path = Path(skill_md_path)
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            return None

        metadata, body = self._parse(raw, path)
        if not metadata.name or not metadata.description:
            return None
        return SkillDefinition(metadata=metadata, content=body, root_dir=path.parent)

    def get(self, name: str) -> SkillDefinition | None:
        normalized = _normalize_text(name).lower()
        for skill in self.discover():
            if skill.metadata.name.lower() == normalized:
                return skill
        return None

    def list_assets(self, skill: SkillDefinition | str) -> list[str]:
        resolved = self._resolve_skill(skill)
        if resolved is None:
            return []
        return list(resolved.metadata.asset_paths)

    def resolve_asset(self, skill: SkillDefinition | str, asset_path: str) -> Path | None:
        resolved = self._resolve_skill(skill)
        if resolved is None:
            return None

        normalized = asset_path.strip().replace("\\", "/") if isinstance(asset_path, str) else ""
        if not normalized:
            return None
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            return None
        if normalized not in resolved.metadata.asset_paths:
            return None

        candidate = (resolved.assets_dir / normalized).resolve()
        assets_root = resolved.assets_dir.resolve()
        if not str(candidate).startswith(str(assets_root)):
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    def read_asset_text(
        self,
        skill: SkillDefinition | str,
        asset_path: str,
        *,
        encoding: str = "utf-8",
    ) -> str | None:
        candidate = self.resolve_asset(skill, asset_path)
        if candidate is None:
            return None
        try:
            return candidate.read_text(encoding=encoding)
        except Exception:
            return None

    def match(
        self,
        query: str,
        *,
        limit: int = 5,
        allowed_names: Iterable[str] | None = None,
    ) -> list[SkillDefinition]:
        query_tokens = {
            token.lower()
            for token in re.findall(
                r"[A-Za-z0-9_/-]+",
                query if isinstance(query, str) else "",
            )
            if token.strip()
        }
        allowed = {
            item.lower()
            for item in ([] if allowed_names is None else allowed_names)
            if isinstance(item, str)
        }
        scored: list[tuple[int, SkillDefinition]] = []
        for skill in self.discover():
            if allowed and skill.metadata.name.lower() not in allowed:
                continue
            haystack = " ".join(
                [
                    skill.metadata.name,
                    skill.metadata.description,
                    " ".join(skill.metadata.tags),
                    skill.metadata.input_hint,
                ]
            ).lower()
            score = 0
            for token in query_tokens:
                if token in haystack:
                    score += 1
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda item: (item[0], item[1].metadata.name), reverse=True)
        return [skill for _, skill in scored[:limit]]

    def render_available_skills_xml(
        self,
        *,
        allowed_names: Iterable[str] | None = None,
    ) -> str:
        allowed = {
            item.lower()
            for item in ([] if allowed_names is None else allowed_names)
            if isinstance(item, str)
        }
        items: list[str] = ["<available_skills>"]
        for skill in self.discover():
            if allowed and skill.metadata.name.lower() not in allowed:
                continue
            items.append(
                "  <skill"
                f' name="{html.escape(skill.metadata.name)}"'
                f' location="{html.escape(skill.metadata.path)}">'
            )
            items.append(
                f"    <description>{html.escape(skill.metadata.description)}</description>"
            )
            if skill.metadata.input_hint:
                items.append(
                    f"    <input_hint>{html.escape(skill.metadata.input_hint)}</input_hint>"
                )
            if skill.metadata.summary:
                items.append(
                    f"    <summary>{html.escape(skill.metadata.summary)}</summary>"
                )
            if skill.metadata.usage:
                items.append(
                    f"    <usage>{html.escape(skill.metadata.usage)}</usage>"
                )
            if skill.metadata.allowed_tools:
                items.append(
                    f"    <allowed_tools>{html.escape(', '.join(skill.metadata.allowed_tools))}</allowed_tools>"
                )
            if skill.metadata.tags:
                items.append(
                    f"    <tags>{html.escape(', '.join(skill.metadata.tags))}</tags>"
                )
            if skill.metadata.asset_paths:
                items.append(
                    f"    <assets>{html.escape(', '.join(skill.metadata.asset_paths))}</assets>"
                )
            if skill.metadata.script_paths:
                items.append(
                    f"    <scripts>{html.escape(', '.join(skill.metadata.script_paths))}</scripts>"
                )
            items.append("  </skill>")
        items.append("</available_skills>")
        return "\n".join(items)

    @staticmethod
    def render_activated_skills(skills: Iterable[SkillDefinition]) -> str:
        lines: list[str] = ["<activated_skills>"]
        for skill in skills:
            lines.append(f'  <skill name="{html.escape(skill.metadata.name)}">')
            if skill.metadata.input_hint:
                lines.append(
                    f"    <input_hint>{html.escape(skill.metadata.input_hint)}</input_hint>"
                )
            if skill.metadata.usage:
                lines.append(f"    <usage>{html.escape(skill.metadata.usage)}</usage>")
            if skill.metadata.constraints:
                lines.append(
                    f"    <constraints>{html.escape('; '.join(skill.metadata.constraints))}</constraints>"
                )
            if skill.metadata.asset_paths:
                lines.append(
                    f"    <assets>{html.escape(', '.join(skill.metadata.asset_paths))}</assets>"
                )
            if skill.metadata.script_paths:
                lines.append(
                    f"    <scripts>{html.escape(', '.join(skill.metadata.script_paths))}</scripts>"
                )
            lines.append("```markdown")
            lines.append(skill.content.rstrip())
            lines.append("```")
            lines.append("  </skill>")
        lines.append("</activated_skills>")
        return "\n".join(lines)

    def _parse(self, raw: str, path: Path) -> tuple[SkillMetadata, str]:
        return parse_skill_document(
            raw,
            path,
            module_name=_module_name_from_skill_path(path),
        )

    def _resolve_skill(self, skill: SkillDefinition | str) -> SkillDefinition | None:
        if isinstance(skill, SkillDefinition):
            return skill
        return self.get(str(skill))


def _module_name_from_skill_path(path: Path) -> str:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "skills" and index > 0:
            return parts[index - 1]
    return ""


def _append_deduped(deduped: list[Path], seen: set[Path], root: Path) -> None:
    resolved = root.expanduser()
    if resolved in seen:
        return
    seen.add(resolved)
    deduped.append(resolved)
