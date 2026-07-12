"""proxy_manager.py — загрузка, валидация и ротация прокси.

Поддержка SOCKS4/SOCKS5/HTTP. Хранит список прокси,
отслеживает живые/мёртвые, выдаёт следующий по ротации.
Многопоточная проверка через ThreadPoolExecutor.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional
import ssl

import socks

from core.storage import load_lines, load_lines_from_url


# ── Модели ────────────────────────────────────────────────


class ProxyStatus(Enum):
    UNTESTED = "Untested"
    ALIVE = "Alive"
    DEAD = "Dead"


@dataclass
class ProxyEntry:
    protocol: str          # socks4 | socks5
    host: str
    port: int
    username: str = ""
    password: str = ""
    status: ProxyStatus = ProxyStatus.UNTESTED
    passed_server: str = ""   # host:port SMTP-сервера, на котором прокси прошла
    country: str = ""
    ping_ms: int = 0

    # --- helpers ---

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        """Полный URL для requests (поддерживает PySocks)."""
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

    @property
    def display(self) -> str:
        """Строка для GUI."""
        return f"[{self.protocol.upper():6s}]  {self.host}:{self.port}"


# ── Парсинг строки прокси ─────────────────────────────────

_PROXY_RE = re.compile(
    r"^(?:(?P<proto>https?|socks[45])://)?"       # protocol://  (опционально)
    r"(?:(?P<user>[^:@]+):(?P<pwd>[^@]+)@)?"      # user:pass@   (опционально)
    r"(?P<host>[^:]+):(?P<port>\d+)"              # host:port    (обязательно)
    r"(?::(?P<user2>[^:]+):(?P<pwd2>.+))?$",      # :user:pass   (формат host:port:user:pass)
    re.IGNORECASE,
)


def parse_proxy_line(line: str) -> ProxyEntry | None:
    """Распознаёт строку прокси в любом из поддерживаемых форматов.

    Форматы:
      protocol://host:port
      protocol://user:pass@host:port
      host:port:user:pass
      host:port

    Если протокол не указан — считается ``http``.
    Возвращает ``None`` если строка не парсится.
    """
    line = line.strip()
    if not line:
        return None

    m = _PROXY_RE.match(line)
    if not m:
        return None

    protocol = (m.group("proto") or "socks5").lower()
    was_http = False
    # Принудительно: любой протокол кроме SOCKS4/SOCKS5 → SOCKS5
    if protocol not in ("socks4", "socks5"):
        protocol = "socks5"
        if (m.group("proto") or "").lower() in ("http", "https"):
            was_http = True
    host = m.group("host")

    try:
        port = int(m.group("port"))
    except ValueError:
        return None

    username = m.group("user") or m.group("user2") or ""
    password = m.group("pwd") or m.group("pwd2") or ""

    entry = ProxyEntry(
        protocol=protocol,
        host=host,
        port=port,
        username=username,
        password=password,
    )
    if was_http:
        entry._was_http = True
    return entry


# ── Проверка одного прокси ────────────────────────────────

# TCP/SMTP тест: проверяем, может ли прокси установить TCP-соединение
# на SMTP-порт и получить приветственное сообщение (код 220).
# Это ровно тот же путь, что используется при реальной рассылке.
# Пробуем несколько серверов: если хотя бы один ответил 220 — прокси живой.
_SMTP_CHECK_TARGETS = [
    ("smtp.gmail.com", 587),
    ("smtp-mail.outlook.com", 587),
    ("smtp.mail.yahoo.com", 587),
    ("smtp.gmail.com", 465),
    ("smtp.mail.yahoo.com", 465),
    ("smtp.aol.com", 587),
    ("smtp.mail.me.com", 587),
    ("smtp.zoho.com", 587),
    ("mail.gmx.com", 587),
]
_CHECK_TIMEOUTS = [5, 10]   # эскалация: быстрый → медленный
_CHECK_RETRIES = 1       # 1 повторная попытка перед вердиктом Dead
_RETRY_PAUSE = 2         # секунд между попытками

# Динамические хосты из загруженных SMTP-аккаунтов
_USER_SMTP_TARGETS: list[tuple[str, int]] = []


def set_user_smtp_targets(accounts: list) -> None:
    """Извлекает уникальные host:port из загруженных SMTP-аккаунтов."""
    global _USER_SMTP_TARGETS
    seen: set[tuple[str, int]] = set()
    targets: list[tuple[str, int]] = []
    for acc in accounts:
        key = (acc.host, acc.port)
        if key not in seen:
            seen.add(key)
            targets.append(key)
    _USER_SMTP_TARGETS = targets


_PROXY_TYPE_MAP = {
    "socks5": socks.SOCKS5,
    "socks4": socks.SOCKS4,
}


def _smtp_tcp_test(proxy: ProxyEntry) -> bool:
    """Проверяет прокси: TCP + баннер 220 + EHLO 250.

    Пробует все серверы (встроенные + пользовательские SMTP).
    При успехе записывает прошедший сервер в ``proxy.passed_server``.
    Использует эскалацию таймаутов: 5с → 10с.
    """
    all_targets = _USER_SMTP_TARGETS + _SMTP_CHECK_TARGETS
    # Оптимизация: проверяем максимум 3 сервера, чтобы не висеть минутами на мёртвых прокси
    # Уникализируем список (порядок сохраняется: сначала юзерские, потом дефолтные)
    unique_targets = []
    for t in all_targets:
        if t not in unique_targets:
            unique_targets.append(t)
    targets_to_check = unique_targets[:3]
    
    for idx, (host, port) in enumerate(targets_to_check):
        timeout = _CHECK_TIMEOUTS[0] if idx == 0 else _CHECK_TIMEOUTS[-1]
        s = socks.socksocket()
        try:
            s.set_proxy(
                _PROXY_TYPE_MAP.get(proxy.protocol, socks.SOCKS5),
                proxy.host,
                proxy.port,
                username=proxy.username or None,
                password=proxy.password or None,
            )
            s.settimeout(timeout)
            t0 = time.time()
            s.connect((host, port))
            ping_ms = int((time.time() - t0) * 1000)
            if not getattr(proxy, "ping_ms", 0) or ping_ms < proxy.ping_ms:
                proxy.ping_ms = ping_ms

            # Если порт 465 (SMTPS), сервер ожидает TLS handshake до отправки баннера
            if port == 465:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                s = context.wrap_socket(s, server_hostname=host)

            # 1. Баннер 220
            banner = s.recv(1024)
            if banner[:3] != b"220":
                continue

            # 2. EHLO → 250
            s.sendall(b"EHLO localhost\r\n")
            ehlo_resp = s.recv(1024)
            if ehlo_resp[:3] != b"250":
                continue

            # 3. QUIT — вежливо закрываем
            s.sendall(b"QUIT\r\n")

            proxy.passed_server = f"{host}:{port}"
            return True
        except socks.ProxyConnectionError:
            # Не смогли подключиться к самому прокси — нет смысла проверять остальные серверы
            return False
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            # Если ошибка при подключении к самому прокси (а не к SMTP)
            if "proxy" in str(e).lower() or isinstance(e, TimeoutError):
                pass # TimeoutError может быть как от прокси, так и от SMTP
            continue
        except Exception:
            continue
        finally:
            try:
                s.close()
            except Exception:
                pass
    return False


def _check_single(proxy: ProxyEntry, on_geo_done=None) -> ProxyEntry:
    """Проверяет прокси TCP-соединением на SMTP-порт. Ставит статус Alive/Dead.

    При неудаче делает 1 повторную попытку через короткую паузу.
    """
    for attempt in range(_CHECK_RETRIES + 1):
        if _smtp_tcp_test(proxy):
            proxy.status = ProxyStatus.ALIVE
            
            def _fetch_geo():
                import requests
                p_url = proxy.url.replace("socks5://", "socks5h://").replace("socks4://", "socks4a://")
                proxies = {"http": p_url, "https": p_url}
                
                # Попытка 1: Через сам прокси (чтобы узнать реальный выходной IP и обойти лимиты)
                for api_url in ["http://ip-api.com/json/", "https://ipinfo.io/json"]:
                    try:
                        resp = requests.get(api_url, proxies=proxies, timeout=4)
                        if resp.status_code == 200:
                            data = resp.json()
                            proxy.country = data.get("countryCode", data.get("country", ""))
                            if proxy.country:
                                if on_geo_done: on_geo_done()
                                return
                    except Exception:
                        pass
                        
                # Попытка 2: Локально (если прокси блокирует HTTP-порты 80/443)
                for api_url in [f"http://ip-api.com/json/{proxy.host}", f"https://ipinfo.io/{proxy.host}/json"]:
                    try:
                        # Без прокси, напрямую со своего IP
                        resp = requests.get(api_url, timeout=4)
                        if resp.status_code == 200:
                            data = resp.json()
                            proxy.country = data.get("countryCode", data.get("country", ""))
                            if proxy.country:
                                if on_geo_done: on_geo_done()
                                return
                    except Exception:
                        pass

            t = threading.Thread(target=_fetch_geo, daemon=True)
            t.start()
            t.join(timeout=6.0) # Ждем 6 секунд, если не успели - ставим [?]
            
            return proxy
        if attempt < _CHECK_RETRIES:
            time.sleep(1) # Было _RETRY_PAUSE, уменьшили для скорости

    proxy.status = ProxyStatus.DEAD
    return proxy


# ── Менеджер ──────────────────────────────────────────────


class ProxyManager:
    """Загрузка, проверка, ротация прокси-листа."""

    def __init__(self) -> None:
        self._proxies: list[ProxyEntry] = []
        self._lock = threading.Lock()
        self._rotation_idx: int = 0

        self._auto_stop = threading.Event()
        self._auto_thread: threading.Thread | None = None

    # -- свойства --------------------------------------------------

    @property
    def proxies(self) -> list[ProxyEntry]:
        with self._lock:
            return list(self._proxies)

    @property
    def alive(self) -> list[ProxyEntry]:
        with self._lock:
            return [p for p in self._proxies if p.status == ProxyStatus.ALIVE]

    @property
    def count_total(self) -> int:
        with self._lock:
            return len(self._proxies)

    @property
    def count_alive(self) -> int:
        with self._lock:
            return sum(1 for p in self._proxies if p.status == ProxyStatus.ALIVE)

    @property
    def count_dead(self) -> int:
        with self._lock:
            return sum(1 for p in self._proxies if p.status == ProxyStatus.DEAD)

    # -- загрузка --------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._proxies.clear()
            self._rotation_idx = 0

    def reset_all(self) -> None:
        """Сбрасывает результаты проверок для всех прокси."""
        with self._lock:
            for p in self._proxies:
                p.status = ProxyStatus.UNTESTED
                p.passed_server = ""
                p.ping_ms = 0
                p.country = ""

    def load_from_lines(self, lines: list[str]) -> int:
        """Парсит строки и добавляет в список. Возвращает кол-во добавленных."""
        added = 0
        with self._lock:
            for line in lines:
                entry = parse_proxy_line(line)
                if entry:
                    self._proxies.append(entry)
                    added += 1
        return added

    def load_from_file(self, filepath: str) -> int:
        lines = load_lines(filepath)
        return self.load_from_lines(lines)

    def load_from_url(self, url: str) -> int:
        lines = load_lines_from_url(url)
        return self.load_from_lines(lines)

    # -- удаление --------------------------------------------------

    def remove_dead(self) -> int:
        """Удаляет мёртвые прокси. Возвращает количество удалённых."""
        with self._lock:
            before = len(self._proxies)
            self._proxies = [p for p in self._proxies if p.status != ProxyStatus.DEAD]
            self._rotation_idx = 0
            return before - len(self._proxies)

    # -- проверка --------------------------------------------------

    def check_all(
        self,
        max_workers: int = 30,
        on_progress: Callable[[int, int, ProxyEntry], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Проверяет ВСЕ прокси параллельно в отдельном потоке.

        ``on_progress(checked, total, proxy)`` вызывается после каждой проверки.
        ``on_done()`` вызывается когда всё завершено.
        Никогда не блокирует вызывающий поток.
        """

        def _worker() -> None:
            with self._lock:
                targets = list(self._proxies)
            total = len(targets)
            if total == 0:
                if on_done:
                    on_done()
                return

            checked = 0
            with ThreadPoolExecutor(max_workers=min(max_workers, total)) as pool:
                futures = {}
                for p in targets:
                    def make_cb(pr=p):
                        return lambda: on_progress(checked, total, pr) if on_progress else None
                    fut = pool.submit(_check_single, p, make_cb())
                    futures[fut] = p
                    
                for fut in as_completed(futures):
                    proxy = futures[fut]
                    try:
                        fut.result()
                    except Exception:
                        proxy.status = ProxyStatus.DEAD
                    checked += 1
                    if on_progress:
                        on_progress(checked, total, proxy)

            if on_done:
                on_done()

        threading.Thread(target=_worker, daemon=True).start()

    # -- ротация ---------------------------------------------------

    def get_next(self) -> ProxyEntry | None:
        """Round-robin по живым прокси без O(N) аллокаций памяти."""
        with self._lock:
            total = len(self._proxies)
            if not total:
                return None
            for _ in range(total):
                idx = self._rotation_idx % total
                self._rotation_idx = idx + 1
                p = self._proxies[idx]
                if p.status == ProxyStatus.ALIVE:
                    return p
            return None

    # -- авто-обновление -------------------------------------------

    def start_auto_refresh(
        self,
        url: str,
        interval_min: int,
        on_refresh: Callable[[int], None] | None = None,
    ) -> None:
        """Фоновый поток: каждые ``interval_min`` минут очищает и заново
        загружает прокси по URL.  ``on_refresh(count)`` вызывается после
        каждой успешной перезагрузки.
        """
        self.stop_auto_refresh()
        self._auto_stop.clear()

        def _loop() -> None:
            while not self._auto_stop.wait(interval_min * 60):
                try:
                    self.clear()
                    count = self.load_from_url(url)
                    if on_refresh:
                        on_refresh(count)
                except Exception:
                    pass

        self._auto_thread = threading.Thread(target=_loop, daemon=True)
        self._auto_thread.start()

    def stop_auto_refresh(self) -> None:
        self._auto_stop.set()
        if self._auto_thread and self._auto_thread.is_alive():
            self._auto_thread.join(timeout=2)
        self._auto_thread = None
