

from __future__ import annotations

import re
import tkinter as tk


def validate_float(new_value: str) -> bool:
    if new_value == "":
        return True
    if re.fullmatch(r'\d*\.?\d*', new_value):
        return True
    return False


def validate_int(new_value: str) -> bool:
    if new_value == "":
        return True
    return new_value.isdigit()


def validate_percent(new_value: str) -> bool:
    if new_value == "":
        return True
    if not new_value.isdigit():
        return False
    val = int(new_value)
    return 0 <= val <= 100


def validate_email_char(new_value: str) -> bool:
    if new_value == "":
        return True
    return bool(re.fullmatch(r'[a-zA-Z0-9@._+\-]+', new_value))


def validate_email_list(new_value: str) -> bool:
    if new_value == "":
        return True
    return bool(re.fullmatch(r'[a-zA-Z0-9@._+\-,\s]+', new_value))


def validate_url(new_value: str) -> bool:
    if new_value == "":
        return True
    return bool(re.fullmatch(r'[a-zA-Z0-9:/._\-?&=%#+@]+', new_value))


def register_float_validation(entry) -> None:
    _register(entry, validate_float)


def register_int_validation(entry) -> None:
    _register(entry, validate_int)


def register_percent_validation(entry) -> None:
    _register(entry, validate_percent)


def register_email_validation(entry) -> None:
    _register(entry, validate_email_char)


def register_email_list_validation(entry) -> None:
    _register(entry, validate_email_list)


def register_url_validation(entry) -> None:
    _register(entry, validate_url)


def _register(entry, func) -> None:
    inner = entry._entry if hasattr(entry, '_entry') else entry
    vcmd = (inner.register(func), '%P')
    inner.configure(validate='key', validatecommand=vcmd)
