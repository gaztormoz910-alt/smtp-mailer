

from __future__ import annotations

import json
from pathlib import Path

from core.appenv import writable_base

# Рядом с .exe (в заморозке), не в _internal: пресеты создаёт пользователь.
PRESETS_DIR = writable_base() / "data" / "presets"


def save_preset(filepath: str, data: dict) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_preset(filepath: str) -> dict:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
