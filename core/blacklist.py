# -*- coding: utf-8 -*-
"""Общая проверка по чёрным спискам (DNSBL для IP и DBL/SURBL/URIBL для доменов).

ПОЧЕМУ отдельный модуль: проверку по блэклистам используют И прокси (IP выходного узла),
И SMTP-аккаунты (IP SMTP-хоста + домен отправителя). Держим ОДНУ корректную реализацию,
чтобы не дублировать логику и не тиражировать баг разбора ответа.

Как работает DNSBL/DBL: спрашиваем у зоны A-запись для «перевёрнутый-IP.зона»
(для доменов — «домен.зона»). Ответ — адрес в 127.0.0.0/8, и НЕ всякий ответ = листинг:
  • 127.0.0.2..127.0.0.63 или 127.0.1.x  → ЛИСТИНГ (адрес/домен в списке);
  • 127.0.0.1                            → НЕ листинг (у URIBL это «запрос заблокирован»);
  • 127.255.255.x                        → НЕ листинг, а ОТКАЗ резолвера (Spamhaus так
                                            отвечает на запросы через публичные 8.8.8.8/1.1.1.1);
  • исключение при резолве               → трактуем как «эта зона не дала листинга».
Старый код проверял `result.startswith("127.")` и засчитывал 127.255.255.254 как листинг —
из-за этого на публичном резолвере ВСЕ проверяемые узлы штрафовались ни за что. Здесь чинится.

Предел без внешних зависимостей: gethostbyname не различает NXDOMAIN («не в списке») и
таймаут («не дозвонились»), поэтому «чисто» здесь — это «ни одна зона не дала листинга»,
а не доказанное отсутствие. Для сигнала «в списке» это безопасно (ложных листингов не даём).
"""
from __future__ import annotations

import socket as _socket
import threading
import time

# Живые IP-DNSBL (проверено санити-контрактом 127.0.0.2 листится / 127.0.0.1 нет; мёртвые
# cbl.abuseat.org и dnsbl.sorbs.net УБРАНЫ — они выведены из эксплуатации и отвечают NXDOMAIN).
# zen.spamhaus.org оставлен, но его ответ зависит от резолвера (см. модульный докстринг):
# 127.255.255.x от него мы уже не считаем листингом, так что вреда нет.
IP_DNSBL_ZONES = [
    # Проверено санити-контрактом на живой сети (2026-09): эти 6 отвечают корректно.
    "b.barracudacentral.org",
    "bl.spamcop.net",
    "psbl.surriel.com",
    "truncate.gbudb.net",
    "all.s5h.net",
    "bl.mailspike.net",
    # zen.spamhaus.org держим отдельно: он листит 127.0.0.2..11, но на публичных резолверах
    # отвечает отказом 127.255.255.x (мы его корректно НЕ считаем листингом). На приватном
    # резолвере он снова даёт покрытие — вреда от него нет, поэтому оставляем последним.
    "zen.spamhaus.org",
    # dnsbl.dronebl.org УБРАН: он помечает листинг адресом 127.0.0.1, а у URIBL это «запрос
    # заблокирован» — совмещать нельзя без ложных срабатываний. 6 живых зон достаточно.
]

# Доменные блок-листы: Spamhaus DBL (листинг 127.0.1.x), SURBL и URIBL (127.0.0.2..63).
DOMAIN_DBL_ZONES = [
    "dbl.spamhaus.org",
    "multi.surbl.org",
    "multi.uribl.com",
]

# Фримейл-домены: у них домен в доменных блок-листах не числится НИКОГДА — проверять его
# бессмысленно, поэтому для них доменную проверку пропускаем (возвращаем «чисто, фримейл»).
FREEMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "ymail.com", "rocketmail.com", "aol.com", "aim.com",
    "icloud.com", "me.com", "mac.com", "gmx.com", "gmx.net", "gmx.de",
    "mail.com", "email.com", "usa.com", "post.com",
    "mail.ru", "bk.ru", "inbox.ru", "list.ru", "internet.ru",
    "yandex.ru", "yandex.com", "ya.ru", "zoho.com",
    "proton.me", "protonmail.com", "pm.me", "tutanota.com", "web.de", "t-online.de",
}
# Плюс страновые Yahoo (@yahoo.co.uk, @yahoo.de, @yahoo.fr и т.д.) — по префиксу.
_FREEMAIL_PREFIXES = ("yahoo.",)


def is_freemail(domain: str) -> bool:
    d = (domain or "").strip().lower().lstrip("@")
    if d in FREEMAIL_DOMAINS:
        return True
    return any(d.startswith(p) for p in _FREEMAIL_PREFIXES)


def _is_listing(res: str | None) -> bool:
    """True, только если ответ резолвера — настоящий листинг (см. модульный докстринг)."""
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
    if b == 255:               # 127.255.255.x — отказ резолвера, НЕ листинг
        return False
    if b == 0 and c == 1:      # 127.0.1.x — листинг доменных DBL (Spamhaus DBL)
        return True
    if b == 0 and c == 0:      # 127.0.0.z: листинг для 2..63, но НЕ 127.0.0.1 (блок URIBL)
        return 2 <= d <= 63
    return False


def _resolve(name: str) -> str | None:
    # Единая точка резолва — её подменяют тесты (детерминированно, без сети).
    try:
        return _socket.gethostbyname(name)
    except Exception:
        return None


# Кэш результатов (много SMTP-аккаунтов делят один хост smtp.gmail.com → один IP; без кэша
# каждый аккаунт слал бы одни и те же DNS-запросы). TTL небольшой: репутация меняется.
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
    """Опрашиваем все зоны ОДНОВРЕМЕННО (общий дедлайн ~timeout вместо суммы), возвращаем
    список зон, давших листинг. labels_by_zone = [(полное_имя_для_резолва, имя_зоны), ...]."""
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
    """Проверка IP по IP-DNSBL. Возвращает (чисто, [зоны-листинги])."""
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
    """Проверка домена по доменным блок-листам (DBL/SURBL/URIBL). (чисто, [зоны])."""
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
    """IP SMTP-хоста для DNSBL (smtp.gmail.com → 142.x). None, если не резолвится."""
    return _resolve(host)


def sanity_check_zone(zone: str, timeout: float = 3.0) -> bool:
    """Санити-контракт зоны: 127.0.0.2 ДОЛЖЕН листиться, 127.0.0.1 — НЕТ. Живая сеть; в
    детерминированных тестах не используется (там подменяется _resolve)."""
    listed = _is_listing(_resolve(f"2.0.0.127.{zone}"))
    clean = _is_listing(_resolve(f"1.0.0.127.{zone}"))
    return listed and not clean
