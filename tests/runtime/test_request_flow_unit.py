from __future__ import annotations

from types import SimpleNamespace

import democrai.core.runtime.observability.request_flow as flow_mod


class _Logger:
    def __init__(self):
        self.info_calls = []

    def info(self, *args, **kwargs):
        self.info_calls.append((args, kwargs))


def _ctx(logger=None, config=None):
    return SimpleNamespace(
        logger=logger,
        config=config,
        request_flow_tracer=None,
    )


def test_request_flow_tracer_records_summary_and_recent(monkeypatch):
    logger = _Logger()
    ctx = _ctx(
        logger=logger,
        config=SimpleNamespace(get=lambda key, default=None: "summary" if key == "debug.request_flow.level" else default),
    )
    monkeypatch.setattr(flow_mod, "app_ctx", lambda: ctx)
    tracer = flow_mod.RequestFlowTracer(buffer_size=3)

    tracer.start("req-1", "userAction", message_type="userAction", action_name="chat.send")
    tracer.step("req-1", "context.built", user="alice", organization_id="org-a")
    summary = tracer.finish("req-1", outcome="ok", response_count=2)

    assert summary is not None
    assert summary["request_id"] == "req-1"
    assert summary["request_kind"] == "userAction"
    assert summary["outcome"] == "ok"
    assert summary["response_count"] == 2
    assert summary["steps"] == ["context.built"]
    assert tracer.get("req-1")["request_id"] == "req-1"
    assert tracer.recent(limit=1)[0]["request_id"] == "req-1"
    assert logger.info_calls


def test_request_flow_tracer_logs_verbose_steps_and_sanitizes(monkeypatch):
    logger = _Logger()
    ctx = _ctx(
        logger=logger,
        config=SimpleNamespace(get=lambda key, default=None: "verbose" if key == "debug.request_flow.level" else default),
    )
    monkeypatch.setattr(flow_mod, "app_ctx", lambda: ctx)
    tracer = flow_mod.RequestFlowTracer(buffer_size=2)

    tracer.start(
        "req-2",
        "bindingAction",
        payload={"secret": "value"},
        large_text="x" * 220,
    )
    tracer.step("req-2", "binding.dispatch.start", result={"a": 1})
    tracer.finish("req-2", outcome="error", error="boom")

    messages = [args[0] for args, _ in logger.info_calls]
    assert any("step=request.received" in message for message in messages)
    assert any("step=binding.dispatch.start" in message for message in messages)
    stored = tracer.get("req-2")
    assert stored is not None
    assert stored["events"][0]["details"]["result"] == "<dict keys=['a']>"


def test_request_flow_helpers_bind_tracer_to_app_context(monkeypatch):
    ctx = _ctx(
        logger=None,
        config=SimpleNamespace(get=lambda key, default=None: default),
    )
    monkeypatch.setattr(flow_mod, "app_ctx", lambda: ctx)

    flow_mod.start_request_flow("req-3", "ping", message_type="ping")
    flow_mod.trace_request_step("req-3", "request.ping", user="guest")
    summary = flow_mod.finish_request_flow("req-3", outcome="ok")

    assert ctx.request_flow_tracer is not None
    assert summary is not None
    assert summary["steps"] == ["request.ping"]
    assert flow_mod.recent_request_flows(limit=1)[0]["request_id"] == "req-3"


def test_request_flow_config_and_edge_cases(monkeypatch):
    class _BrokenConfig:
        def get(self, key, default=None):
            raise RuntimeError("broken")

    ctx = _ctx(logger=None, config=_BrokenConfig())
    monkeypatch.setattr(flow_mod, "app_ctx", lambda: ctx)
    monkeypatch.setenv("DEMOCRAI_REQUEST_FLOW_DEBUG", "weird")
    monkeypatch.setenv("DEMOCRAI_REQUEST_FLOW_BUFFER_SIZE", "bad")

    assert flow_mod._config_get("x", 7) == 7
    assert flow_mod.request_flow_level() == "off"
    assert flow_mod._buffer_size() == 200
    assert flow_mod._sanitize_value(["a", "b"]) == "<list len=2>"

    tracer = flow_mod.RequestFlowTracer(buffer_size=2)
    tracer.start("", "ping")
    tracer.step("", "ignored")
    assert tracer.finish("", outcome="ok") is None

    tracer.step("req-4", "late.step", request_kind="late", user="u1")
    summary = tracer.finish("req-4", outcome="ok")
    assert summary is not None
    assert summary["request_kind"] == "late"
    assert summary["steps"] == ["late.step"]
    assert tracer.get("missing") is None


def test_request_flow_summary_skips_logging_without_logger(monkeypatch):
    ctx = _ctx(
        logger=None,
        config=SimpleNamespace(get=lambda key, default=None: "summary" if key == "debug.request_flow.level" else default),
    )
    monkeypatch.setattr(flow_mod, "app_ctx", lambda: ctx)
    tracer = flow_mod.RequestFlowTracer(buffer_size=2)

    tracer.start("req-5", "init")
    summary = tracer.finish("req-5", outcome="ok")

    assert summary is not None
    assert summary["request_id"] == "req-5"
