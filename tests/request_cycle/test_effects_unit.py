from democrai.core.application.request_cycle.effects import (
    BaseEffect,
    ConfirmEffect,
    NavigateEffect,
    NotifyEffect,
    RefreshModulesEffect,
    RenderEffect,
    ScrollEffect,
    SetJwtEffect,
    StartPipelineEffect,
    UiMessagesEffect,
    effects_from_action_result,
)
from democrai.core.runtime.foundation.app import RequestContext


def test_effects_from_action_result_parses_explicit_effects_with_scope():
    effects = effects_from_action_result(
        {
            "effects": [
                {"type": "navigate", "path": "/home", "render": False},
                {"type": "render", "path": "/dashboard"},
                {"type": "ui_messages", "messages": [{"kind": "note"}]},
                {
                    "type": "notify",
                    "channel": "bus",
                    "payload": {"ok": True},
                    "user_id": "u1",
                    "organization_id": "org-a",
                },
                {"type": "refresh_modules"},
                {"type": "scroll", "component_id": "list"},
                {"type": "set_jwt", "token": "jwt-1"},
            ]
        },
        action_name="demo.run",
    )

    assert [type(effect) for effect in effects] == [
        NavigateEffect,
        RenderEffect,
        UiMessagesEffect,
        NotifyEffect,
        RefreshModulesEffect,
        ScrollEffect,
        SetJwtEffect,
    ]
    notify = effects[3]
    assert notify.user_id is None
    assert notify.organization_id is None
    assert effects[0].render is False


def test_effects_from_action_result_parses_legacy_payloads():
    effects = effects_from_action_result(
        {
            "navigate": "/home",
            "status": "need_confirmation",
            "ok": False,
            "error": "Missing AI dependency: onnxruntime",
            "pipeline": [{"task": "demo.task", "label": "Demo job"}],
            "notify": {
                "channel": "ws",
                "payload": {"msg": "hello"},
                "user_id": "u2",
                "organization_id": "org-b",
            },
            "refresh": True,
            "refresh_modules": True,
            "scroll_to": "bottom_anchor",
            "jwt": "jwt-2",
            "messages": [{"surfaceUpdate": {"surfaceId": "main"}}],
            "surfaceUpdate": {"surfaceId": "secondary"},
        },
        action_name="module.demo_action",
    )

    assert not any(isinstance(effect, ConfirmEffect) for effect in effects)
    assert any(isinstance(effect, StartPipelineEffect) for effect in effects)
    assert any(isinstance(effect, NotifyEffect) for effect in effects)
    assert any(isinstance(effect, RefreshModulesEffect) for effect in effects)
    assert any(isinstance(effect, ScrollEffect) for effect in effects)
    assert any(isinstance(effect, SetJwtEffect) for effect in effects)
    assert sum(isinstance(effect, UiMessagesEffect) for effect in effects) == 2

    pipeline = next(effect for effect in effects if isinstance(effect, StartPipelineEffect))
    dependency_toast = next(
        effect
        for effect in effects
        if isinstance(effect, NotifyEffect) and effect.channel == "toast"
    )
    notify = next(
        effect
        for effect in effects
        if isinstance(effect, NotifyEffect) and effect.channel == "ws"
    )

    assert pipeline.module == "module"
    assert dependency_toast.payload["variant"] == "error"
    assert dependency_toast.payload["text"] == "Missing AI dependency: onnxruntime"
    assert notify.organization_id is None


def test_effects_from_action_result_ignores_invalid_explicit_descriptors():
    raw_effect = NavigateEffect("/keep")
    effects = effects_from_action_result(
        {
            "effects": [
                raw_effect,
                None,
                "bad",
                {"type": "navigate", "path": 3},
                {"type": "render", "path": 7},
                {"type": "ui_messages", "messages": "bad"},
                {"type": "pipeline", "label": 4, "task": "ignored"},
                {"type": "confirm", "via": 9, "path": 1, "params": "bad", "render": 0},
                {"type": "notify", "channel": "ok", "payload": {}, "organization_id": 5},
                {"type": "scroll", "component_id": 8},
                {"type": "set_jwt", "token": 42},
                {"type": "unknown"},
            ]
        },
        action_name="plain_action",
    )

    assert [type(effect) for effect in effects] == [
        NavigateEffect,
        RenderEffect,
        ConfirmEffect,
        NotifyEffect,
        SetJwtEffect,
    ]
    assert effects[0] is raw_effect
    assert effects[1].path is None
    assert effects[2].via == "dialog"
    assert effects[2].path is None
    assert effects[2].params == {}
    assert effects[2].render is False
    assert effects[3].organization_id == 5
    assert effects[4].token == "42"


