"""storage.py — хелперы чтения txt/csv файлов.

Общие утилиты для загрузки списков (прокси, SMTP-аккаунтов,
адресов получателей, тем, тел). Парсинг строк, игнорирование
пустых строк и комментариев (#).
"""

from __future__ import annotations

import csv
from pathlib import Path

import requests


def load_lines(filepath: str | Path) -> list[str]:
    """Читает текстовый файл, возвращает непустые строки без комментариев (#).

    Кодировка utf-8 с fallback на latin-1.  Пробелы по краям обрезаются.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def load_lines_from_url(url: str, timeout: int = 15) -> list[str]:
    """GET-запрос на URL, возвращает непустые строки без комментариев."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    lines: list[str] = []
    for raw in resp.text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_blocks(
    filepath: str | Path,
    separator: str = "===END===",
) -> list[str]:
    """Читает файл и разделяет на блоки по строке-разделителю.

    Каждый блок может быть многострочным (HTML, plain text).
    Пустые блоки игнорируются.  Используется для тел писем.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: list[str] = []
    for chunk in text.split(separator):
        cleaned = chunk.strip()
        if cleaned:
            blocks.append(cleaned)
    return blocks


def load_csv_rows(
    filepath: str | Path,
    delimiter: str = ",",
) -> list[list[str]]:
    """Читает CSV, возвращает список строк (каждая строка — список полей).

    Пропускает пустые строки и строки-комментарии (#).
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        for row in reader:
            stripped = [c.strip() for c in row]
            if stripped and stripped[0] and not stripped[0].startswith("#"):
                rows.append(stripped)
    return rows
