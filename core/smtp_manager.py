

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
    # Опционально привязанный к аккаунту прокси (ProxyEntry). None → аккаунт
    # работает через общий пул прокси. ТЗ задачи 2, вариант В.
    bound_proxy: Any = None
    # Через какой прокси аккаунт проверялся в последний раз (для показа в UI):
    # "host:port" или "прямое соединение". Пусто, пока не проверялся.
    checked_via_proxy: str = ""

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


_SMTP_DELIMITERS = ['|', ';', ',', '\t']

import re as _re

def _parse_port(raw: str) -> int | None:
    
    raw = raw.strip()
    if not raw:
        return None
    m = _re.match(r'^(\d+)', raw)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_smtp_line(line: str) -> SmtpAccount | None:
    # Опциональная привязка прокси к аккаунту (ТЗ задачи 2, вариант В: общий пул —
    # дефолт, привязка — опционально). Формат: host:port:email:password|>proxy,
    # где proxy — любой формат из parse_proxy_line. Маркер «|>» редок в реальных
    # логинах и разбирается ПЕРВЫМ, до обычного парсинга полей, чтобы не
    # конфликтовать с делимитерами '|;,\t'. Нет маркера — bound_proxy=None и
    # аккаунт идёт через общий пул.
    line = line.strip()
    if not line:
        return None
    bound_proxy = None
    if "|>" in line:
        acct_part, _sep, proxy_part = line.partition("|>")
        from core.proxy_manager import parse_proxy_line
        bound_proxy = parse_proxy_line(proxy_part.strip())
        line = acct_part.strip()
    acc = _parse_account_fields(line)
    if acc is not None:
        acc.bound_proxy = bound_proxy
    return acc


def _parse_account_fields(line: str) -> SmtpAccount | None:
    line = line.strip()
    if not line:
        return None

    for delim in _SMTP_DELIMITERS:
        if delim not in line:
            continue
        parts = line.split(delim)
        if len(parts) < 3:
            continue

        if len(parts) >= 4:
            port = _parse_port(parts[1])

            if port is not None:
                host = parts[0].strip()
                email = parts[2].strip()
                password = delim.join(parts[3:]).strip()

                if host and email and password:
                    return SmtpAccount(
                        host=host, port=port,
                        email=email, password=password,
                    )

        host_port = parts[0].strip()
        email = parts[1].strip()
        password = delim.join(parts[2:]).strip()

        if ':' not in host_port:
            continue
        if '@' not in email and '@' in line:
            continue

        hp = host_port.rsplit(':', 1)
        host = hp[0].strip()
        port = _parse_port(hp[1])
        if port is None:
            continue

        if host and email and password:
            return SmtpAccount(
                host=host, port=port,
                email=email, password=password,
            )

    parts = line.split(":", 3)
    if len(parts) < 4:
        return None
    host, port_str, email, password = parts
    port = _parse_port(port_str)
    if port is None:
        return None
    return SmtpAccount(
        host=host.strip(),
        port=port,
        email=email.strip(),
        password=password.strip(),
    )


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
    s = socks.socksocket()
    s.set_proxy(
        _PROXY_TYPE_MAP.get(proxy.protocol, socks.SOCKS5),
        proxy.host,
        proxy.port,
        rdns=True,
        username=proxy.username or None,
        password=proxy.password or None,
    )
    s.settimeout(timeout)
    s.connect((dest_host, dest_port))
    return s


_CONNECT_TIMEOUT = 15

_UNVERIFIED_CTX: ssl.SSLContext | None = None

def _get_ssl_ctx() -> ssl.SSLContext:
    global _UNVERIFIED_CTX
    if _UNVERIFIED_CTX is None:
        _UNVERIFIED_CTX = ssl._create_unverified_context()
    return _UNVERIFIED_CTX


import string

def _make_smart_ehlo(sender_email: str) -> str:
    
    rnd = random.SystemRandom()
    domain = sender_email.split("@")[-1] if "@" in sender_email else "localhost"
    
    rnd_str = lambda n: "".join(rnd.choice(string.ascii_lowercase + string.digits) for _ in range(n))
    
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


