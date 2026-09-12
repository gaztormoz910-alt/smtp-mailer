

from __future__ import annotations

import random
from typing import Any


_PROFILES: dict[str, dict[str, Any]] = {
    "gmail": {
        "delay_range": (2.0, 5.0),
        "max_per_conn": 30,
        "max_per_hour": 150,
        "warmup_start": 5,
        "domains": ["gmail.com", "googlemail.com"],
    },
    "outlook": {
        "delay_range": (1.5, 4.0),
        "max_per_conn": 40,
        "max_per_hour": 200,
        "warmup_start": 10,
        "domains": ["outlook.com", "hotmail.com", "live.com", "msn.com"],
    },
    "yahoo": {
        "delay_range": (3.0, 8.0),
        "max_per_conn": 20,
        "max_per_hour": 100,
        "warmup_start": 3,
        "domains": ["yahoo.com", "ymail.com", "rocketmail.com",
                     "yahoo.co.uk", "yahoo.co.jp", "yahoo.fr",
                     "yahoo.de", "yahoo.it", "yahoo.es"],
    },
    "aol": {
        "delay_range": (2.0, 5.0),
        "max_per_conn": 30,
        "max_per_hour": 120,
        "warmup_start": 5,
        "domains": ["aol.com"],
    },
    "icloud": {
        "delay_range": (3.0, 7.0),
        "max_per_conn": 20,
        "max_per_hour": 80,
        "warmup_start": 3,
        "domains": ["icloud.com", "me.com", "mac.com"],
    },
    "zoho": {
        "delay_range": (1.0, 3.0),
        "max_per_conn": 50,
        "max_per_hour": 300,
        "warmup_start": 10,
        "domains": ["zohomail.com", "zoho.com", "zohomail.eu"],
    },
    "gmx": {
        "delay_range": (1.0, 3.0),
        "max_per_conn": 50,
        "max_per_hour": 250,
        "warmup_start": 10,
        "domains": ["gmx.com", "gmx.net", "gmx.de"],
    },
}

_DEFAULT_PROFILE: dict[str, Any] = {
    "delay_range": (0.8, 2.5),
    "max_per_conn": 60,
    "max_per_hour": 500,
    "warmup_start": 15,
}


_DOMAIN_MAP: dict[str, str] = {}

def _build_domain_map() -> None:
    for group_name, profile in _PROFILES.items():
        for domain in profile.get("domains", []):
            _DOMAIN_MAP[domain.lower()] = group_name

_build_domain_map()


def get_domain_group(email: str) -> str:
    
    if "@" not in email:
        return "other"
    domain = email.split("@")[-1].lower()
    return _DOMAIN_MAP.get(domain, "other")


def get_profile(email_or_group: str) -> dict[str, Any]:
    
    if "@" in email_or_group:
        group = get_domain_group(email_or_group)
    else:
        group = email_or_group
    
    return dict(_PROFILES.get(group, _DEFAULT_PROFILE))


def get_delay(email: str, base_delay: float = 0.0, jitter: float = 0.0) -> float:
    
    
    rnd = random.SystemRandom()
    
    if base_delay > 0:
        return max(0.1, base_delay + rnd.uniform(-jitter, jitter))
    
    profile = get_profile(email)
    lo, hi = profile["delay_range"]
    return rnd.uniform(lo, hi)


def get_warmup_factor(sent_count: int, email: str = "") -> float:
    
    
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
    profile = get_profile(email)
    return profile.get("max_per_conn", 50)
