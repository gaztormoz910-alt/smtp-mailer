"""smtp_manager.py — управление SMTP-аккаунтами и соединениями.

Загрузка аккаунтов из файла, проверка логина (с поддержкой прокси
через PySocks), ротация аккаунтов round-robin, контроль лимитов.
"""

from __future__ import annotations

import smtplib
import socket
import ssl
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

import socks

from core.storage import load_lines


# ── Модели ────────────────────────────────────────────────


class SmtpStatus(Enum):
    UNTESTED = "Untested"
    ALIVE = "Alive"
    DEAD = "Dead"


@dataclass
class SmtpAccount:
    host: str
    port: int
    email: str
    password: str
    status: SmtpStatus = SmtpStatus.UNTESTED
    sent_count: int = 0
    last_error: str = ""

    @property
    def display_host(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def encryption(self) -> str:
        if self.port == 465:
            return "SSL"
        if self.port == 587:
            return "STARTTLS"
        return "PLAIN"


# ── Парсинг ───────────────────────────────────────────────


def parse_smtp_line(line: str) -> SmtpAccount | None:
    """Парсит ``host:port:email:password``.  Пароль может содержать двоеточия."""
    line = line.strip()
    if not line:
        return None
    parts = line.split(":", 3)
    if len(parts) < 4:
        return None
    host, port_str, email, password = parts
    try:
        port = int(port_str.strip())
    except ValueError:
        return None
    return SmtpAccount(
        host=host.strip(),
        port=port,
        email=email.strip(),
        password=password.strip(),
    )


# ── Прокси-сокет (PySocks) ───────────────────────────────

_PROXY_TYPE_MAP = {
    "socks5": socks.SOCKS5,
    "socks4": socks.SOCKS4,
    "http":   socks.HTTP,
}


def _make_proxy_sock(
    proxy: Any,
    dest_host: str,
    dest_port: int,
    timeout: int = 12,
) -> socket.socket:
    """Создаёт TCP-сокет, подключённый к ``dest`` через прокси."""
    s = socks.socksocket()
    s.set_proxy(
        _PROXY_TYPE_MAP.get(proxy.protocol, socks.HTTP),
        proxy.host,
        proxy.port,
        username=proxy.username or None,
        password=proxy.password or None,
    )
    s.settimeout(timeout)
    s.connect((dest_host, dest_port))
    return s


# ── Подключение к SMTP ───────────────────────────────────

_CONNECT_TIMEOUT = 30


def connect_smtp(
    account: SmtpAccount,
    proxy: Any | None = None,
    timeout: int = _CONNECT_TIMEOUT,
) -> smtplib.SMTP:
    """Устанавливает соединение → EHLO → TLS → LOGIN.

    Возвращает готовый к отправке объект ``smtplib.SMTP``.
    При любой ошибке бросает исключение.
    """
    host, port = account.host, account.port
    raw_sock = _make_proxy_sock(proxy, host, port, timeout) if proxy else None

    # ── SSL (порт 465) ────────────────────────────────
    if port == 465:
        if raw_sock:
            ctx = ssl.create_default_context()
            ssl_sock = ctx.wrap_socket(raw_sock, server_hostname=host)
            smtp = smtplib.SMTP_SSL(timeout=timeout)
            smtp.sock = ssl_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host                       # noqa: SLF001
            code, _ = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, b"Bad greeting")
        else:
            smtp = smtplib.SMTP_SSL(host, port, timeout=timeout)
        smtp.ehlo()

    # ── STARTTLS (порт 587) ───────────────────────────
    elif port == 587:
        if raw_sock:
            smtp = smtplib.SMTP(timeout=timeout)
            smtp.sock = raw_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host                       # noqa: SLF001
            code, _ = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, b"Bad greeting")
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout)
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()

    # ── Без шифрования / авто-STARTTLS (порт 25 и др.) ──
    else:
        if raw_sock:
            smtp = smtplib.SMTP(timeout=timeout)
            smtp.sock = raw_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host                       # noqa: SLF001
            code, _ = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, b"Bad greeting")
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout)
        smtp.ehlo()
        try:
            smtp.starttls()
            smtp.ehlo()
        except (smtplib.SMTPNotSupportedError, smtplib.SMTPException):
            pass  # сервер не поддерживает STARTTLS — продолжаем plaintext

    smtp.login(account.email, account.password)
    return smtp


# ── Менеджер ──────────────────────────────────────────────


