from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

from democrai.core.runtime.lifecycle import service_manager as service_manager_mod
from democrai.core.runtime.foundation.app import app_ctx


class _LoggerCapture:
    def __init__(self):
        self.errors = []
        self.infos = []
        self.warnings = []

    def error(self, message, *args, **kwargs):
        self.errors.append(message)

    def info(self, message, *args, **kwargs):
        self.infos.append(message)

    def warning(self, message, *args, **kwargs):
        self.warnings.append(message)


def test_service_manager_config_scan_and_ensure(monkeypatch, tmp_path):
    logger = _LoggerCapture()
    app_ctx().logger = logger
    original_load_config = service_manager_mod.ServiceManager.load_config
    monkeypatch.setattr(service_manager_mod.ServiceManager, "load_config", lambda self: None)

    manager = service_manager_mod.ServiceManager()
    manager.config_path = str(tmp_path / "services.json")
    Path(manager.config_path).write_text(
        json.dumps({"ollama": {"host": "10.0.0.2", "port": 9999}}),
        encoding="utf-8",
    )
    service_manager_mod.ServiceManager.load_config(manager)
    assert manager.services["ollama"].host == "127.0.0.1"

    # Run real load_config on a fresh manager.
    monkeypatch.setattr(service_manager_mod.ServiceManager, "load_config", original_load_config)
    manager = service_manager_mod.ServiceManager()
    manager.config_path = str(tmp_path / "services.json")
    manager.load_config()
    assert manager.services["ollama"].host == "10.0.0.2"
    assert manager.services["ollama"].port == 9999

    monkeypatch.setattr(service_manager_mod.shutil, "which", lambda cmd: "/usr/bin/docker" if cmd == "docker" else "/usr/bin/ollama")
    monkeypatch.setattr(
        manager,
        "is_port_open",
        lambda host, port: (host, port) in {("10.0.0.2", 9999), ("127.0.0.1", 5432)},
    )
    statuses = asyncio.run(manager.scan_services())
    assert statuses["ollama"] == "running"
    assert statuses["postgres"] == "running"
    assert statuses["milvus"] == "missing"

    monkeypatch.setattr(manager, "scan_services", lambda: asyncio.sleep(0, result={"postgres": "missing", "ollama": "missing", "milvus": "missing"}))
    docker_runs = []
    monkeypatch.setattr(manager, "_run_docker_service", lambda name: asyncio.sleep(0, result=docker_runs.append(name)))
    asyncio.run(manager.ensure_service("postgres"))
    assert docker_runs == ["postgres"]
    assert "Attempting to start postgres" in logger.infos[-1]

    asyncio.run(manager.ensure_service("ollama"))
    assert "Please install it" in logger.warnings[-1]

    monkeypatch.setattr(manager, "check_docker", lambda: False)
    asyncio.run(manager.ensure_service("milvus"))
    assert "Docker missing" in logger.warnings[-1]
    asyncio.run(manager.ensure_service("unknown"))


def test_service_manager_docker_run_and_load_config_error(monkeypatch, tmp_path):
    logger = _LoggerCapture()
    app_ctx().logger = logger
    original_load_config = service_manager_mod.ServiceManager.load_config
    monkeypatch.setattr(service_manager_mod.ServiceManager, "load_config", lambda self: None)
    manager = service_manager_mod.ServiceManager()

    async def _fast_sleep(seconds):
        return None

    monkeypatch.setattr(service_manager_mod.asyncio, "sleep", _fast_sleep)
    asyncio.run(manager._run_docker_service("postgres"))
    assert "Pulling postgres:latest" in logger.infos[0]
    assert "Service postgres started via Docker." in logger.infos[1]

    monkeypatch.setattr(
        service_manager_mod.asyncio,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(RuntimeError("docker boom")),
    )
    asyncio.run(manager._run_docker_service("milvus"))
    assert "Failed to start milvus via Docker: docker boom" in logger.errors[-1]
    asyncio.run(manager._run_docker_service("unknown"))

    manager.config_path = str(tmp_path / "broken.json")
    Path(manager.config_path).write_text("{broken", encoding="utf-8")
    manager.load_config = original_load_config.__get__(manager, service_manager_mod.ServiceManager)
    manager.load_config()
    assert "Error loading service config" in logger.errors[-1]