def smtp_keep_alive(conn: smtplib.SMTP) -> bool:
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

    # Приоритет у привязанного к аккаунту прокси; иначе — прокси из общего пула
    # (может быть None → прямое соединение). ТЗ задачи 2, вариант В.
    bound = getattr(account, "bound_proxy", None)
    if bound is not None:
        proxy = bound

    fake_ehlo = _make_smart_ehlo(account.email)

    host, port = account.host, account.port
    raw_sock = _make_proxy_sock(proxy, host, port, timeout) if proxy else None

    if port == 465:
        if raw_sock:
            ctx = _get_ssl_ctx()
            ssl_sock = ctx.wrap_socket(raw_sock, server_hostname=host)
            smtp = smtplib.SMTP_SSL(timeout=timeout, local_hostname=fake_ehlo)
            smtp.sock = ssl_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host
            code, _ = smtp.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, b"Bad greeting")
        else:
            ctx = _get_ssl_ctx()
            smtp = smtplib.SMTP_SSL(host, port, timeout=timeout, local_hostname=fake_ehlo, context=ctx)
        smtp.ehlo()

    elif port == 587:
        if raw_sock:
            smtp = smtplib.SMTP(timeout=timeout, local_hostname=fake_ehlo)
            smtp.sock = raw_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host
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
            raise smtplib.SMTPConnectError(587, f"STARTTLS failed: {e}".encode())

    else:
        if raw_sock:
            smtp = smtplib.SMTP(timeout=timeout, local_hostname=fake_ehlo)
            smtp.sock = raw_sock
            smtp.file = smtp.sock.makefile("rb")
            smtp._host = host
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
            pass

    smtp.login(account.email, account.password)
    return smtp


