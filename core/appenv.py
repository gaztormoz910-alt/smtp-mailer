# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

APP_NAME = "Pinion"

_SRC_ROOT = Path(__file__).resolve().parent.parent


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", _SRC_ROOT))
    return base / rel


def writable_base() -> Path:
    if _frozen():
        return Path(sys.executable).resolve().parent
    return _SRC_ROOT


def app_version() -> str:
    try:
        return resource_path("VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        return "0.0.0"
