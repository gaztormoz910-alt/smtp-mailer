"""validation.py — Валидация инпутов для GUI.

Жёсткая проверка: числовые поля принимают ТОЛЬКО цифры и точку,
процентные — только цифры 0-100, email — только валидный формат.
"""

from __future__ import annotations

import re
import tkinter as tk


# ── Числовая валидация (только цифры + одна точка) ────────

def validate_float(new_value: str) -> bool:
    """Разрешает только числа с плавающей точкой (например: 5.0, 0.5, 100)."""
    if new_value == "":
        return True  # разрешаем пустое поле (placeholder покажется)
    # Разрешаем: цифры, одна точка, начало с точки (.5)
    if re.fullmatch(r'\d*\.?\d*', new_value):
        return True
    return False


def validate_int(new_value: str) -> bool:
    """Разрешает только целые числа (0, 1, 50, 100)."""
    if new_value == "":
        return True
    return new_value.isdigit()


def validate_percent(new_value: str) -> bool:
    """Разрешает только 0-100."""
    if new_value == "":
        return True
    if not new_value.isdigit():
        return False
    val = int(new_value)
    return 0 <= val <= 100


def validate_email_char(new_value: str) -> bool:
    """Разрешает символы допустимые в email (буквы, цифры, @, ., _, -, +)."""
    if new_value == "":
        return True
    return bool(re.fullmatch(r'[a-zA-Z0-9@._+\-]+', new_value))


def validate_email_list(new_value: str) -> bool:
    """Разрешает список email через запятую (буквы, цифры, @, ., _, -, +, запятая, пробел)."""
    if new_value == "":
        return True
    return bool(re.fullmatch(r'[a-zA-Z0-9@._+\-,\s]+', new_value))


def validate_url(new_value: str) -> bool:
    """Разрешает символы допустимые в URL."""
    if new_value == "":
        return True
    return bool(re.fullmatch(r'[a-zA-Z0-9:/._\-?&=%#+@]+', new_value))


# ── Регистрация валидаторов на Entry ──────────────────────

def register_float_validation(entry) -> None:
    """Привязывает валидацию float к CTkEntry."""
    _register(entry, validate_float)


def register_int_validation(entry) -> None:
    """Привязывает валидацию integer к CTkEntry."""
    _register(entry, validate_int)


def register_percent_validation(entry) -> None:
    """Привязывает валидацию percent (0-100) к CTkEntry."""
    _register(entry, validate_percent)


def register_email_validation(entry) -> None:
    """Привязывает валидацию email-символов к CTkEntry."""
    _register(entry, validate_email_char)


def register_email_list_validation(entry) -> None:
    """Привязывает валидацию списка email к CTkEntry."""
    _register(entry, validate_email_list)


def register_url_validation(entry) -> None:
    """Привязывает валидацию URL к CTkEntry."""
    _register(entry, validate_url)


def _register(entry, func) -> None:
    """Внутренняя регистрация через Tkinter validatecommand."""
    # CTkEntry хранит внутренний tk.Entry через ._entry
    inner = entry._entry if hasattr(entry, '_entry') else entry
    vcmd = (inner.register(func), '%P')
    inner.configure(validate='key', validatecommand=vcmd)
