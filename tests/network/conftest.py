from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _mock_network_app_ctx(monkeypatch):
    """Provide a minimal app_ctx with a no-op logger for network unit tests."""
    fake_logger = SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    fake_ctx = SimpleNamespace(logger=fake_logger)

    import democrai.core.infrastructure.network.protocol.handlers as _ph
    import democrai.core.infrastructure.network.flows.streams as _sd
    import democrai.core.infrastructure.network.flows.request_launch as _rl
    import democrai.core.infrastructure.network.runtime.callbacks as _tr

    monkeypatch.setattr(_ph, "app_ctx", lambda: fake_ctx)
    monkeypatch.setattr(_sd, "app_ctx", lambda: fake_ctx)
    monkeypatch.setattr(_rl, "app_ctx", lambda: fake_ctx)
    monkeypatch.setattr(_tr, "app_ctx", lambda: fake_ctx, raising=False)
