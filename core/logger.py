

from __future__ import annotations

import csv
import io
import json
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import queue

from core.appenv import writable_base

# Пишем рядом с .exe (в заморозке), а не в _internal: это пользовательские логи.
LOGS_DIR = writable_base() / "logs"


class JsonLogger:

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
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()

    def _writer_loop(self) -> None:
        while not self._stop_event.is_set():
            self._flush_queue(timeout=1.0)
            
    def _flush_queue(self, timeout: float = 1.0) -> None:
        entries_by_file = {}
        try:
            item = self._queue.get(timeout=timeout)
            path, line = item
            entries_by_file.setdefault(path, []).append(line)
            self._queue.task_done()
            
            while True:
                try:
                    item = self._queue.get_nowait()
                    path, line = item
                    entries_by_file.setdefault(path, []).append(line)
                    self._queue.task_done()
                except queue.Empty:
                    break
                    
            for path, lines in entries_by_file.items():
                try:
                    with path.open("a", encoding="utf-8") as fh:
                        fh.write("\n".join(lines) + "\n")
                except Exception:
                    pass
        except queue.Empty:
            pass


    def _log_path(self) -> Path:
        return LOGS_DIR / f"{date.today().isoformat()}.jsonl"

    def _send_log_path(self) -> Path:
        # ТЗ задачи 6: полный лог рассылки по дням — logs/YYYY-MM-DD.json.
        # Содержимое — JSON Lines (одна запись на строку): безопасно для дозаписи
        # из фонового потока в отличие от растущего JSON-массива.
        return LOGS_DIR / f"{date.today().isoformat()}.json"

    def _test_log_path(self) -> Path:
        # ТЗ задачи 7: тестовые отправки — в отдельный файл test-log.json, чтобы
        # не мешать их с боевым логом рассылки и статистикой кампании.
        return LOGS_DIR / "test-log.json"

    def log(self, category: str, message: str, **extra: Any) -> None:
        entry: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "cat": category,
            "msg": message,
        }
        entry.update(extra)
        line = json.dumps(entry, ensure_ascii=False)
        self._queue.put((self._log_path(), line))


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

        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "recipient": recipient,
            "smtp_used": smtp_used,
            "proxy_used": proxy_used,
            "subject": subject,
            "status": status,
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
        self._queue.put((self._send_log_path(), line))


    def log_test(
        self,
        recipient: str,
        smtp_used: str,
        proxy_used: str,
        subject: str,
        status: str,
        error_text: str = "",
        elapsed: float = 0.0,
    ) -> None:
        # Тестовая отправка (кнопка ТЕСТ): отдельный файл, НЕ влияет на статистику
        # и на боевой лог рассылки.
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "recipient": recipient,
            "smtp_used": smtp_used,
            "proxy_used": proxy_used,
            "subject": subject,
            "status": status,
            "test": True,
        }
        if elapsed:
            entry["elapsed"] = elapsed
        if error_text:
            entry["error_text"] = error_text

        line = json.dumps(entry, ensure_ascii=False)
        self._queue.put((self._test_log_path(), line))


    @staticmethod
    def list_send_logs() -> list[Path]:
        if not LOGS_DIR.exists():
            return []
        return sorted(LOGS_DIR.glob("*.json"), reverse=True)

    @staticmethod
    def export_json(src: Path, dst: Path) -> int:
        # src хранится как JSON Lines (одна запись на строку). Экспорт собирает их
        # в валидный JSON-массив, чтобы итоговый .json читался строгим парсером.
        records: list = []
        with src.open("r", encoding="utf-8") as fin:
            for raw in fin:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        dst.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(records)

    @staticmethod
    def export_csv(src: Path, dst: Path) -> int:
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
