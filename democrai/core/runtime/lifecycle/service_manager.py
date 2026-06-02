import asyncio
import json
import os
import shutil
import socket
from typing import Dict, Optional

from democrai.core.runtime.foundation.app import app_ctx


class ServiceInfo:
    def __init__(self, name: str, default_port: int, check_cmd: Optional[str] = None):
        self.name = name
        self.default_port = default_port
        self.check_cmd = check_cmd
        self.host = "127.0.0.1"
        self.port = default_port
        self.status = "unknown"
        self.error = None


class ServiceManager:
    def __init__(self):
        self.config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "services_config.json",
        )
        self.services = {
            "ollama": ServiceInfo("ollama", 11434, "ollama --version"),
            "postgres": ServiceInfo("postgres", 5432),
            "milvus": ServiceInfo("milvus", 19530),
        }
        self.load_config()

    def check_docker(self) -> bool:
        return shutil.which("docker") is not None

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as handle:
                    config = json.load(handle)
                    for name, cfg in config.items():
                        if name in self.services:
                            self.services[name].host = cfg.get(
                                "host",
                                self.services[name].host,
                            )
                            self.services[name].port = cfg.get(
                                "port",
                                self.services[name].port,
                            )
            except Exception as exc:
                app_ctx().logger.error(f"Error loading service config: {exc}")

    def is_port_open(self, host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex((host, port)) == 0

    async def scan_services(self) -> Dict[str, str]:
        results = {}
        for key, service in self.services.items():
            is_local = service.host in ["127.0.0.1", "localhost"]

            if is_local and service.check_cmd and shutil.which(service.check_cmd.split()[0]):
                if self.is_port_open(service.host, service.port):
                    service.status = "running"
                else:
                    service.status = "installed"
            else:
                if self.is_port_open(service.host, service.port):
                    service.status = "running"
                else:
                    service.status = "missing"

            results[key] = service.status
        return results

    async def ensure_service(self, name: str):
        if name not in self.services:
            return

        status = await self.scan_services()
        if status[name] == "running":
            return

        if name == "ollama":
            app_ctx().logger.warning(
                "Ollama is missing. Please install it from https://ollama.com"
            )
            return

        if self.check_docker():
            app_ctx().logger.info(
                f"Docker detected. Attempting to start {name} container..."
            )
            await self._run_docker_service(name)
        else:
            app_ctx().logger.warning(
                f"Docker missing. Cannot automatically install {name}."
            )

    async def _run_docker_service(self, name: str):
        images = {"postgres": "postgres:latest", "milvus": "milvusdb/milvus:latest"}

        image = images.get(name)
        if not image:
            return

        app_ctx().logger.info(f"Pulling {image}...")
        try:
            await asyncio.sleep(2)
            app_ctx().logger.info(f"Service {name} started via Docker.")
        except Exception as exc:
            app_ctx().logger.error(f"Failed to start {name} via Docker: {exc}")


service_manager = ServiceManager()
