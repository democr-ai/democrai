import asyncio

from democrai.core.application.request_cycle.engine import RequestCycleEngine
from democrai.core.runtime.foundation.app import RequestContext, app_ctx, reset_req_ctx, set_req_ctx


class _Dispatcher:
    async def dispatch(self, name, ctx, session, permissions, sdk):
        if name == "demo.fail":
            return {"type": "error", "error": "boom", "details": "broken"}
        return {"value": {"name": name, "ctx": ctx, "user": session.get("user")}}


def _run_with_request_context(coro):
    token = set_req_ctx(
        RequestContext(
            app=app_ctx(),
            request_id="req-test",
            user="fabio",
            role=None,
            organization_id=None,
            access_level=None,
            channel="test",
        )
    )
    try:
        return asyncio.run(coro)
    finally:
        reset_req_ctx(token)


def test_request_cycle_binding_action_returns_correlated_value():
    engine = RequestCycleEngine()
    session = {
        "user": {"username": "fabio", "id": 1},
        "_perm_cache_user": "fabio",
        "_perm_cache_ts": 9999999999.0,
        "_perm_cache_values": [],
    }

    response = _run_with_request_context(
        engine.handle(
            {
                "request_id": "req-1",
                "bindingAction": {
                    "bindingId": "/_bindings/actions/demo",
                    "name": "demo.load",
                    "context": {"id": 7},
                },
            },
            get_session=lambda user, role: session,
            render=lambda session: [],
            dispatcher=_Dispatcher(),
            session_service=type("SessionService", (), {})(),
        )
    )

    assert response == [
        {
            "bindingActionResult": {
                "requestId": "req-1",
                "bindingId": "/_bindings/actions/demo",
                "ok": True,
                "value": {"name": "demo.load", "ctx": {"id": 7}, "user": {"username": "fabio", "id": 1}},
            }
        }
    ]


def test_request_cycle_binding_action_returns_error_payload():
    engine = RequestCycleEngine()
    session = {
        "_perm_cache_user": "fabio",
        "_perm_cache_ts": 9999999999.0,
        "_perm_cache_values": [],
    }

    response = _run_with_request_context(
        engine.handle(
            {
                "request_id": "req-2",
                "bindingAction": {
                    "bindingId": "/_bindings/actions/demo",
                    "name": "demo.fail",
                    "context": {},
                },
            },
            get_session=lambda user, role: session,
            render=lambda session: [],
            dispatcher=_Dispatcher(),
            session_service=type("SessionService", (), {})(),
        )
    )

    assert response == [
        {
            "bindingActionResult": {
                "requestId": "req-2",
                "bindingId": "/_bindings/actions/demo",
                "ok": False,
                "error": "boom",
                "details": "broken",
            }
        }
    ]
