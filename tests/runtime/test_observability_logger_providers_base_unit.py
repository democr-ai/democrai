from __future__ import annotations

import pytest

from democrai.core.infrastructure.observability.logger.providers.base import LogProvider


def test_log_provider_base_contract():
    class _Provider(LogProvider):
        pass

    with pytest.raises(TypeError):
        _Provider()

    # Execute abstract method body to cover interface default `pass` branch.
    assert LogProvider.get_handlers(object(), "demo") is None
