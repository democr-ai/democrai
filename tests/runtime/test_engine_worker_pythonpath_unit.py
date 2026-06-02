from pathlib import Path

from democrai.core.application.ai.engine.runtime.environment import application_root


def test_engine_worker_application_root_contains_democrai_package():
    root = Path(application_root())

    assert (root / "democrai").is_dir()


def test_engine_worker_application_root_uses_base_dir_parent_in_dev(monkeypatch):
    import democrai.core.application.ai.engine.runtime.environment as environment_mod

    monkeypatch.setattr(environment_mod, "is_frozen", lambda: False)
    monkeypatch.setattr(
        environment_mod,
        "get_base_dir",
        lambda: "/opt/democrai-app/democrai",
    )

    assert environment_mod.application_root() == "/opt/democrai-app"


def test_engine_worker_application_root_uses_base_dir_when_frozen(monkeypatch):
    import democrai.core.application.ai.engine.runtime.environment as environment_mod

    monkeypatch.setattr(environment_mod, "is_frozen", lambda: True)
    monkeypatch.setattr(
        environment_mod,
        "get_base_dir",
        lambda: "/opt/Democrai",
    )

    assert environment_mod.application_root() == "/opt/Democrai"
