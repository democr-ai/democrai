from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.storage.errors import MigrationError
from democrai.core.infrastructure.storage.migrations import orchestrator


class _KGStoreMock:
    def __init__(self, calls: list[str], fail: bool = False):
        self._calls = calls
        self._fail = fail

    def run_migrations(self) -> None:
        self._calls.append("kg")
        if self._fail:
            raise RuntimeError("kg failure")


def test_orchestrator_runs_in_deterministic_order(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    ctx = SimpleNamespace(kg_store=_KGStoreMock(calls))

    monkeypatch.setattr(orchestrator, "run_vector_migrations", lambda: calls.append("vector"))
    monkeypatch.setattr(orchestrator, "run_data_migrations", lambda: calls.append("data"))
    monkeypatch.setattr(orchestrator, "run_obs_migrations", lambda: calls.append("obs"))

    orchestrator.run_storage_migrations(ctx)
    assert calls == ["kg", "vector", "data", "obs"]


def test_orchestrator_wraps_exceptions(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    ctx = SimpleNamespace(kg_store=_KGStoreMock(calls))

    def _fail_vector() -> None:
        calls.append("vector")
        raise RuntimeError("vector failure")

    monkeypatch.setattr(orchestrator, "run_vector_migrations", _fail_vector)
    monkeypatch.setattr(orchestrator, "run_data_migrations", lambda: calls.append("data"))
    monkeypatch.setattr(orchestrator, "run_obs_migrations", lambda: calls.append("obs"))

    with pytest.raises(MigrationError, match="Storage migrations failed"):
        orchestrator.run_storage_migrations(ctx)

    assert calls == ["kg", "vector"]