def test_effects_from_action_result_parses_explicit_pipeline_and_messages_variants():
    effects = effects_from_action_result(
        {
            "effects": [
                {"type": "ui_messages", "messages": [{"ok": 1}, "bad"]},
                {"type": "pipeline", "task": "demo.task", "args": "bad"},
                {"type": "pipeline", "task": "demo.task2", "label": "Run", "module": "custom"},
            ]
        },
        action_name="module.execute",
    )

    assert [type(effect) for effect in effects] == [
        UiMessagesEffect,
        StartPipelineEffect,
        StartPipelineEffect,
    ]
    assert effects[0].messages == [{"ok": 1}]
    assert effects[1].label == "Pipeline"
    assert effects[1].args == {}
    assert effects[1].module == "module"
    assert effects[2].module == "custom"


def test_effects_from_action_result_parses_legacy_variants_and_guessing():
    effects = effects_from_action_result(
        {
            "path": "/legacy",
            "op": "navigate",
            "pipeline": [
                {"task": "one", "label": "One", "args": {"a": 1}, "module": 3},
                {"task": "two"},
                {"task": None, "label": "ignored"},
                "skip",
            ],
            "notify": [
                {"channel": "ws", "payload": {"a": 1}, "organization_id": 7},
                {"channel": "redis", "payload": {"b": 2}, "organization_id": "org-z"},
                {"channel": 1, "payload": {}},
                "skip",
            ],
            "message": {"kind": "toast"},
            "windowAction": {"type": "open"},
            "messages": ["bad"],
            "scroll_to": "",
            "jwt": None,
        },
        action_name="module.action",
    )

    assert [type(effect) for effect in effects] == [
        NavigateEffect,
        StartPipelineEffect,
        StartPipelineEffect,
        NotifyEffect,
        NotifyEffect,
        UiMessagesEffect,
    ]
    assert effects[1].module is None
    assert effects[2].module == "module"
    assert effects[3].organization_id == 7
    assert effects[4].organization_id is None
    assert effects[5].messages == [
        {
            "path": "/legacy",
            "op": "navigate",
            "pipeline": [
                {"task": "one", "label": "One", "args": {"a": 1}, "module": 3},
                {"task": "two"},
                {"task": None, "label": "ignored"},
                "skip",
            ],
            "notify": [
                {"channel": "ws", "payload": {"a": 1}, "organization_id": 7},
                {"channel": "redis", "payload": {"b": 2}, "organization_id": "org-z"},
                {"channel": 1, "payload": {}},
                "skip",
            ],
            "message": {"kind": "toast"},
            "windowAction": {"type": "open"},
            "messages": ["bad"],
            "scroll_to": "",
            "jwt": None,
        }
    ]


def test_effects_from_action_result_parses_message_and_no_dot_action_name():
    effects = effects_from_action_result(
        {"message": {"kind": "toast", "text": "ok"}},
        action_name="plain_action",
    )

    assert len(effects) == 1
    assert isinstance(effects[0], UiMessagesEffect)
    assert effects[0].messages == [{"kind": "toast", "text": "ok"}]


def test_effects_from_action_result_covers_remaining_invalid_branches():
    effects = effects_from_action_result(
        {
            "effects": [
                {"type": "notify", "channel": 7, "payload": {}},
                {"type": "set_jwt", "token": None},
                {"type": "pipeline", "task": "job", "label": "Job"},
            ]
        },
        action_name="plain_action",
    )

    assert len(effects) == 1
    assert isinstance(effects[0], StartPipelineEffect)
    assert effects[0].module is None


def test_effect_context_and_base_effect_dataclasses():
    effect = BaseEffect()
    # EffectContext removed: RequestContext is now passed directly to EffectExecutor.
    # action_name and action_context are separate parameters to execute().
    ctx = RequestContext(
        request_id="req-1",
        user=1,
        role="admin",
        organization_id=1,
        access_level=7,
        channel="desktop",
        action_name="module.run",
    )

    assert effect.kind == ""  # BaseEffect has no kind; subclasses set it in __post_init__
    assert ctx.organization_id == 1
    assert ctx.action_name == "module.run"
