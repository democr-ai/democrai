from __future__ import annotations

from types import SimpleNamespace

import democrai.core.application.services.translation as translation_mod


def test_translation_service_uses_default_language_in_setup_without_preferences(monkeypatch):
    preference_calls = []
    monkeypatch.setattr(
        translation_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            setup_mode=True,
            logger=SimpleNamespace(info=lambda *_a, **_k: None),
        ),
    )
    monkeypatch.setattr(
        translation_mod,
        "get_preference",
        lambda *_a, **_k: preference_calls.append("called"),
    )
    monkeypatch.setattr(
        translation_mod.TranslationService,
        "_load_core_locales",
        lambda self: self._translations.setdefault("en", {}).update({"hello": "Hello"}),
    )

    service = translation_mod.TranslationService()
    service.initialize()

    assert service._default_language == "en"
    assert service.t("hello") == "Hello"
    assert preference_calls == []
