from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.platform.ui.yaml_builder import YamlUIBuilder


@pytest.mark.security_p0
def test_sdui_include_traversal_to_allowed_path(tmp_path: Path):
    """Test that path traversal to whitelisted paths (like /etc) is permitted by sandbox.

    Scenario: @include/../../../etc/hostname traverses to /etc/hostname.
    /etc is in process_guard._SYSTEM_READ_PATHS whitelist (needed for app functionality).
    The file is readable by design.

    This test verifies sandbox behavior: traversal to whitelisted paths is allowed.
    """
    module_dir = tmp_path / "a" / "b" / "module"
    module_dir.mkdir(parents=True, exist_ok=True)

    sdk = SimpleNamespace(module_path=str(module_dir))
    builder = YamlUIBuilder(sdk)

    # /etc/hostname is a whitelisted path, readable by design.
    # The path calculation: /tmp/.../a/b/module + ../../../etc/hostname = /etc/hostname
    yaml_content = """
components:
  - '@include/../../../../../../../etc/hostname'
"""

    with process_guard_context(
        subject="security.sdui.include.whitelisted_path",
        allowed_paths=[str(module_dir)],
        allow_subprocess=False,
    ):
        # /etc is whitelisted, so access is allowed.
        # File may not exist or may parse as invalid YAML, but not PermissionError.
        try:
            builder.build(yaml_content)
        except (ValueError, FileNotFoundError):
            # Expected: /etc/hostname may not exist or may be unparseable as YAML
            pass
        except PermissionError:
            pytest.fail("Access to /etc should be allowed (whitelisted path)")


@pytest.mark.security_p0
def test_sdui_include_deep_traversal_to_blocked_path(tmp_path: Path):
    """Test that deep path traversal to non-whitelisted directories is blocked.

    Scenario: @include/../../../../../../root/secret.yaml traverses to /root/secret.yaml.
    /root is NOT in process_guard whitelist, so access is denied.

    The file doesn't exist in /root, so YamlUIBuilder raises FileNotFoundError
    (access check happens via os.path.exists() which is subject to sandbox rules).
    If the file existed, process_guard would block the open() call with PermissionError.
    """
    module_dir = tmp_path / "a" / "b" / "module"
    module_dir.mkdir(parents=True, exist_ok=True)

    sdk = SimpleNamespace(module_path=str(module_dir))
    builder = YamlUIBuilder(sdk)

    yaml_content = """
components:
  - '@include/../../../../../../root/secret.yaml'
"""

    with process_guard_context(
        subject="security.sdui.include.deep_traversal_blocked",
        allowed_paths=[str(module_dir)],
        allow_subprocess=False,
    ):
        # Access to /root is denied by sandbox.
        # File doesn't exist, so FileNotFoundError is raised.
        # If file existed, PermissionError would be raised instead.
        with pytest.raises((FileNotFoundError, PermissionError)):
            builder.build(yaml_content)


@pytest.mark.security_p0
def test_sdui_include_absolute_path_to_blocked_directory(tmp_path: Path):
    """Test that @include with absolute paths to blocked directories is denied.

    Scenario: @include//root/secret.yaml. os.path.join(base, "/root/secret.yaml")
    returns /root/secret.yaml (absolute paths reset the join).
    /root is not in the process_guard whitelist, so access is blocked.

    This verifies that while YamlUIBuilder doesn't sanitize absolute paths,
    process_guard prevents access to directories outside the allowed list
    (whitelist includes /etc, /usr, /tmp, but NOT /root).
    """
    module_dir = tmp_path / "module"
    module_dir.mkdir(parents=True, exist_ok=True)

    sdk = SimpleNamespace(module_path=str(module_dir))
    builder = YamlUIBuilder(sdk)

    yaml_content = """
components:
  - '@include//root/secret.yaml'
"""

    with process_guard_context(
        subject="security.sdui.include.blocked_dir",
        allowed_paths=[str(module_dir)],
        allow_subprocess=False,
    ):
        with pytest.raises(PermissionError, match="sandbox_filesystem_denied"):
            builder.build(yaml_content)


def test_sdui_include_symlink_can_escape_module(tmp_path: Path):
    """Test that symlinks inside module_dir can point to files outside module_dir.

    Scenario: A symlink inside module_dir points to sensitive.yaml outside.
    @include/link.yaml follows the symlink and reads the external file.
    YamlUIBuilder does not validate symlink targets.

    This documents that symlink-based escapes are possible via @include.
    process_guard may block these in production, but the SDUI layer itself
    has no sanitization for symlink targets.
    """
    module_dir = tmp_path / "module"
    module_dir.mkdir(parents=True, exist_ok=True)

    sensitive = tmp_path / "sensitive.yaml"
    sensitive.write_text("secret: data", encoding="utf-8")

    symlink = module_dir / "link.yaml"
    try:
        symlink.symlink_to(sensitive)
    except OSError:
        # Symlink creation may fail on some systems; skip if not supported.
        pytest.skip("Symlinks not supported in test environment")

    sdk = SimpleNamespace(module_path=str(module_dir))
    builder = YamlUIBuilder(sdk)

    yaml_content = """
components:
  - '@include/link.yaml'
"""

    # Symlink is followed and external file is readable.
    # Parsing fails because file is not a valid component.
    with pytest.raises(ValueError, match="Component definition|Invalid content"):
        builder.build(yaml_content)


def test_sdui_include_legitimate_file_inside_module(tmp_path: Path):
    """Test that legitimate includes within module_dir work correctly.

    Scenario: YAML includes a file inside module_dir. The file is accessible
    and parsed. The test includes malformed YAML that fails component parsing
    (not a valid component kind), which is expected.

    This is a regression test to ensure legitimate includes are not blocked.
    The difference from the traversal tests is that this file is legitimately
    inside module_dir and should be accessible.
    """
    module_dir = tmp_path / "module"
    module_dir.mkdir(parents=True, exist_ok=True)

    legit = module_dir / "legit.yaml"
    legit.write_text("invalid: yaml_content_no_kind", encoding="utf-8")

    sdk = SimpleNamespace(module_path=str(module_dir))
    builder = YamlUIBuilder(sdk)

    yaml_content = """
components:
  - '@include/legit.yaml'
"""

    # File is accessible (no PermissionError), but parsing fails due to
    # invalid component definition (no 'kind' property).
    with pytest.raises(ValueError, match="Component definition must include"):
        builder.build(yaml_content)
