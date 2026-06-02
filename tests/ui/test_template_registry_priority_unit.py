import sys
from types import ModuleType

from democrai.sdk.decorators import ui_template
from democrai.core.runtime.foundation.registry import TemplateRegistry, template_registry


class _RegistrySnapshot:
    def __enter__(self):
        self.templates = {
            name: list(entries) for name, entries in template_registry._templates.items()
        }
        self.registration_order = template_registry._registration_order
        return self

    def __exit__(self, exc_type, exc, tb):
        template_registry._templates = {
            name: list(entries) for name, entries in self.templates.items()
        }
        template_registry._registration_order = self.registration_order


def test_template_registry_returns_highest_priority_registration():
    registry = TemplateRegistry()

    def low():
        return "low"

    def high():
        return "high"

    registry.register("full", low, priority=10)
    registry.register("full", high, priority=20)

    assert registry.get("full") is high
    registration = registry.get_registration("full")
    assert registration is not None
    assert registration.priority == 20


def test_template_registry_prefers_latest_registration_on_same_priority():
    registry = TemplateRegistry()

    def first():
        return "first"

    def second():
        return "second"

    registry.register("full", first, priority=10)
    registry.register("full", second, priority=10)

    assert registry.get("full") is second


def test_ui_template_keeps_explicit_name_for_module_overrides():
    with _RegistrySnapshot():
        module_name = "modules.demo.test_templates"
        sys.modules[module_name] = ModuleType(module_name)

        def module_full_template():
            return "module-full"

        module_full_template.__module__ = module_name
        decorated = ui_template("full", priority=50)(module_full_template)

        registration = template_registry.get_registration("full")
        assert registration is not None
        assert registration.func is decorated
        assert registration.priority == 50


def test_ui_template_auto_namespaces_when_name_is_omitted():
    with _RegistrySnapshot():
        module_name = "modules.demo.auto_templates"
        sys.modules[module_name] = ModuleType(module_name)

        def module_template():
            return "module-template"

        module_template.__module__ = module_name
        decorated = ui_template()(module_template)

        registration = template_registry.get_registration("demo.module_template")
        assert registration is not None
        assert registration.func is decorated
