from __future__ import annotations

import ctypes
import subprocess
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.windows_only

from democrai.core.infrastructure.sandbox.os.windows import low_integrity


def _proc() -> low_integrity.WindowsLowIntegrityProcess:
    # Only the wait() timeout/failure branches are exercised; they touch nothing
    # but self._process_handle and self.returncode, so dummy handles are enough.
    return low_integrity.WindowsLowIntegrityProcess(
        prepared=SimpleNamespace(),
        token_handle=0,
        process_handle=123,
        thread_handle=0,
        pid=999,
    )


def _patch_wait_result(monkeypatch, code: int) -> None:
    def fake_windll(name, *a, **k):
        return SimpleNamespace(WaitForSingleObject=lambda handle, ms: code)

    monkeypatch.setattr(ctypes, "WinDLL", fake_windll)


def test_wait_timeout_raises_timeoutexpired_not_timeouterror(monkeypatch):
    # WAIT_TIMEOUT must surface as subprocess.TimeoutExpired so the spawn broker's
    # _wait (which only catches TimeoutExpired) maps it to spawn_broker_wait_timeout.
    _patch_wait_result(monkeypatch, low_integrity.WAIT_TIMEOUT)
    proc = _proc()
    with pytest.raises(subprocess.TimeoutExpired):
        proc.wait(timeout=0.01)
    assert proc.returncode is None  # not consumed on timeout


def test_wait_failed_raises_oserror(monkeypatch):
    # 0xFFFFFFFF == WAIT_FAILED — an error, NOT a timeout.
    _patch_wait_result(monkeypatch, 0xFFFFFFFF)
    proc = _proc()
    with pytest.raises(OSError):
        proc.wait(timeout=0.01)
    assert proc.returncode is None
