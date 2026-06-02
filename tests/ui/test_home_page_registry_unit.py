from democrai.core.application.home import (
    consume_post_login_path,
    clear_post_login_path,
    remember_post_login_path,
    resolve_guest_page_path,
    resolve_home_page_path,
    resolve_post_login_redirect_path,
)
from democrai.sdk.decorators import guest_page, home_page
from democrai.core.runtime.foundation.registry import (
    GuestPageRegistry,
    HomePageRegistry,
    guest_page_registry,
    home_page_registry,
)


class _RegistrySnapshot:
    def __enter__(self):
        self.home_entries = list(home_page_registry._entries)
        self.home_registration_order = home_page_registry._registration_order
        self.guest_entries = list(guest_page_registry._entries)
        self.guest_registration_order = guest_page_registry._registration_order
        return self

    def __exit__(self, exc_type, exc, tb):
        home_page_registry._entries = list(self.home_entries)
        home_page_registry._registration_order = self.home_registration_order
        guest_page_registry._entries = list(self.guest_entries)
        guest_page_registry._registration_order = self.guest_registration_order


def test_home_page_registry_returns_highest_priority_path():
    registry = HomePageRegistry()
    registry.register("/dashboard/index", priority=0)
    registry.register("/module/index", priority=100)

    assert registry.get() == "/module/index"
    registration = registry.get_registration()
    assert registration is not None
    assert registration.priority == 100


def test_home_page_registry_prefers_latest_registration_on_same_priority():
    registry = HomePageRegistry()
    registry.register("/dashboard/index", priority=10)
    registry.register("/components/index", priority=10)

    assert registry.get() == "/components/index"


def test_home_page_decorator_registers_override_path():
    with _RegistrySnapshot():
        @home_page("/template_override_example/index", priority=200)
        def register_example_home():
            return None

        assert register_example_home() is None
        registration = home_page_registry.get_registration()
        assert registration is not None
        assert registration.path == "/template_override_example/index"
        assert registration.priority == 200


def test_resolve_home_page_path_uses_registry_winner():
    with _RegistrySnapshot():
        home_page_registry.register("/dashboard/index", priority=0)
        home_page_registry.register("/template_override_example/index", priority=100)

        assert resolve_home_page_path() == "/template_override_example/index"


def test_guest_page_registry_returns_highest_priority_path():
    registry = GuestPageRegistry()
    registry.register("/auth/login", priority=0)
    registry.register("/welcome/index", priority=100)

    assert registry.get() == "/welcome/index"


def test_guest_page_decorator_registers_override_path():
    with _RegistrySnapshot():
        @guest_page("/welcome/index", priority=200)
        def register_guest_page():
            return None

        assert register_guest_page() is None
        registration = guest_page_registry.get_registration()
        assert registration is not None
        assert registration.path == "/welcome/index"
        assert registration.priority == 200


def test_resolve_guest_page_path_uses_registry_winner():
    with _RegistrySnapshot():
        guest_page_registry.register("/auth/login", priority=0)
        guest_page_registry.register("/welcome/index", priority=100)

        assert resolve_guest_page_path() == "/welcome/index"


def test_resolve_home_and_guest_page_path_defaults_when_registry_empty():
    with _RegistrySnapshot():
        home_page_registry._entries = []
        home_page_registry._registration_order = 0
        guest_page_registry._entries = []
        guest_page_registry._registration_order = 0

        assert resolve_home_page_path() == "/auth/profile"
        assert resolve_guest_page_path() == "/auth/login"


def test_post_login_redirect_prefers_remembered_private_path():
    session = {"current_path": "/chat/index"}

    remember_post_login_path(session, "/chat/index")

    assert resolve_post_login_redirect_path(session) == "/chat/index"
    assert "post_login_path" not in session


def test_post_login_redirect_ignores_guest_page_path():
    session = {}

    remember_post_login_path(session, "/auth/login")

    assert resolve_post_login_redirect_path(session) == resolve_home_page_path()


def test_clear_post_login_path_removes_saved_target():
    session = {"post_login_path": "/chat/index"}

    clear_post_login_path(session)

    assert "post_login_path" not in session


def test_post_login_helpers_ignore_setup_guest_and_invalid_values():
    session = {}
    remember_post_login_path(session, "/system/setup")
    assert session == {}

    session = {"post_login_path": ""}
    assert consume_post_login_path(session) is None
    session = {"post_login_path": 123}
    assert consume_post_login_path(session) is None
