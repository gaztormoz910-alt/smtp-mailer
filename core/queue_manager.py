"""queue_manager.py — база получателей + control email inject.

Загрузка адресатов из CSV/TXT, формирование финальной очереди
с вставкой контрольных адресов каждые N писем (round-robin).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Recipient:
    """Один получатель (или контрольный адрес)."""
    email: str
    name: str = ""
    is_control: bool = False

    def to_dict(self) -> dict:
        d: dict = {"email": self.email}
        if self.name:
            d["name"] = self.name
        if self.is_control:
            d["is_control"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Recipient:
        return cls(
            email=d.get("email", ""),
            name=d.get("name", ""),
            is_control=d.get("is_control", False),
        )


# ── Загрузка ──────────────────────────────────────────────


def load_recipients_txt(filepath: str) -> list[Recipient]:
    """Загрузка из TXT: одна строка — один email."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    result: list[Recipient] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line and not line.startswith("#") and "@" in line:
                result.append(Recipient(email=line))
    return result


def load_recipients_csv(filepath: str) -> list[Recipient]:
    """Загрузка из CSV: колонка ``email`` обязательна, ``name`` опциональна."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    result: list[Recipient] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return result

        # ищем колонку email (регистронезависимо)
        email_col = None
        name_col = None
        for f in reader.fieldnames:
            fl = f.strip().lower()
            if fl == "email":
                email_col = f
            elif fl == "name":
                name_col = f

        if email_col is None:
            raise ValueError("CSV must have an 'email' column")

        for row in reader:
            email = row.get(email_col, "").strip()
            name = row.get(name_col, "").strip() if name_col else ""
            if email and "@" in email:
                result.append(Recipient(email=email, name=name))

    return result


def load_recipients(filepath: str) -> list[Recipient]:
    """Автоопределение формата по расширению."""
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        return load_recipients_csv(filepath)
    return load_recipients_txt(filepath)


# ── Формирование очереди с control inject ─────────────────


def build_queue(
    recipients: list[Recipient],
    control_emails: list[str] | None = None,
    control_every_n: int = 0,
) -> list[Recipient]:
    """Строит финальную очередь с контрольными адресами.

    Каждый ``control_every_n``-й обычный получатель дополняется
    контрольным письмом.  Контрольные адреса чередуются round-robin.

    Если ``control_every_n <= 0`` или ``control_emails`` пуст — возвращает
    исходный список без изменений.
    """
    if not control_emails or control_every_n <= 0:
        return list(recipients)

    queue: list[Recipient] = []
    ctrl_idx = 0
    regular_count = 0

    for r in recipients:
        queue.append(r)
        regular_count += 1

        if regular_count >= control_every_n:
            ctrl_email = control_emails[ctrl_idx % len(control_emails)]
            queue.append(Recipient(
                email=ctrl_email,
                name="[CONTROL]",
                is_control=True,
            ))
            ctrl_idx += 1
            regular_count = 0

    return queue
