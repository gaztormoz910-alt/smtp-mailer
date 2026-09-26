# -*- coding: utf-8 -*-
"""Единая точка правды о путях и версии — чтобы код одинаково работал и из
исходников, и внутри собранного PyInstaller-`.exe`.

Почему это нужно:
- В собранном onedir-приложении ресурсы (web/, assets/, VERSION) лежат во
  временной папке распаковки `sys._MEIPASS`, а НЕ рядом с исходником. Обращение
  по относительному пути от `__file__` без учёта заморозки читает не тот каталог.
- Данные, которые приложение ПИШЕТ (logs/, data/), наоборот, нельзя держать в
  `_internal` рядом с распакованными библиотеками: их сотрут при обновлении, и
  это не место для пользовательских файлов. Пишем рядом с самим `.exe`.
"""
import os
import sys
from pathlib import Path

APP_NAME = "Pinion"

# Корень исходников = родитель пакета core/ (используется, когда НЕ заморожено).
_SRC_ROOT = Path(__file__).resolve().parent.parent


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(rel: str) -> Path:
    """Путь к ресурсу, вшитому в сборку (только для ЧТЕНИЯ): web/, assets/, VERSION.
    В заморозке — от `sys._MEIPASS`, иначе — от корня исходников."""
    base = Path(getattr(sys, "_MEIPASS", _SRC_ROOT))
    return base / rel


def writable_base() -> Path:
    """Каталог, куда приложение ПИШЕТ (logs/, data/). В заморозке — папка рядом с
    `.exe` (её ставит инсталлятор в профиль пользователя, туда можно писать без
    прав администратора); иначе — корень исходников (как было в разработке)."""
    if _frozen():
        return Path(sys.executable).resolve().parent
    return _SRC_ROOT


def app_version() -> str:
    """Версия из единственного файла VERSION (вшивается в сборку через datas).
    Если файла нет (например, запуск из чистого дерева до set_version) — '0.0.0'."""
    try:
        return resource_path("VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        return "0.0.0"
