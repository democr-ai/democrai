from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from democrai.sdk.ui import Builder

from . import module_routes as _module_routes
from . import router_resolution as _resolution


def normalize_path(p: str) -> str:
    """
    Normalizes a URL-like path by removing trailing slashes, dots, and duplicate slashes.

    :param p: The raw path string.
    :return: A normalized path string without a leading slash.
    """
    if p is None:
        return ""
    p = p.strip().replace("\\", "/")
    p = re.sub(r"/{2,}", "/", p)
    p = p.split("?", 1)[0].split("#", 1)[0]
    p = posixpath.normpath(p)
    if p == ".":
        p = ""
    return p.lstrip("/")


_PARAM = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")
_CATCHALL = re.compile(r"\[\.\.\.([A-Za-z_][A-Za-z0-9_]*)\]")


@dataclass(frozen=True)
class CompiledRoute:
    pattern: str
    regex: re.Pattern
    param_names: Tuple[str, ...]
    score: Tuple[int, int, int, int]

    def match(self, path: str) -> Optional[Dict[str, str]]:
        """
        Tests if a path matches this route's regex and extracts parameters.

        :param path: The normalized path to test.
        :return: A dictionary of extracted parameters if matched, else None.
        """
        m = self.regex.match(path)
        if not m:
            return None
        d = m.groupdict()
        for k, v in list(d.items()):
            if v is None:
                d[k] = ""
        return d


def _analyze_segments(pattern: str) -> Tuple[int, int, int, int]:
    p = normalize_path(pattern)
    segs = [s for s in p.split("/") if s != ""]
    static = dyn = catch = 0
    for s in segs:
        if _CATCHALL.fullmatch(s):
            catch += 1
        elif _PARAM.fullmatch(s):
            dyn += 1
        else:
            static += 1
    return (static, -dyn, -catch, len(segs))


def compile_pattern(pattern: str, *, allow_trailing_slash: bool = True) -> CompiledRoute:
    p = normalize_path(pattern)
    segs = [s for s in p.split("/") if s != ""]
    param_names: List[str] = []
    regex_parts: List[str] = ["^"]

    for i, seg in enumerate(segs):
        regex_parts.append("/" if i > 0 else "")
        m_c = _CATCHALL.fullmatch(seg)
        if m_c:
            name = m_c.group(1)
            param_names.append(name)
            if i == 0:
                regex_parts[-1] = ""
                regex_parts.append(rf"(?P<{name}>.*)?")
            else:
                regex_parts.pop()
                regex_parts.append(rf"(?:/(?P<{name}>.*))?")
            continue

        m_p = _PARAM.fullmatch(seg)
        if m_p:
            name = m_p.group(1)
            param_names.append(name)
            regex_parts.append(rf"(?P<{name}>[^/]+)")
            continue

        regex_parts.append(re.escape(seg))

    regex_parts.append(r"/?$" if allow_trailing_slash else r"$")
    regex = re.compile("".join(regex_parts))
    return CompiledRoute(pattern=pattern, regex=regex, param_names=tuple(param_names), score=_analyze_segments(pattern))


@dataclass
class MatchResult:
    pattern: str
    params: Dict[str, str]
    resolved_path: str


def materialize(pattern: str, params: Dict[str, str]) -> str:
    out = pattern
    for k, v in params.items():
        out = out.replace(f"[{k}]", v)
        out = out.replace(f"[...{k}]", v)
    return normalize_path(out)


class _Router:
    def __init__(self):
        self._routes: List[CompiledRoute] = []

    def set_patterns(self, patterns: Iterable[str], *, allow_trailing_slash: bool = True):
        compiled = [compile_pattern(p, allow_trailing_slash=allow_trailing_slash) for p in patterns]
        compiled.sort(key=lambda r: r.score, reverse=True)
        self._routes = compiled

    def add_patterns(self, patterns: Iterable[str], *, allow_trailing_slash: bool = True) -> None:
        existing = {route.pattern for route in self._routes}
        new_patterns = list(existing)
        for pattern in patterns:
            if pattern not in existing:
                new_patterns.append(pattern)
        self.set_patterns(new_patterns, allow_trailing_slash=allow_trailing_slash)

    def match(self, request_path: str) -> Optional[MatchResult]:
        """
        Matches a request path against all registered routes.

        :param request_path: The raw request path (e.g., from a URL).
        :return: A MatchResult object if a match is found, else None.
        """
        path = normalize_path(request_path)
        for r in self._routes:
            params = r.match(path)
            if params is not None:
                return MatchResult(pattern=r.pattern, params=params, resolved_path=materialize(r.pattern, params))
        return None


ROUTER = _Router()
_ROUTE_CACHE_WARMED_PLUGINS: set[str] = set()


def printErrorResponse(code: int, message: str) -> Builder:
    builder = Builder()
    from democrai.sdk.components.domains.text.text import Text

    builder.add(Text(str(code), message))
    return builder


class Router:
    """
    Public API for the Democr.ai routing system.

    Provides methods for path parsing, route resolution, and cache management.
    The Router delegates the actual resolution to the internal `_resolution` module.
    """
    @staticmethod
    def invalidate_module_routes(module_name: str) -> None:
        _module_routes.invalidate_module_routes(
            ROUTER,
            normalize_path,
            _ROUTE_CACHE_WARMED_PLUGINS,
            module_name,
        )

    @staticmethod
    def _discover_module_patterns(module) -> List[str]:
        return _module_routes.discover_module_patterns(module)

    @staticmethod
    def _ensure_module_routes(module) -> None:
        _module_routes.ensure_module_routes(ROUTER, _ROUTE_CACHE_WARMED_PLUGINS, module)

    @staticmethod
    def parse_path(path: str):
        """
        Parses a full path or URL into its constituent parts.

        :param path: The path or URL string (e.g., '/chat/main?id=1').
        :return: A tuple of (app_name, page_path, params_dict).
        """
        parsed = urlparse(path)
        path_parts = [part for part in parsed.path.strip("/").split("/") if part]
        app_name = path_parts[0] if path_parts else "dashboard"
        page_path = "/".join(path_parts[1:]) if len(path_parts) > 1 else "index"
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        return app_name, page_path, params

    @staticmethod
    def warmup():
        return _resolution.warmup()

    @staticmethod
    async def resolve(path: str, session: dict, extra_params: Optional[dict] = None) -> Builder:
        """
        Resolves a path into a UI component builder (Builder).

        :param path: The path to resolve.
        :param session: The current user session.
        :param extra_params: Optional additional parameters to merge into the resolution.
        :return: An Builder instance.
        """
        return await _resolution.resolve(path, session, extra_params)
