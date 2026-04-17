from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_NAME = "config.yaml"


def load_config(agent_root: Path) -> dict[str, Any]:
    path = agent_root / DEFAULT_CONFIG_NAME
    if not path.is_file():
        example = agent_root / "config.example.yaml"
        raise FileNotFoundError(
            f"Missing {path}. Copy {example.name} to {DEFAULT_CONFIG_NAME} and edit."
        )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("config must be a YAML mapping")
    return data


def project_root(cfg: dict[str, Any], agent_root: Path) -> Path:
    raw = cfg.get("project_root", "..")
    return (agent_root / raw).resolve()
