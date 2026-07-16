"""domain_config.py — Domain-aware профили для почтовых провайдеров.

Каждый провайдер имеет свои лимиты и рекомендации по скорости.
Профили используются движком рассылки для адаптивных задержек,
лимитов на соединение и warm-up стратегий.
"""

from __future__ import annotations

import random
from typing import Any


# ── Профили провайдеров ────────────────────────────────────

_PROFILES: dict[str, dict[str, Any]] = {
    # Gmail: строгий, но быстрый при правильных заголовках
    "gmail": {
        "delay_range": (2.0, 5.0),
        "max_per_conn": 30,
        "max_per_hour": 150,
        "warmup_start": 5,
        "domains": ["gmail.com", "googlemail.com"],
    },
    # Outlook / Hotmail / Live
    "outlook": {
        "delay_range": (1.5, 4.0),
        "max_per_conn": 40,
        "max_per_hour": 200,
        "warmup_start": 10,
        "domains": ["outlook.com", "hotmail.com", "live.com", "msn.com"],
    },
    # Yahoo: очень строгий rate limit
    "yahoo": {
        "delay_range": (3.0, 8.0),
        "max_per_conn": 20,
        "max_per_hour": 100,
        "warmup_start": 3,
        "domains": ["yahoo.com", "ymail.com", "rocketmail.com",
                     "yahoo.co.uk", "yahoo.co.jp", "yahoo.fr",
                     "yahoo.de", "yahoo.it", "yahoo.es"],
    },
    # AOL: умеренный
    "aol": {
        "delay_range": (2.0, 5.0),
        "max_per_conn": 30,
        "max_per_hour": 120,
        "warmup_start": 5,
        "domains": ["aol.com"],
    },
    # iCloud (Apple): строгий
    "icloud": {
        "delay_range": (3.0, 7.0),
        "max_per_conn": 20,
        "max_per_hour": 80,
        "warmup_start": 3,
        "domains": ["icloud.com", "me.com", "mac.com"],
    },
    # Zoho: быстрый
    "zoho": {
        "delay_range": (1.0, 3.0),
        "max_per_conn": 50,
        "max_per_hour": 300,
        "warmup_start": 10,
        "domains": ["zohomail.com", "zoho.com", "zohomail.eu"],
    },
    # GMX: быстрый
    "gmx": {
        "delay_range": (1.0, 3.0),
        "max_per_conn": 50,
        "max_per_hour": 250,
        "warmup_start": 10,
        "domains": ["gmx.com", "gmx.net", "gmx.de"],
    },
}

# Дефолтный профиль для корпоративных/неизвестных доменов (быстрее всех)
_DEFAULT_PROFILE: dict[str, Any] = {
    "delay_range": (0.8, 2.5),
    "max_per_conn": 60,
    "max_per_hour": 500,
    "warmup_start": 15,
}

# ── Маппинг домен → профиль (строится один раз) ───────────

_DOMAIN_MAP: dict[str, str] = {}

def _build_domain_map() -> None:
    for group_name, profile in _PROFILES.items():
        for domain in profile.get("domains", []):
            _DOMAIN_MAP[domain.lower()] = group_name

_build_domain_map()


# ── Публичный API ─────────────────────────────────────────

def get_domain_group(email: str) -> str:
    """Определяет группу провайдера по email.
    
    Returns: "gmail", "outlook", "yahoo", ... или "other"
    """
    if "@" not in email:
        return "other"
    domain = email.split("@")[-1].lower()
    return _DOMAIN_MAP.get(domain, "other")


def get_profile(email_or_group: str) -> dict[str, Any]:
    """Возвращает профиль провайдера для email или группы.
    
    >>> get_profile("user@gmail.com")
    {"delay_range": (2.0, 5.0), ...}
    >>> get_profile("gmail")
    {"delay_range": (2.0, 5.0), ...}
    """
    # Если передан email
    if "@" in email_or_group:
        group = get_domain_group(email_or_group)
    else:
        group = email_or_group
    
    return dict(_PROFILES.get(group, _DEFAULT_PROFILE))


def get_delay(email: str, base_delay: float = 0.0, jitter: float = 0.0) -> float:
    """Вычисляет задержку для конкретного получателя.
    
    Если base_delay > 0 — пользователь задал своё значение, используем ЕГО + jitter.
    Если base_delay == 0 — авто-режим, берём из профиля домена.
    
    Returns: финальная задержка в секундах
    """
    rnd = random.SystemRandom()
    
    if base_delay > 0:
        # Пользователь задал свой delay — используем ЕГО
        return max(0.1, base_delay + rnd.uniform(-jitter, jitter))
    
    # Авто-режим: берём из профиля домена
    profile = get_profile(email)
    lo, hi = profile["delay_range"]
    return rnd.uniform(lo, hi)


def get_warmup_factor(sent_count: int, email: str = "") -> float:
    """Возвращает множитель задержки для warm-up.
    
    Новый аккаунт шлёт медленнее, постепенно ускоряется.
    
    Returns: 1.0 = нормальная скорость, 3.0 = втрое медленнее
    """
    profile = get_profile(email) if email else _DEFAULT_PROFILE
    warmup_start = profile.get("warmup_start", 10)
    
    if sent_count < warmup_start:
        return 3.0
    elif sent_count < warmup_start * 5:
        return 2.0
    elif sent_count < warmup_start * 20:
        return 1.3
    return 1.0


def get_max_per_conn(email: str) -> int:
    """Возвращает лимит писем на одно SMTP соединение для домена."""
    profile = get_profile(email)
    return profile.get("max_per_conn", 50)
