# -*- coding: utf-8 -*-
from __future__ import annotations

import socket as _socket
import threading
import time

IP_DNSBL_ZONES = [
    "b.barracudacentral.org",
    "bl.spamcop.net",
    "psbl.surriel.com",
    "truncate.gbudb.net",
    "all.s5h.net",
    "bl.mailspike.net",
    "zen.spamhaus.org",
]

DOMAIN_DBL_ZONES = [
    "dbl.spamhaus.org",
    "multi.surbl.org",
    "multi.uribl.com",
]

FREEMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "ymail.com", "rocketmail.com", "aol.com", "aim.com",
    "icloud.com", "me.com", "mac.com", "gmx.com", "gmx.net", "gmx.de",
    "mail.com", "email.com", "usa.com", "post.com",
    "mail.ru", "bk.ru", "inbox.ru", "list.ru", "internet.ru",
    "yandex.ru", "yandex.com", "ya.ru", "zoho.com",
    "proton.me", "protonmail.com", "pm.me", "tutanota.com", "web.de", "t-online.de",
}
_FREEMAIL_PREFIXES = ("yahoo.",)


def is_freemail(domain: str) -> bool:
    d = (domain or "").strip().lower().lstrip("@")
    if d in FREEMAIL_DOMAINS:
        return True
    return any(d.startswith(p) for p in _FREEMAIL_PREFIXES)


def _is_listing(res: str | None) -> bool:
    if not res or not res.startswith("127."):
        return False
    parts = res.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b, c, d = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    except ValueError:
        return False
    if a != 127:
        return False
    if b == 255:
        return False
    if b == 0 and c == 1:
        return True
    if b == 0 and c == 0:
        return 2 <= d <= 63
    return False


def _resolve(name: str) -> str | None:
    try:
        return _socket.gethostbyname(name)
    except Exception:
        return None


_CACHE: dict[str, tuple[float, tuple[bool, list[str]]]] = {}
_CACHE_TTL = 600.0
_CACHE_LOCK = threading.Lock()


def _cache_get(key: str):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and (time.time() - item[0]) < _CACHE_TTL:
            return item[1]
    return None


def _cache_put(key: str, value: tuple[bool, list[str]]) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)


def _query_zones(labels_by_zone: list[tuple[str, str]], timeout: float) -> list[str]:
    hits: list[str] = []
    lock = threading.Lock()
    threads: list[threading.Thread] = []

    def _q(fqdn: str, zone: str) -> None:
        if _is_listing(_resolve(fqdn)):
            with lock:
                hits.append(zone)

    for fqdn, zone in labels_by_zone:
        th = threading.Thread(target=_q, args=(fqdn, zone), daemon=True)
        th.start()
        threads.append(th)
    deadline = time.time() + timeout
    for th in threads:
        th.join(max(0.0, deadline - time.time()))
    return hits


def check_ip(ip: str, timeout: float = 2.0) -> tuple[bool, list[str]]:
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return True, []
        rev = ".".join(reversed(parts))
    except Exception:
        return True, []
    ck = _cache_get("ip:" + ip)
    if ck is not None:
        return ck
    hits = _query_zones([(f"{rev}.{z}", z) for z in IP_DNSBL_ZONES], timeout)
    result = (len(hits) == 0, hits)
    _cache_put("ip:" + ip, result)
    return result


def check_domain(domain: str, timeout: float = 2.0) -> tuple[bool, list[str]]:
    d = (domain or "").strip().lower().lstrip("@")
    if not d or "." not in d:
        return True, []
    ck = _cache_get("dom:" + d)
    if ck is not None:
        return ck
    hits = _query_zones([(f"{d}.{z}", z) for z in DOMAIN_DBL_ZONES], timeout)
    result = (len(hits) == 0, hits)
    _cache_put("dom:" + d, result)
    return result


def resolve_host_ip(host: str) -> str | None:
    return _resolve(host)


def sanity_check_zone(zone: str, timeout: float = 3.0) -> bool:
    listed = _is_listing(_resolve(f"2.0.0.127.{zone}"))
    clean = _is_listing(_resolve(f"1.0.0.127.{zone}"))
    return listed and not clean
