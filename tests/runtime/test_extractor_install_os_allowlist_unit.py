from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


class _FakeStdout:
    def __init__(self, lines: list[bytes], events: list[str]) -> None:
        self._lines = list(lines)
        self._events = events

    async def readline(self) -> bytes:
        self._events.append("read")
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeProcess:
    def __init__(self, stdout: _FakeStdout) -> None:
        self.pid = 12345
        self.stdout = stdout
        self.returncode = 0
        self.terminated = False

    async def wait(self) -> int:
        return int(self.returncode)

    def terminate(self) -> None:
        self.terminated = True


@pytest.mark.asyncio
async def test_extractor_install_process_applies_os_allowlist_to_child_pid(monkeypatch):
    import democrai.core.application.knowledge.extractor.install_events as mod

    events: list[str] = []
    payload = json.dumps({"status": "installed"}, sort_keys=True)
    fake_process = _FakeProcess(
        _FakeStdout(
            [
                f"{mod.EXTRACTOR_INSTALL_PROCESS_RESULT_PREFIX}{payload}\n".encode(
                    "utf-8"
                ),
            ],
            events,
        )
    )

    async def _create_subprocess_exec(*_args, **_kwargs):
        events.append("spawn")
        return fake_process

    async def _apply(pid):
        events.append(f"apply:{pid}")

    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", _create_subprocess_exec)
    monkeypatch.setattr(mod, "_apply_os_network_allowlist_to_install_process", _apply)
    monkeypatch.setattr(mod, "emit_extractor_install_output", lambda *_a, **_k: None)
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(get=lambda *_a, **_k: False),
            runtime_module_paths=("modules",),
            runtime_engine_paths=("engines",),
            runtime_extractor_paths=("extractors",),
        ),
    )

    result = await mod._run_extractor_install_runtime_process(
        extractor_id="docling",
        force=False,
        node_id="node-1",
        event_id="event-1",
        source_node_id=None,
        install_config={"ocr_engine": "rapidocr"},
    )

    assert result == {"status": "installed"}
    assert events[:3] == ["spawn", "apply:12345", "read"]
