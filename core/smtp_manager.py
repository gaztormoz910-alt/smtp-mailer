"""smtp_manager.py — управление SMTP-аккаунтами и соединениями.

Загрузка аккаунтов из файла, проверка логина (с поддержкой прокси
через PySocks), ротация аккаунтов round-robin, контроль лимитов.
"""

from __future__ import annotations

import smtplib
import socket
import ssl
import random
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
    ping_ms: int = 0

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
        _PROXY_TYPE_MAP.get(proxy.protocol, socks.SOCKS5),
        proxy.host,
        proxy.port,
        rdns=True,  # Force remote DNS resolution to prevent SOCKS 0x01 errors
        username=proxy.username or None,
        password=proxy.password or None,
    )
    s.settimeout(timeout)
    s.connect((dest_host, dest_port))
    return s


# ── Подключение к SMTP ─────────────────────────────────────────

_CONNECT_TIMEOUT = 15  # Увеличили таймаут для медленных прокси

# Кэшированный SSL-контекст (создаётся один раз, используется многократно)
_UNVERIFIED_CTX: ssl.SSLContext | None = None

def _get_ssl_ctx() -> ssl.SSLContext:
    """Ленивое создание SSL-контекста (thread-safe через GIL)."""
    global _UNVERIFIED_CTX
    if _UNVERIFIED_CTX is None:
        _UNVERIFIED_CTX = ssl._create_unverified_context()
    return _UNVERIFIED_CTX


# ── Smart EHLO ─────────────────────────────────────────

import string

def _make_smart_ehlo(sender_email: str) -> str:
    """Генерирует реалистичный EHLO на основе домена отправителя.
    
    Для freemail (gmail, gmx, etc.) использует реальные паттерны,
    которые существуют в DNS. Для кастомных доменов — генерирует
    правдоподобные поддомены.
    """
    rnd = random.SystemRandom()
    domain = sender_email.split("@")[-1] if "@" in sender_email else "localhost"
    
    rnd_str = lambda n: "".join(rnd.choice(string.ascii_lowercase + string.digits) for _ in range(n))
    
    # Реальные EHLO паттерны для freemail провайдеров
    _FREEMAIL_EHLO = {
        'gmail.com': [
            lambda: f"mail-{rnd.choice(['oi','lf','pg','qt','vs','wr','yb','ua','io','il'])}{rnd.randint(1,9)}-f{rnd.randint(100,255)}.google.com",
        ],
        'gmx.com': [lambda: f"mout.gmx.net"],
        'gmx.net': [lambda: f"mout.gmx.net"],
        'gmx.de': [lambda: f"mout.gmx.net"],
        'web.de': [lambda: f"mout.web.de"],
        'outlook.com': [
            lambda: f"{rnd.choice(['EUR','AMS','DUB','FRA','LON','PAR'])}{rnd.randint(1,9)}PEPF0000{rnd.randint(1000,9999)}.mail.protection.outlook.com",
        ],
        'hotmail.com': [
            lambda: f"{rnd.choice(['EUR','AMS','DUB'])}{rnd.randint(1,9)}PEPF0000{rnd.randint(1000,9999)}.mail.protection.outlook.com",
        ],
        'yahoo.com': [
            lambda: f"sonic{rnd.randint(100,999)}-{rnd.randint(1,99)}.consmr.mail.{rnd.choice(['bf2','ne1','gq1'])}.yahoo.com",
        ],
        'icloud.com': [
            lambda: f"st{rnd.randint(11,43)}-asmtp{rnd.randint(100,999)}.me.com",
        ],
        'zohomail.eu': [lambda: f"sender{rnd.randint(1,20)}.zoho.eu"],
        'zohomail.com': [lambda: f"sender{rnd.randint(1,20)}.zoho.com"],
    }
    
    domain_lower = domain.lower()
    if domain_lower in _FREEMAIL_EHLO:
        return rnd.choice(_FREEMAIL_EHLO[domain_lower])()
    
    # Для кастомных доменов — поддомены самого домена (правдоподобно)
    templates = [
        lambda: f"mail.{domain}",
        lambda: f"smtp.{domain}",
        lambda: f"mx.{domain}",
        lambda: f"relay.{domain}",
        lambda: f"out.{domain}",
        lambda: f"mailer.{domain}",
        lambda: f"mta.{domain}",
        lambda: f"send.{domain}",
    ]
    return rnd.choice(templates)()


# ── NOOP keep-alive ───────────────────────────────────

def smtp_keep_alive(conn: smtplib.SMTP) -> bool:
    """Проверяет что SMTP соединение ещё живое через NOOP."""
    try:
        code, _ = conn.noop()
        return code == 250
    except Exception:
        return False


