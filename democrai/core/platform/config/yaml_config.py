import os
import yaml
from typing import Any
from .base import ConfigProvider


class YamlConfigProvider(ConfigProvider):
    """YAML-based implementation of ConfigProvider."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._config: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                if loaded is None:
                    self._config = {}
                elif isinstance(loaded, dict):
                    self._config = loaded
                else:
                    raise ValueError("root YAML value must be a mapping")
            except Exception as e:
                print(f"[Config] Error loading {self.config_path}: {e}")
                self._config = {}

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        current = self._config
        for part in parts[:-1]:
            child = current.get(part)
            if not isinstance(child, dict):
                return default
            current = child
        return current.get(parts[-1], default)

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        target = self._config
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._config, f, default_flow_style=False)
        except Exception as e:
            print(f"[Config] Error saving {self.config_path}: {e}")
