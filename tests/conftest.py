import os
import sys

import pytest


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import democrai.sdk as sdk_module

sys.modules["sdk"] = sdk_module


def pytest_collection_modifyitems(config, items):
    platform_markers = {
        "linux_only": (
            sys.platform.startswith("linux"),
            "test platform-dependent Linux-only behavior",
        ),
        "macos_only": (
            sys.platform == "darwin",
            "test platform-dependent macOS-only behavior",
        ),
        "windows_only": (
            sys.platform == "win32",
            "test platform-dependent Windows-only behavior",
        ),
    }
    for item in items:
        for marker_name, (enabled, reason) in platform_markers.items():
            if item.get_closest_marker(marker_name) and not enabled:
                item.add_marker(pytest.mark.skip(reason=reason))


def _install_process_guard_test_compat() -> None:
    from democrai.core.application.access_policy import AccessManifestRule
    from democrai.core.application.access_policy import AccessResource
    from democrai.core.application.access_policy import AccessSubject
    from democrai.core.infrastructure.sandbox import process_guard as process_guard_mod

    original = process_guard_mod.process_guard_context
    if getattr(original, "_tests_compat", False):
        return

    def _rule(subject_kind: str, subject: str, resource_type: str, operation: str, target: str):
        return AccessManifestRule(
            subject=AccessSubject.create(subject_kind, subject),
            resource=AccessResource.create(
                resource_type=resource_type,
                operation=operation,
                target=target,
            ),
        )

    class _CompatProcessGuardContext:
        _tests_compat = True

        def __init__(
            self,
            *,
            allowed_paths=None,
            allowed_targets=None,
            include_runtime_paths=None,
            access=None,
            subject: str,
            subject_kind: str = "module",
            **kwargs,
        ):
            rules = list(access or [])
            for path in list(allowed_paths or []):
                for operation in ("read", "create", "modify", "delete", "execute"):
                    rules.append(_rule(subject_kind, subject, "filesystem", operation, str(path)))
            for target in list(allowed_targets or []):
                for operation in ("connect", "receive", "send"):
                    rules.append(_rule(subject_kind, subject, "network", operation, str(target)))
            if include_runtime_paths is not None:
                kwargs["include_runtime_access"] = include_runtime_paths
            self.subject = subject
            self.subject_kind = subject_kind
            self.access = tuple(rules)
            self.include_runtime_access = kwargs.get("include_runtime_access", True)
            self._inner = original(
                subject=subject,
                subject_kind=subject_kind,
                access=rules,
                **kwargs,
            )

        def __enter__(self):
            return self._inner.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self._inner.__exit__(exc_type, exc, tb)

    process_guard_mod.process_guard_context = _CompatProcessGuardContext


_install_process_guard_test_compat()