def connect_smtp(
    account: SmtpAccount,
    proxy: Any | None = None,
    timeout: int = _CONNECT_TIMEOUT,
) -> smtplib.SMTP:
    """Устанавливает соединение → EHLO → TLS → LOGIN.

    Возвращает готовый к отправке объект ``smtplib.SMTP``.
    При любой ошибке бросает исключение.
    """
    fake_ehlo = _make_smart_ehlo(account.email)

    host, port = account.host, account.port
    raw_sock = _make_proxy_sock(proxy, host, port, timeout) if proxy else None

    # ── SSL (порт 465) ────────────────────────────────
    if port == 465:
        if raw_sock:
            ctx = _get_ssl_ctx()
            ssl_sock = ctx.wrap_socket(raw_sock, server_hostname=host)
            smtp = smtplib.SMTP_SSL(timeout=timeout, local_hostname=fake_ehlo)
            smtp.sock = ssl_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host                       # noqa: SLF001
            code, _ = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, b"Bad greeting")
        else:
            ctx = _get_ssl_ctx()
            smtp = smtplib.SMTP_SSL(host, port, timeout=timeout, local_hostname=fake_ehlo, context=ctx)
        smtp.ehlo()

    # ── STARTTLS (порт 587) ───────────────────────────
    elif port == 587:
        if raw_sock:
            smtp = smtplib.SMTP(timeout=timeout, local_hostname=fake_ehlo)
            smtp.sock = raw_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host                       # noqa: SLF001
            code, _ = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, b"Bad greeting")
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout, local_hostname=fake_ehlo)
        smtp.ehlo()
        ctx = _get_ssl_ctx()
        try:
            smtp.starttls(context=ctx)
            smtp.ehlo()
        except (smtplib.SMTPNotSupportedError, smtplib.SMTPException, EOFError) as e:
            # Some servers drop connection or fail starttls, we pass it up or log it
            raise smtplib.SMTPConnectError(587, f"STARTTLS failed: {e}".encode())

    # ── Без шифрования / авто-STARTTLS (порт 25 и др.) ──
    else:
        if raw_sock:
            smtp = smtplib.SMTP(timeout=timeout, local_hostname=fake_ehlo)
            smtp.sock = raw_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host                       # noqa: SLF001
            code, _ = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, b"Bad greeting")
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout, local_hostname=fake_ehlo)
        smtp.ehlo()
        try:
            ctx = _get_ssl_ctx()
            smtp.starttls(context=ctx)
            smtp.ehlo()
        except (smtplib.SMTPNotSupportedError, smtplib.SMTPException, EOFError):
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

    def reset_all(self) -> None:
        """Сбрасывает результаты проверок для всех аккаунтов."""
        with self._lock:
            for acc in self._accounts:
                acc.status = SmtpStatus.UNTESTED
                acc.last_error = ""
                acc.ping_ms = 0
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
                t0 = time.time()
                smtp = connect_smtp(account, proxy=proxy)
                smtp.quit()
                ping_ms = int((time.time() - t0) * 1000)
                if not getattr(account, "ping_ms", 0) or ping_ms < account.ping_ms:
                    account.ping_ms = ping_ms
                
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
                    time.sleep(1) # Уменьшена задержка, чтобы UI не висел долго
                    continue
                account.status = SmtpStatus.UNTESTED
                return False

            except (OSError, socks.ProxyError, socket.timeout, TimeoutError) as exc:
                account.last_error = f"Connection error: {exc}"
                if attempt < max_attempts - 1:
                    time.sleep(1) # Уменьшена задержка
                    continue
                # Важно: если ошибка сетевая (таймаут, отказ прокси), мы НЕ помечаем SMTP аккаунт как DEAD.
                # Потому что проблема может быть в самом прокси, а не в SMTP сервере/аккаунте.
                # Мёртвым (DEAD) аккаунт считается только если сервер ответил "Неверный логин" или 5xx ошибкой.
                account.status = SmtpStatus.UNTESTED
                return False

            except Exception as exc:
                account.last_error = f"Unexpected error: {exc}"
                account.status = SmtpStatus.UNTESTED
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
                    except Exception as e:
                        if isinstance(e, (OSError, socks.ProxyError, socket.timeout, TimeoutError)):
                            acc.last_error = f"Unexpected network error: {e}"
                            acc.status = SmtpStatus.UNTESTED
                        else:
                            acc.last_error = f"Unexpected error: {e}"
                            acc.status = SmtpStatus.UNTESTED
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
