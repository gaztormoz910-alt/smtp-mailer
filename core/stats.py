

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class SmtpStat:
    email: str
    host: str = ""
    sent: int = 0
    errors: int = 0
    status: str = "idle"
    last_activity: float = 0.0  # epoch последнего письма/ошибки (ТЗ: «последняя активность»)


@dataclass
class ProxyStat:
    address: str
    used: int = 0
    errors: int = 0
    status: str = "idle"


class SendStats:


    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sent: int = 0
        self._errors: int = 0
        self._total: int = 0
        self._start_time: float | None = None
        self._running: bool = False
        self._paused: bool = False
        self._stopped: bool = False  # True если кампанию остановили вручную (не естественный конец)
        self._smtp: dict[str, SmtpStat] = {}
        self._proxy: dict[str, ProxyStat] = {}


    def start(self, total: int) -> None:
        with self._lock:
            self._total = total
            self._sent = 0
            self._errors = 0
            self._start_time = time.time()
            self._running = True
            self._paused = False
            self._stopped = False

    def stop(self) -> None:
        # Естественное завершение (воркер дошёл до конца очереди). Ручную остановку
        # помечает mark_stopped(); stop() НЕ сбрасывает этот флаг, чтобы «Остановлено»
        # не превратилось в «Завершено», когда воркер в конце тоже зовёт stop().
        with self._lock:
            self._running = False
            self._paused = False

    def mark_stopped(self) -> None:
        with self._lock:
            self._running = False
            self._paused = False
            self._stopped = True

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def reset(self) -> None:
        with self._lock:
            self._sent = 0
            self._errors = 0
            self._total = 0
            self._start_time = None
            self._running = False
            self._paused = False
            self._stopped = False
            self._smtp.clear()
            self._proxy.clear()


    def record_sent(self, smtp_email: str, proxy_addr: str = "") -> None:
        with self._lock:
            self._sent += 1
            s = self._ensure_smtp(smtp_email)
            s.sent += 1
            s.status = "active"
            s.last_activity = time.time()
            if proxy_addr:
                p = self._ensure_proxy(proxy_addr)
                p.used += 1
                p.status = "active"

    def record_error(self, smtp_email: str, proxy_addr: str = "",
                     smtp_dead: bool = False) -> None:
        with self._lock:
            self._errors += 1
            s = self._ensure_smtp(smtp_email)
            s.errors += 1
            s.last_activity = time.time()
            if smtp_dead:
                s.status = "dead"
            if proxy_addr:
                p = self._ensure_proxy(proxy_addr)
                p.errors += 1


    @property
    def snapshot(self) -> dict:
        with self._lock:
            elapsed = (time.time() - self._start_time) if self._start_time else 0
            elapsed_min = elapsed / 60 if elapsed > 0 else 0
            speed = self._sent / elapsed_min if elapsed_min > 0.1 else 0.0
            remaining = max(0, self._total - self._sent - self._errors)
            eta_min = remaining / speed if speed > 0 else 0.0

            if self._running:
                if self._paused:
                    status_text = "На паузе"
                else:
                    pct = (self._sent / self._total * 100) if self._total else 0
                    status_text = f"Идёт рассылка: {self._sent} / {self._total} ({pct:.1f}%)"
            elif self._stopped:
                status_text = "Остановлено"
            elif self._sent > 0:
                status_text = "Завершено"
            else:
                status_text = "Ожидание"

            started_at = (
                time.strftime("%H:%M:%S", time.localtime(self._start_time))
                if self._start_time else "—"
            )

            def _fmt_activity(ts: float) -> str:
                return time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "—"

            return {
                "status_text": status_text,
                "sent": self._sent,
                "errors": self._errors,
                "total": self._total,
                "remaining": remaining,
                "running": self._running,
                "paused": self._paused,
                "stopped": self._stopped,
                "started_at": started_at,
                "elapsed_sec": round(elapsed, 1),
                "speed_per_min": round(speed, 1),
                "eta_min": round(eta_min, 1),
                "progress": (self._sent + self._errors) / self._total if self._total else 0.0,
                "smtp": [
                    {"email": s.email, "host": s.host,
                     "sent": s.sent, "errors": s.errors, "status": s.status,
                     "last_activity": _fmt_activity(s.last_activity)}
                    for s in self._smtp.values()
                ],
                "proxy": [
                    {"address": p.address,
                     "used": p.used, "errors": p.errors, "status": p.status}
                    for p in self._proxy.values()
                ],
            }


    def _ensure_smtp(self, email: str) -> SmtpStat:
        if email not in self._smtp:
            self._smtp[email] = SmtpStat(email=email)
        return self._smtp[email]

    def _ensure_proxy(self, addr: str) -> ProxyStat:
        if addr not in self._proxy:
            self._proxy[addr] = ProxyStat(address=addr)
        return self._proxy[addr]
