

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


class ProxyStatus(Enum):
    UNTESTED = "Untested"
    ALIVE = "Alive"
    DEAD = "Dead"


@dataclass
class ProxyEntry:
    protocol: str
    host: str
    port: int
    username: str = ""
    password: str = ""
    status: ProxyStatus = ProxyStatus.UNTESTED
    passed_server: str = ""
    country: str = ""
    ping_ms: int = 0
    blacklist_clean: bool | None = None
    blacklist_hits: list[str] | None = None


    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

    @property
    def score(self) -> int:
        if self.status != ProxyStatus.ALIVE:
            return 0
        s = 50
        if self.ping_ms > 0:
            if self.ping_ms < 200:
                s += 30
            elif self.ping_ms < 500:
                s += 20
            elif self.ping_ms < 1000:
                s += 10
        if self.blacklist_clean is True:
            s += 20
        elif self.blacklist_clean is False:
            s -= 40
        return max(0, min(100, s))

    @property
    def display(self) -> str:
        return f"[{self.protocol.upper():6s}]  {self.host}:{self.port}"


_PROXY_RE = re.compile(
    r"^(?:(?P<proto>https?|socks[45])://)?"
    r"(?:(?P<user>[^:@]+):(?P<pwd>[^@]+)@)?"
    r"(?P<host>[^:]+):(?P<port>\d+)"
    r"(?::(?P<user2>[^:]+):(?P<pwd2>.+))?$",
    re.IGNORECASE,
)


def parse_proxy_line(line: str) -> ProxyEntry | None:


    line = line.strip()
    if not line:
        return None

    m = _PROXY_RE.match(line)
    if not m:
        return None

    protocol = (m.group("proto") or "socks5").lower()
    was_http = False
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
_CHECK_TIMEOUTS = [5, 10]
_CHECK_RETRIES = 1
_RETRY_PAUSE = 2


import socket as _socket

_DNSBL_SERVERS = [
    "zen.spamhaus.org",
    "b.barracudacentral.org",
    "bl.spamcop.net",
    "dnsbl.sorbs.net",
    "all.s5h.net",
]


def _check_dnsbl(ip: str, timeout: float = 2.0) -> tuple[bool, list[str]]:
    # Проверка по DNSBL. Важно: НЕ трогаем глобальный socket.setdefaulttimeout —
    # он процессно-глобальный, и при параллельной проверке потоки затирали таймауты
    # друг другу (гонка), из-за чего результаты были недетерминированными. Вместо
    # этого все блок-листы опрашиваем ОДНОВРЕМЕННО в daemon-потоках с общим дедлайном:
    # это и убирает гонку, и даёт ~timeout вместо суммы по всем зонам (было ~10 c).
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return True, []
        reversed_ip = ".".join(reversed(parts))
    except Exception:
        return True, []

    hits: list[str] = []
    hits_lock = threading.Lock()
    threads: list[threading.Thread] = []

    def _q(zone: str) -> None:
        try:
            result = _socket.gethostbyname(f"{reversed_ip}.{zone}")
            if result.startswith("127."):
                with hits_lock:
                    hits.append(zone)
        except Exception:
            pass

    for dnsbl in _DNSBL_SERVERS:
        th = threading.Thread(target=_q, args=(dnsbl,), daemon=True)
        th.start()
        threads.append(th)

    deadline = time.time() + timeout
    for th in threads:
        th.join(max(0.0, deadline - time.time()))

    return len(hits) == 0, hits

_USER_SMTP_TARGETS: list[tuple[str, int]] = []


def set_user_smtp_targets(accounts: list) -> None:
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


def _smtp_tcp_test(proxy: ProxyEntry, to_override: float | None = None) -> bool:

    all_targets = _USER_SMTP_TARGETS + _SMTP_CHECK_TARGETS
    unique_targets = []
    for t in all_targets:
        if t not in unique_targets:
            unique_targets.append(t)
    targets_to_check = unique_targets[:5]

    for idx, (host, port) in enumerate(targets_to_check):
        # Таймаут можно задать из UI (ползунок); иначе — прежние значения 5/10 с.
        timeout = to_override if to_override else (_CHECK_TIMEOUTS[0] if idx == 0 else _CHECK_TIMEOUTS[-1])
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

            if port == 465:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                s = context.wrap_socket(s, server_hostname=host)

            banner = s.recv(1024)
            if banner[:3] != b"220":
                continue

            s.sendall(b"EHLO localhost\r\n")
            ehlo_resp = s.recv(1024)
            if ehlo_resp[:3] != b"250":
                continue

            s.sendall(b"QUIT\r\n")

            proxy.passed_server = f"{host}:{port}"
            return True
        except socks.ProxyConnectionError:
            return False
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            if "proxy" in str(e).lower() or isinstance(e, TimeoutError):
                pass
            continue
        except Exception:
            continue
        finally:
            try:
                s.close()
            except Exception:
                pass
    return False


