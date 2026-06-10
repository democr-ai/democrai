from __future__ import annotations

import sys
import threading
import uuid
from types import SimpleNamespace

import pytest

import democrai.core.application.ai.engine.runtime.worker as engine_subject_mod
import democrai.core.application.knowledge.extractor.worker_subject as extractor_subject_mod
import democrai.core.runtime.dependencies.installer as installer_mod
from democrai.core.infrastructure.process.child_failure import ChildProcessFailure


def test_child_failure_format_is_stable_and_greppable():
    message = ChildProcessFailure.format(
        subject="engine:demo",
        stage="invoke",
        error="engine_worker_error",
        returncode=126,
        details={"engine_id": "demo", "operation": "invoke"},
        traceback="Traceback (most recent call last):\n  boom",
        output_tail="line-1\nline-2",
    )

    first_line, *rest = message.splitlines()
    assert first_line == (
        "[child-failure subject=engine:demo stage=invoke rc=126]"
        " engine_worker_error engine_id=demo operation=invoke"
    )
    assert "Traceback (most recent call last):" in message
    assert "[stderr tail]" in message
    assert rest[-1] == "line-2"


def test_child_failure_format_truncates_only_the_tail():
    long_tail = "x" * (ChildProcessFailure.OUTPUT_TAIL_CHARS + 500)
    message = ChildProcessFailure.format(
        subject="s",
        stage="st",
        error="err",
        traceback="tb-content",
        output_tail=long_tail,
    )
    assert "tb-content" in message
    tail_section = message.split("[stderr tail]\n", 1)[1]
    assert len(tail_section) == ChildProcessFailure.OUTPUT_TAIL_CHARS


def test_child_failure_wrap_never_rewrites_original():
    original = "inner_error\nTraceback (most recent call last):\n  detail"
    wrapped = ChildProcessFailure.wrap("outer context", original)
    assert wrapped.startswith("outer context\n")
    assert wrapped.endswith(original)
    assert ChildProcessFailure.wrap("only prefix", "") == "only prefix"


def test_engine_request_failure_logs_traceback_and_stderr_tail(monkeypatch):
    fixed_id = uuid.uuid4()
    monkeypatch.setattr(engine_subject_mod.uuid, "uuid4", lambda: fixed_id)

    logged: list[str] = []
    monkeypatch.setattr(
        engine_subject_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(error=logged.append)),
    )

    subject = engine_subject_mod.EngineWorkerSubject.__new__(
        engine_subject_mod.EngineWorkerSubject
    )
    subject._engine_id = "demo"
    subject._process = SimpleNamespace(poll=lambda: None)
    subject._control_channel = SimpleNamespace(send_json=lambda *_a, **_k: None)
    subject._write_lock = threading.Lock()
    subject._response_condition = threading.Condition()
    subject._closed = False
    subject._responses = {
        fixed_id.hex: {
            "ok": False,
            "error": "worker_boom",
            "traceback": "Traceback (most recent call last):\n  worker detail",
        }
    }
    subject._stderr_tail = ["sandbox denied /dev/nvidia0"]
    subject._stderr_lock = threading.Lock()

    with pytest.raises(RuntimeError, match="worker_boom"):
        subject._request("invoke", {"method": "chat"})

    assert logged
    block = logged[0]
    assert "[child-failure subject=engine:demo stage=invoke]" in block
    assert "Traceback (most recent call last):" in block
    assert "worker detail" in block
    assert "[stderr tail]" in block
    assert "sandbox denied /dev/nvidia0" in block


def test_extractor_request_failure_logs_traceback_and_stderr_tail(monkeypatch):
    fixed_id = uuid.uuid4()
    monkeypatch.setattr(extractor_subject_mod.uuid, "uuid4", lambda: fixed_id)

    logged: list[str] = []
    monkeypatch.setattr(
        extractor_subject_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(error=logged.append)),
    )

    subject = extractor_subject_mod.ExtractorWorkerSubject.__new__(
        extractor_subject_mod.ExtractorWorkerSubject
    )
    subject._extractor_id = "docling"
    subject._phase = "runtime"
    subject._process = SimpleNamespace(poll=lambda: None)
    subject._control_channel = SimpleNamespace(send_json=lambda *_a, **_k: None)
    subject._write_lock = threading.Lock()
    subject._response_condition = threading.Condition()
    subject._closed = False
    subject._responses = {
        fixed_id.hex: {
            "ok": False,
            "error": "extract_boom",
            "traceback": "Traceback (most recent call last):\n  extractor detail",
        }
    }
    subject._stderr_tail = ["libGL.so.1 missing"]
    subject._stderr_lock = threading.Lock()
    subject._stdout_tail = []
    subject._stdout_lock = threading.Lock()

    with pytest.raises(RuntimeError, match="extract_boom"):
        subject._request("extract", {"config": {}})

    assert logged
    block = logged[0]
    assert "[child-failure subject=extractor:docling stage=extract]" in block
    assert "extractor detail" in block
    assert "[stderr tail]" in block
    assert "libGL.so.1 missing" in block


def test_extractor_output_tail_falls_back_to_stdout():
    subject = extractor_subject_mod.ExtractorWorkerSubject.__new__(
        extractor_subject_mod.ExtractorWorkerSubject
    )
    subject._stderr_tail = []
    subject._stderr_lock = threading.Lock()
    subject._stdout_tail = ["install progress line"]
    subject._stdout_lock = threading.Lock()

    tail, label = subject._worker_output_tail()
    assert tail == "install progress line"
    assert label == "stdout tail"

    subject._stderr_tail = ["real error"]
    tail, label = subject._worker_output_tail()
    assert tail == "real error"
    assert label == "stderr tail"


def test_installer_subprocess_failure_carries_output_tail():
    with pytest.raises(RuntimeError) as excinfo:
        installer_mod._run_install_subprocess(
            [
                sys.executable,
                "-c",
                "print('resolving deps'); print('boom: no matching distribution'); raise SystemExit(3)",
            ],
            label="[Installer] test install",
        )

    message = str(excinfo.value)
    assert "[child-failure subject=installer stage=[Installer] test install rc=3]" in message
    assert "installer_subprocess_failed" in message
    assert "[output tail]" in message
    assert "boom: no matching distribution" in message
