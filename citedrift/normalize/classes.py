"""source_class from config/source_classes.json. Never infer."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "config" / "source_classes.json"


def load_source_classes(path: Path = DEFAULT_PATH) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in data.items()}


def source_class(domain: str, mapping: dict[str, str] | None = None) -> str:
    mapping = mapping if mapping is not None else load_source_classes()
    return mapping.get(domain.lower(), "unclassified")
