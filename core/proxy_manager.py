"""proxy_manager.py — загрузка, валидация и ротация прокси.

Поддержка SOCKS4/SOCKS5/HTTP. Хранит список прокси,
отслеживает живые/мёртвые, выдаёт следующий по ротации.
Многопоточная проверка через ThreadPoolExecutor.
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import requests

from core.storage import load_lines, load_lines_from_url


# ── Модели ────────────────────────────────────────────────


class ProxyStatus(Enum):
    UNTESTED = "Untested"
    ALIVE = "Alive"
    DEAD = "Dead"


@dataclass
class ProxyEntry:
    protocol: str          # http | socks4 | socks5
    host: str
    port: int
    username: str = ""
    password: str = ""
    status: ProxyStatus = ProxyStatus.UNTESTED

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

    protocol = (m.group("proto") or "http").lower()
    host = m.group("host")

    try:
        port = int(m.group("port"))
    except ValueError:
        return None

    username = m.group("user") or m.group("user2") or ""
    password = m.group("pwd") or m.group("pwd2") or ""

    return ProxyEntry(
        protocol=protocol,
        host=host,
        port=port,
        username=username,
        password=password,
    )


# ── Проверка одного прокси ────────────────────────────────

_CHECK_URLS = [
    "https://api.ipify.org?format=json",
    "http://httpbin.org/ip",
]
_CHECK_TIMEOUT = 7


def _check_single(proxy: ProxyEntry) -> ProxyEntry:
    """Проверяет прокси GET-запросом через него. Ставит статус Alive/Dead."""
    proxies_dict = {"http": proxy.url, "https": proxy.url}

    for url in _CHECK_URLS:
        try:
            resp = requests.get(url, proxies=proxies_dict, timeout=_CHECK_TIMEOUT)
            if resp.status_code == 200:
                proxy.status = ProxyStatus.ALIVE
                return proxy
        except Exception:
            continue

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
                futures = {pool.submit(_check_single, p): p for p in targets}
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
