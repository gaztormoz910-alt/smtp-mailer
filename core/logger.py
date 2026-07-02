"""logger.py — JSON-lines логгер + send-лог + экспорт.

Пишет логи по дням в ``logs/`` в формате JSON-lines.
Категории: success, auth_error, spam_block, network_error, info, send.
Потокобезопасный singleton.
"""

from __future__ import annotations

import csv
import io
import json
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


class JsonLogger:
    """Singleton JSON-lines логгер — один файл на день."""

    _instance: JsonLogger | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> JsonLogger:
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    # ── internal ──────────────────────────────────────────

    def _log_path(self) -> Path:
        return LOGS_DIR / f"{date.today().isoformat()}.jsonl"

    def _send_log_path(self) -> Path:
        return LOGS_DIR / f"{date.today().isoformat()}_send.jsonl"

    def log(self, category: str, message: str, **extra: Any) -> None:
        entry: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "cat": category,
            "msg": message,
        }
        entry.update(extra)
        line = json.dumps(entry, ensure_ascii=False)
        with self._write_lock:
            with self._log_path().open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    # ── convenience shortcuts ─────────────────────────────

    def success(self, message: str, **kw: Any) -> None:
        self.log("success", message, **kw)

    def auth_error(self, message: str, **kw: Any) -> None:
        self.log("auth_error", message, **kw)

    def spam_block(self, message: str, **kw: Any) -> None:
        self.log("spam_block", message, **kw)

    def network_error(self, message: str, **kw: Any) -> None:
        self.log("network_error", message, **kw)

    def info(self, message: str, **kw: Any) -> None:
        self.log("info", message, **kw)

    def warning(self, message: str, **kw: Any) -> None:
        self.log("warning", message, **kw)

    # ── структурированный send-лог ────────────────────────

    def log_send(
        self,
        recipient: str,
        smtp_used: str,
        proxy_used: str,
        subject: str,
        status: str,
        error_text: str = "",
        control: bool = False,
        had_cc: bool = False,
        had_bcc: bool = False,
    ) -> None:
        """Записывает одну строку send-лога (JSON-lines).

        Файл: ``logs/YYYY-MM-DD_send.jsonl``.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "recipient": recipient,
            "smtp_used": smtp_used,
            "proxy_used": proxy_used,
            "subject": subject,
            "status": status,  # "sent" | "error"
        }
        if error_text:
            entry["error_text"] = error_text
        if control:
            entry["control"] = True
        if had_cc:
            entry["had_cc"] = True
        if had_bcc:
            entry["had_bcc"] = True

        line = json.dumps(entry, ensure_ascii=False)
        with self._write_lock:
            with self._send_log_path().open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    # ── экспорт ───────────────────────────────────────────

    @staticmethod
    def list_send_logs() -> list[Path]:
        """Возвращает список файлов ``*_send.jsonl`` отсортированных по дате."""
        if not LOGS_DIR.exists():
            return []
        return sorted(LOGS_DIR.glob("*_send.jsonl"), reverse=True)

    @staticmethod
    def export_json(src: Path, dst: Path) -> int:
        """Копирует send-лог как есть (JSON-lines → .json).  Возвращает кол-во записей."""
        count = 0
        with src.open("r", encoding="utf-8") as fin, \
             dst.open("w", encoding="utf-8") as fout:
            for line in fin:
                fout.write(line)
                count += 1
        return count

    @staticmethod
    def export_csv(src: Path, dst: Path) -> int:
        """Конвертирует send-лог (JSON-lines) в CSV.  Возвращает кол-во записей."""
        fields = [
            "timestamp", "recipient", "smtp_used", "proxy_used",
            "subject", "status", "error_text", "control",
            "had_cc", "had_bcc",
        ]
        count = 0
        with src.open("r", encoding="utf-8") as fin, \
             dst.open("w", encoding="utf-8", newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for raw in fin:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                    writer.writerow(row)
                    count += 1
                except json.JSONDecodeError:
                    continue
        return count