class SmtpManager:
    """Загрузка, проверка, ротация SMTP-аккаунтов."""

    def __init__(self) -> None:
        self._accounts: list[SmtpAccount] = []
        self._lock = threading.Lock()
        self._rotation_idx: int = 0

    # -- свойства --------------------------------------------------

    @property
    def accounts(self) -> list[SmtpAccount]:
        with self._lock:
            return list(self._accounts)

    @property
    def count_total(self) -> int:
        with self._lock:
            return len(self._accounts)

    @property
    def count_alive(self) -> int:
        with self._lock:
            return sum(1 for a in self._accounts if a.status == SmtpStatus.ALIVE)

    @property
    def count_dead(self) -> int:
        with self._lock:
            return sum(1 for a in self._accounts if a.status == SmtpStatus.DEAD)

    # -- загрузка --------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._accounts.clear()
            self._rotation_idx = 0

    def load_from_file(self, filepath: str) -> int:
        """Загружает аккаунты из файла ``host:port:email:password``."""
        lines = load_lines(filepath)
        added = 0
        with self._lock:
            for line in lines:
                acc = parse_smtp_line(line)
                if acc:
                    self._accounts.append(acc)
                    added += 1
        return added

    # -- удаление --------------------------------------------------

    def remove_dead(self) -> int:
        with self._lock:
            before = len(self._accounts)
            self._accounts = [
                a for a in self._accounts if a.status != SmtpStatus.DEAD
            ]
            self._rotation_idx = 0
            return before - len(self._accounts)

    # -- проверка --------------------------------------------------

    def check_single(
        self,
        account: SmtpAccount,
        proxy: Any | None = None,
    ) -> bool:
        """Тест-логин одного аккаунта.  Обновляет ``status`` и ``last_error``.

        5xx → Dead (перма-бан / неверный пароль).
        4xx / сетевая ошибка → повторная попытка через 5 секунд.
        Если и вторая попытка провалилась — остаётся в ротации (Untested).
        """
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                smtp = connect_smtp(account, proxy=proxy)
                smtp.quit()
                account.status = SmtpStatus.ALIVE
                account.last_error = ""
                return True

            except smtplib.SMTPAuthenticationError as exc:
                account.status = SmtpStatus.DEAD
                msg = exc.smtp_error
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="replace")
                account.last_error = f"Auth failed: {msg}"
                return False

            except smtplib.SMTPException as exc:
                code = getattr(exc, "smtp_code", 0)
                err = str(exc)
                if code and code >= 500:
                    account.status = SmtpStatus.DEAD
                    account.last_error = f"Permanent ({code}): {err}"
                    return False
                # Временная ошибка (4xx) — попробуем ещё раз
                account.last_error = f"Temp error: {err}"
                if attempt < max_attempts - 1:
                    time.sleep(5)
                    continue
                return False

            except (OSError, socks.ProxyError) as exc:
                account.last_error = f"Connection error: {exc}"
                if attempt < max_attempts - 1:
                    time.sleep(5)
                    continue
                return False
        return False

    _HOST_MAX_CONCURRENT = 3   # макс. одновременных соединений к одному хосту

    def check_all(
        self,
        proxy_getter: Callable[[], Any] | None = None,
        max_workers: int = 10,
        on_progress: Callable[[int, int, SmtpAccount], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Проверяет все аккаунты параллельно (фоновый поток).

        ``proxy_getter`` — вызываемый объект, возвращающий прокси или None.
        Per-host throttling: не более ``_HOST_MAX_CONCURRENT`` одновременных
        соединений к одному SMTP-хосту (защита от 421 Too many connections).
        """

        def _worker() -> None:
            with self._lock:
                targets = list(self._accounts)
            total = len(targets)
            if not total:
                if on_done:
                    on_done()
                return

            # Семафоры для ограничения параллельных соединений к одному хосту
            host_semaphores: dict[str, threading.Semaphore] = defaultdict(
                lambda: threading.Semaphore(self._HOST_MAX_CONCURRENT)
            )

            checked = 0

            def _do(acc: SmtpAccount) -> SmtpAccount:
                sem = host_semaphores[acc.host]
                sem.acquire()
                try:
                    px = proxy_getter() if proxy_getter else None
                    self.check_single(acc, proxy=px)
                finally:
                    sem.release()
                return acc

            with ThreadPoolExecutor(max_workers=min(max_workers, total)) as pool:
                futures = {pool.submit(_do, a): a for a in targets}
                for fut in as_completed(futures):
                    acc = futures[fut]
                    try:
                        fut.result()
                    except Exception:
                        acc.last_error = "Unexpected error"
                    checked += 1
                    if on_progress:
                        on_progress(checked, total, acc)

            if on_done:
                on_done()

        threading.Thread(target=_worker, daemon=True).start()

    # -- ротация ---------------------------------------------------

    def get_next(self) -> SmtpAccount | None:
        """Round-robin по живым аккаунтам без O(N) аллокаций памяти."""
        with self._lock:
            total = len(self._accounts)
            if not total:
                return None
            for _ in range(total):
                idx = self._rotation_idx % total
                self._rotation_idx = idx + 1
                a = self._accounts[idx]
                if a.status == SmtpStatus.ALIVE:
                    return a
            return None