class SmtpManager:

    def __init__(self) -> None:
        self._accounts: list[SmtpAccount] = []
        self._lock = threading.Lock()
        self._rotation_idx: int = 0


    @property
    def accounts(self) -> list[SmtpAccount]:
        with self._lock:
            return list(self._accounts)

    def slice(self, offset: int, limit: int) -> list[SmtpAccount]:
        # Окно списка аккаунтов для постраничного показа без копирования всего
        # (срез — O(размера окна)). Полный список остаётся в менеджере — ротация и
        # проверка идут по всему объёму.
        if offset < 0:
            offset = 0
        with self._lock:
            return self._accounts[offset:offset + limit]

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


    def counts(self) -> tuple[int, int, int]:
        # (всего, живых, мёртвых) за ОДИН проход под одним локом — вместо трёх
        # отдельных O(n)-проходов. Дёшево показывать счётчики на больших списках.
        with self._lock:
            total = len(self._accounts)
            alive = dead = 0
            for a in self._accounts:
                if a.status == SmtpStatus.ALIVE:
                    alive += 1
                elif a.status == SmtpStatus.DEAD:
                    dead += 1
            return total, alive, dead

    def clear(self) -> None:
        with self._lock:
            self._accounts.clear()

    def reset_all(self) -> None:
        with self._lock:
            for acc in self._accounts:
                acc.status = SmtpStatus.UNTESTED
                acc.last_error = ""
                acc.ping_ms = 0
                acc.checked_via_proxy = ""
            self._rotation_idx = 0

    def load_from_file(self, filepath: str) -> int:
        lines = load_lines(filepath)
        added = 0
        with self._lock:
            for line in lines:
                acc = parse_smtp_line(line)
                if acc:
                    self._accounts.append(acc)
                    added += 1
        return added


    def remove_dead(self) -> int:
        with self._lock:
            before = len(self._accounts)
            self._accounts = [
                a for a in self._accounts if a.status != SmtpStatus.DEAD
            ]
            self._rotation_idx = 0
            return before - len(self._accounts)

    def remove_untested(self) -> int:
        # Удаляет НЕПРОВЕРЕННЫЕ аккаунты (status UNTESTED) — по просьбе владельца отдельной
        # кнопкой, чтобы не путать с «Убрать мёртвые» (та трогает только DEAD). Живых/мёртвых
        # не касается.
        with self._lock:
            before = len(self._accounts)
            self._accounts = [
                a for a in self._accounts if a.status != SmtpStatus.UNTESTED
            ]
            self._rotation_idx = 0
            return before - len(self._accounts)


    def check_single(
        self,
        account: SmtpAccount,
        proxy: Any | None = None,
        timeout: int | None = None,
    ) -> bool:


        max_attempts = 2
        conn_timeout = int(timeout) if timeout else _CONNECT_TIMEOUT
        for attempt in range(max_attempts):
            try:
                # Фиксируем, через какой прокси идёт проверка (для показа в UI). Приоритет —
                # привязанный к аккаунту прокси (как в connect_smtp), иначе прокси из пула,
                # иначе прямое соединение. Пишем на каждой попытке — остаётся последний.
                _eff_proxy = getattr(account, "bound_proxy", None) or proxy
                account.checked_via_proxy = (
                    f"{_eff_proxy.host}:{_eff_proxy.port}" if _eff_proxy else "прямое соединение"
                )
                t0 = time.time()
                smtp = connect_smtp(account, proxy=proxy, timeout=conn_timeout)
                smtp.quit()
                ping_ms = int((time.time() - t0) * 1000)
                if not getattr(account, "ping_ms", 0) or ping_ms < account.ping_ms:
                    account.ping_ms = ping_ms
                
                account.status = SmtpStatus.ALIVE
                account.last_error = ""
                return True

            except smtplib.SMTPAuthenticationError as exc:
                # ВАЖНО (см. гигиену доставляемости): ложный «мёртвый» — это навсегда
                # потерянный живой аккаунт. «Мёртвый» ставим ТОЛЬКО когда сервер доказал,
                # что проблема в самом аккаунте (заблокирован/отключён). Отказ по
                # репутации/политике/троттлингу (Office365 5.7.3 «authentication
                # unsuccessful», Gmail 5.7.9 «log in with your web browser», отключён
                # basic-auth, «too many/rate») — это про НАШ выходной IP, а не про пароль;
                # такой отказ через один прокси не доказывает ничего → «не пров.»
                # (повторяемо через другой прокси). Асимметрия: ложный «не пров.» стоит
                # одной перепроверки, ложный «мёртвый» — потерянного аккаунта.
                msg = exc.smtp_error
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="replace")
                msg_lower = msg.lower()

                if any(w in msg_lower for w in ("locked", "disabled", "suspended",
                                                  "deactivated", "compromised", "terminated")):
                    account.status = SmtpStatus.DEAD
                    account.last_error = f"🔒 Аккаунт заблокирован: {msg}"
                    return False

                # Всё прочее на этапе логина — неоднозначно (обычно про IP/политику),
                # НЕ хороним: помечаем «не пров.» с понятной причиной, разрешаем повтор.
                if "web browser" in msg_lower or "5.7.9" in msg_lower:
                    account.last_error = f"🛡️ Провайдер требует вход через браузер/пароль приложения (не пароль): {msg}"
                elif "authentication unsuccessful" in msg_lower or "5.7.3" in msg_lower:
                    account.last_error = f"🛡️ Отказ по репутации/политике IP (не пароль): {msg}"
                elif "basic auth" in msg_lower or "disabled for" in msg_lower:
                    account.last_error = f"🛡️ Basic-auth отключён провайдером: {msg}"
                elif any(w in msg_lower for w in ("too many", "rate", "throttl")):
                    account.last_error = f"⏱️ Троттлинг — повтор через другой прокси: {msg}"
                else:
                    account.last_error = f"⚠️ Неоднозначный отказ логина (перепроверьте с чистого прокси): {msg}"
                account.status = SmtpStatus.UNTESTED
                return False

            except smtplib.SMTPConnectError as exc:
                code = getattr(exc, "smtp_code", 0)
                err = str(exc)
                err_lower = err.lower()
                
                if "starttls" in err_lower or "tls" in err_lower:
                    account.last_error = f"🔐 TLS Failure: {err}"
                    if attempt < max_attempts - 1:
                        time.sleep(1)
                        continue
                    account.status = SmtpStatus.UNTESTED
                    return False
                
                account.last_error = f"Connect error ({code}): {err}"
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                account.status = SmtpStatus.UNTESTED
                return False

            except smtplib.SMTPException as exc:
                code = getattr(exc, "smtp_code", 0)
                err = str(exc)
                err_lower = err.lower()
                
                if code and code >= 500:
                    # 5xx на connect/EHLO/relay — это про НАШ выходной IP/репутацию, а не
                    # про пароль аккаунта. Не хороним аккаунт: «не пров.» (повтор с другого
                    # прокси). Приговор аккаунту даёт только явная блокировка на логине выше.
                    if any(w in err_lower for w in ("blocked", "banned", "blacklisted",
                                                      "denied", "rejected")):
                        account.last_error = f"🛡️ IP заблокирован сервером ({code}) — не пароль: {err}"
                    elif any(w in err_lower for w in ("relay", "not allowed")):
                        account.last_error = f"⛔ Relay запрещён с нашего IP ({code}): {err}"
                    else:
                        account.last_error = f"5xx на подключении ({code}) — вероятно репутация IP: {err}"
                    account.status = SmtpStatus.UNTESTED
                    return False

                if any(w in err_lower for w in ("too many", "rate", "throttl")):
                    account.last_error = f"⏱️ Rate Limited: {err}"
                elif "try again" in err_lower or "temporary" in err_lower:
                    account.last_error = f"⏳ Temp error (retry): {err}"
                else:
                    account.last_error = f"Temp error: {err}"
                    
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                account.status = SmtpStatus.UNTESTED
                return False

            except (OSError, socks.ProxyError, socket.timeout, TimeoutError) as exc:
                err_str = str(exc).lower()
                
                if isinstance(exc, socks.ProxyError) or "proxy" in err_str:
                    account.last_error = f"🌐 Proxy error: {exc}"
                elif isinstance(exc, (socket.timeout, TimeoutError)) or "timed out" in err_str:
                    account.last_error = f"⏰ Timeout: {exc}"
                elif "connection refused" in err_str:
                    account.last_error = f"🚫 Connection refused: {exc}"
                elif "ttl expired" in err_str or "unreachable" in err_str:
                    account.last_error = f"🌐 Network unreachable: {exc}"
                elif "unexpectedly closed" in err_str or "eof" in err_str:
                    account.last_error = f"💔 Connection dropped: {exc}"
                else:
                    account.last_error = f"Connection error: {exc}"
                    
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                account.status = SmtpStatus.UNTESTED
                return False

            except Exception as exc:
                account.last_error = f"Unexpected error: {exc}"
                account.status = SmtpStatus.UNTESTED
                return False
        return False

    _HOST_MAX_CONCURRENT = 12

    def check_all(
        self,
        proxy_getter: Callable[[], Any] | None = None,
        max_workers: int = 30,
        on_progress: Callable[[int, int, SmtpAccount], None] | None = None,
        on_done: Callable[[], None] | None = None,
        timeout: int | None = None,
        soft_retries: int = 0,
        only_untested: bool = False,
    ) -> None:


        def _worker() -> None:
            with self._lock:
                # only_untested=True → перепроверяем ТОЛЬКО непроверенные (кнопка
                # «Перепроверить не пров.»): живых/мёртвых не трогаем.
                targets = [a for a in self._accounts
                           if not only_untested or a.status == SmtpStatus.UNTESTED]
            total = len(targets)
            if not total:
                if on_done:
                    on_done()
                return

            host_semaphores: dict[str, threading.Semaphore] = defaultdict(
                lambda: threading.Semaphore(self._HOST_MAX_CONCURRENT)
            )

            checked = 0

            def _do(acc: SmtpAccount) -> SmtpAccount:
                sem = host_semaphores[acc.host]
                sem.acquire()
                try:
                    # Мягкий отказ (UNTESTED — репутация/политика/троттлинг/таймаут)
                    # повторяем ЧЕРЕЗ ДРУГОЙ прокси: тот же выход вернёт тот же ответ.
                    # Останавливаемся на успехе (ALIVE) или доказанной смерти (DEAD).
                    attempts = 1 + max(0, soft_retries) if proxy_getter else 1
                    for _ in range(attempts):
                        px = proxy_getter() if proxy_getter else None
                        ok = self.check_single(acc, proxy=px, timeout=timeout)
                        if ok or acc.status == SmtpStatus.DEAD:
                            break
                finally:
                    sem.release()
                return acc

            workers = max(1, min(max_workers, total)) if max_workers else total
            with ThreadPoolExecutor(max_workers=workers) as pool:
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


    def get_next(self) -> SmtpAccount | None:
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
