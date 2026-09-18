# -*- coding: utf-8 -*-
# Ручной регресс-тест контента (2026). Раньше здесь проверялось, что омоглифы/entities
# не ломают <a>. Эти приёмы УДАЛЕНЫ (фильтры 2026 детектят их как фишинг), поэтому тест
# теперь доказывает ОБРАТНОЕ: движок их больше НЕ добавляет, а ссылки и спинтакс целы.
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
from core.content import render

VARS = {"name": "John", "email": "john@mail.com", "senderName": "Sam"}
LINKS = {"": ["https://example.com/link?ref=abc123"]}
ZW = ["​", "‌", "‍", "⁠", "﻿"]
ENT = re.compile(r"&#x?[0-9A-Fa-f]+;")
ok = True

print("=== ТЕСТ 1: plain-text — нет омоглифов и zero-width ===")
plain = "hey {{name}}, {i saw your note|someone left a message}. {here|}: [[LINK]]"
for t in range(20):
    r = render(plain, VARS, link_pools=LINKS, is_subject=False)
    if not r.isascii() or any(z in r for z in ZW) or "example.com" not in r:
        print(f"  ❌ ПРОВАЛ (trial {t}): {r!r}"); ok = False; break
else:
    print("  ✅ 20/20 — вывод чистый ASCII, без zero-width, ссылка на месте")

print("\n=== ТЕСТ 2: HTML — нет zero-width/entity-букв, <a> и ссылка целы ===")
html = ('<div style="font-size:{15|16}px"><p>hey {{name}}, {check this|take a look}</p>'
        '<a href="[[LINK]]" style="color:#39f">{see it|open}</a></div>')
for t in range(20):
    r = render(html, VARS, link_pools=LINKS, is_subject=False)
    if any(z in r for z in ZW) or ENT.search(r) or "<a href=" not in r or "example.com" not in r:
        print(f"  ❌ ПРОВАЛ (trial {t}): {r!r}"); ok = False; break
else:
    print("  ✅ 20/20 — без zero-width, без entity-букв, <a> и ссылка целы")

print("\nOK" if ok else "\nFAILED")
sys.exit(0 if ok else 1)