def _check_single(proxy: ProxyEntry, on_geo_done=None, timeout: float | None = None) -> ProxyEntry:

    for attempt in range(_CHECK_RETRIES + 1):
        if _smtp_tcp_test(proxy, timeout):
            proxy.status = ProxyStatus.ALIVE
            
            try:
                is_clean, hits = _check_dnsbl(proxy.host)
                proxy.blacklist_clean = is_clean
                proxy.blacklist_hits = hits if hits else None
            except Exception:
                proxy.blacklist_clean = None
            
            def _fetch_geo():
                import requests
                p_url = proxy.url.replace("socks5://", "socks5h://").replace("socks4://", "socks4a://")
                proxies = {"http": p_url, "https": p_url}
                
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
                        
                for api_url in [f"http://ip-api.com/json/{proxy.host}", f"https://ipinfo.io/{proxy.host}/json"]:
                    try:
                        resp = requests.get(api_url, timeout=4)
                        if resp.status_code == 200:
                            data = resp.json()
                            proxy.country = data.get("countryCode", data.get("country", ""))
                            if proxy.country:
                                if on_geo_done: on_geo_done()
                                return
                    except Exception:
                        pass

            threading.Thread(target=_fetch_geo, daemon=True).start()
            
            return proxy
        if attempt < _CHECK_RETRIES:
            time.sleep(1)

    proxy.status = ProxyStatus.DEAD
    return proxy


class ProxyManager:

    def __init__(self) -> None:
        self._proxies: list[ProxyEntry] = []
        self._lock = threading.Lock()
        self._rotation_idx: int = 0

        self._auto_stop = threading.Event()
        self._auto_thread: threading.Thread | None = None


    @property
    def proxies(self) -> list[ProxyEntry]:
        with self._lock:
            return list(self._proxies)

    @property
    def alive(self) -> list[ProxyEntry]:
        with self._lock:
            return [p for p in self._proxies if p.status == ProxyStatus.ALIVE]

    def slice(self, offset: int, limit: int) -> list[ProxyEntry]:
        # Окно пула для постраничного показа больших списков без копирования всего
        # (срез — O(размера окна)). Полный пул остаётся в менеджере — ротация и
        # проверка идут по всему объёму.
        if offset < 0:
            offset = 0
        with self._lock:
            return self._proxies[offset:offset + limit]

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

    def counts(self) -> tuple[int, int, int]:
        # (всего, живых, мёртвых) за ОДИН проход под одним локом — вместо трёх
        # отдельных O(n)-проходов. Нужно для дешёвого показа счётчиков на больших
        # пулах (миллионы прокси): вызывающая сторона ещё и кэширует результат.
        with self._lock:
            total = len(self._proxies)
            alive = dead = 0
            for p in self._proxies:
                if p.status == ProxyStatus.ALIVE:
                    alive += 1
                elif p.status == ProxyStatus.DEAD:
                    dead += 1
            return total, alive, dead

    @property
    def count_blacklisted(self) -> int:
        with self._lock:
            return sum(1 for p in self._proxies 
                       if p.status == ProxyStatus.ALIVE and p.blacklist_clean is False)


    def clear(self) -> None:
        with self._lock:
            self._proxies.clear()
            self._rotation_idx = 0

    def reset_all(self) -> None:
        with self._lock:
            for p in self._proxies:
                p.status = ProxyStatus.UNTESTED
                p.passed_server = ""
                p.ping_ms = 0
                p.country = ""
                p.blacklist_clean = None
                p.blacklist_hits = None

    def load_from_lines(self, lines: list[str]) -> int:
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


    def remove_dead(self) -> int:
        with self._lock:
            before = len(self._proxies)
            self._proxies = [p for p in self._proxies if p.status != ProxyStatus.DEAD]
            self._rotation_idx = 0
            return before - len(self._proxies)


    def check_all(
        self,
        max_workers: int = 30,
        on_progress: Callable[[int, int, ProxyEntry], None] | None = None,
        on_done: Callable[[], None] | None = None,
        timeout: float | None = None,
    ) -> None:


        def _worker() -> None:
            with self._lock:
                targets = list(self._proxies)
            total = len(targets)
            if total == 0:
                if on_done:
                    on_done()
                return

            checked = 0
            workers = max(1, min(max_workers, total)) if max_workers else total
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {}
                for p in targets:
                    def make_cb(pr=p):
                        return lambda: on_progress(checked, total, pr) if on_progress else None
                    fut = pool.submit(_check_single, p, make_cb(), timeout)
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


    def get_next(self) -> ProxyEntry | None:
        with self._lock:
            total = len(self._proxies)
            if not total:
                return None
            for _ in range(total):
                idx = self._rotation_idx % total
                self._rotation_idx = idx + 1
                p = self._proxies[idx]
                if p.status == ProxyStatus.ALIVE and p.blacklist_clean is not False:
                    return p
            for _ in range(total):
                idx = self._rotation_idx % total
                self._rotation_idx = idx + 1
                p = self._proxies[idx]
                if p.status == ProxyStatus.ALIVE:
                    return p
            return None

    def sort_by_score(self) -> None:
        with self._lock:
            self._proxies.sort(key=lambda p: p.score, reverse=True)
            self._rotation_idx = 0


    def start_auto_refresh(
        self,
        url: str,
        interval_min: int,
        on_refresh: Callable[[int], None] | None = None,
    ) -> None:
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


def needs_check_before_send(mgr: "ProxyManager") -> bool:
    # ТЗ задачи 1 требует авто-проверку прокси перед стартом рассылки. Проверяем
    # не «всегда» (это зря гоняло бы уже верифицированный пул и тормозило старт),
    # а только когда в пуле остались непроверенные (UNTESTED) прокси: именно там
    # есть риск уйти в рассылку с неизвестным по живости прокси. Если прокси нет
    # вовсе или все уже размечены ALIVE/DEAD — повторная проверка не нужна.
    total = mgr.count_total
    if total == 0:
        return False
    untested = total - mgr.count_alive - mgr.count_dead
    return untested > 0
