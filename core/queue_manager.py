

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Recipient:
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


def load_recipients_txt(filepath: str) -> list[Recipient]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    result: list[Recipient] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line and not line.startswith("#") and "@" in line:
                if "," in line:
                    parts = line.split(",", 1)
                    p1, p2 = parts[0].strip(), parts[1].strip()
                    if "@" in p1:
                        result.append(Recipient(email=p1, name=p2))
                    elif "@" in p2:
                        result.append(Recipient(email=p2, name=p1))
                    else:
                        result.append(Recipient(email=line))
                else:
                    result.append(Recipient(email=line))
    return result


def load_recipients_csv(filepath: str) -> list[Recipient]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    result: list[Recipient] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        first_line = fh.readline()
        fh.seek(0)
        delim = ';' if ';' in first_line else ','
        reader = csv.DictReader(fh, delimiter=delim)
        if not reader.fieldnames:
            return result

        email_col = None
        name_col = None
        for f in reader.fieldnames:
            fl = f.strip().lower()
            if "email" in fl or "e-mail" in fl:
                email_col = f
            elif "name" in fl or "имя" in fl or "ф.и.о" in fl:
                name_col = f

        if email_col is None:
            # ТЗ задачи 8: колонка email ОБЯЗАТЕЛЬНА — без неё ошибка, в том числе
            # для 2-колоночных файлов (больше не угадываем «первая колонка = email»).
            raise ValueError("CSV must have an 'email' column")
        if name_col is None and len(reader.fieldnames) == 2:
            for f in reader.fieldnames:
                if f != email_col:
                    name_col = f
                    break

        for row in reader:
            email = row.get(email_col, "").strip()
            name = row.get(name_col, "").strip() if name_col else ""
            if email and "@" in email:
                result.append(Recipient(email=email, name=name))

    return result


def load_recipients(filepath: str) -> list[Recipient]:
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        return load_recipients_csv(filepath)
    return load_recipients_txt(filepath)


def preview_recipients(recipients: list[Recipient], limit: int = 5) -> tuple[list[Recipient], int]:
    # ТЗ задачи 8: превью базы — первые `limit` строк (по умолчанию 5) и счётчик
    # остатка, а не весь список/постраничный срез.
    shown = list(recipients[:limit])
    extra = max(0, len(recipients) - len(shown))
    return shown, extra


def build_queue(
    recipients: list[Recipient],
    control_emails: list[str] | None = None,
    control_every_n: int = 0,
) -> list[Recipient]:


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
