"""LLM configuration loader - reads llm_config.yml and provides model settings per task."""
import os
from typing import Dict, Any, Optional
from pathlib import Path
from functools import lru_cache

import yaml

from core.logging import log_info, log_warning

_CONFIG_PATH = Path(__file__).parent.parent / "llm_config.yml"

_DEFAULTS = {
    "model": "vertex_ai.gemini-2.5-flash-image",
    "temperature": 0.2,
    "max_tokens": 6096,
    "timeout": 180,
}


class LLMTaskConfig:
    """Settings for a single LLM task."""

    def __init__(self, model: str, temperature: float, max_tokens: int, timeout: int):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"LLMTaskConfig(model={self.model!r}, temp={self.temperature}, max_tokens={self.max_tokens})"


class LLMConfig:
    """Central LLM configuration loaded from llm_config.yml."""

    def __init__(self, config_path: str = None):
        self._path = Path(config_path) if config_path else _CONFIG_PATH
        self._raw: Dict[str, Any] = {}
        self._defaults: Dict[str, Any] = dict(_DEFAULTS)
        self._load()

    def _load(self):
        if not self._path.exists():
            log_warning(f"LLM config not found at {self._path}, using defaults", "llm_config")
            return

        with open(self._path, "r") as f:
            self._raw = yaml.safe_load(f) or {}

        file_defaults = self._raw.get("defaults", {})
        if file_defaults:
            self._defaults.update(file_defaults)

        log_info(f"Loaded LLM config from {self._path} ({len(self._raw) - 1} task entries)", "llm_config")

    def reload(self):
        self._raw = {}
        self._defaults = dict(_DEFAULTS)
        self._load()
        log_info("LLM config reloaded", "llm_config")

    def get(self, task_name: str) -> LLMTaskConfig:
        task_cfg = self._raw.get(task_name, {})
        return LLMTaskConfig(
            model=task_cfg.get("model", self._defaults["model"]),
            temperature=task_cfg.get("temperature", self._defaults["temperature"]),
            max_tokens=task_cfg.get("max_tokens", self._defaults["max_tokens"]),
            timeout=task_cfg.get("timeout", self._defaults["timeout"]),
        )

    def get_model(self, task_name: str) -> str:
        return self.get(task_name).model

    def get_temperature(self, task_name: str) -> float:
        return self.get(task_name).temperature

    def get_max_tokens(self, task_name: str) -> int:
        return self.get(task_name).max_tokens

    def list_tasks(self) -> list:
        return [k for k in self._raw.keys() if k != "defaults"]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._raw)


@lru_cache()
def get_llm_config() -> LLMConfig:
    return LLMConfig()
