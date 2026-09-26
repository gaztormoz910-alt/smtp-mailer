# -*- coding: utf-8 -*-
"""Единственный источник версии: пишет файл VERSION и генерирует version_info.txt
для ресурса версии `.exe`. Так тег, окно, свойства файла и запись деинсталляции
физически не могут разойтись — все читают из VERSION.

Windows требует в ресурсе версии РОВНО четыре числа: '1.0.5' → (1, 0, 5, 0).

Запуск: python tools/set_version.py 1.0.0
        python tools/set_version.py            (перечитать текущий VERSION)
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(REPO, "VERSION")
VINFO_FILE = os.path.join(REPO, "version_info.txt")

APP_NAME = "Pinion"
COMPANY = "Pinion"
DESCRIPTION = "Pinion — массовые email-рассылки через пул SMTP и SOCKS-прокси"


def _read_current() -> str:
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1.0.0"


def _normalize(v: str) -> tuple[str, tuple[int, int, int, int]]:
    v = v.strip().lstrip("vV").strip()
    if not re.fullmatch(r"\d+(\.\d+){0,3}", v):
        raise SystemExit(f"плохая версия: {v!r} (нужно вида 1.0.0)")
    parts = [int(x) for x in v.split(".")]
    while len(parts) < 4:
        parts.append(0)
    parts = parts[:4]
    # каноническая строка — первые три числа (мажор.минор.патч)
    canonical = ".".join(str(x) for x in parts[:3])
    return canonical, (parts[0], parts[1], parts[2], parts[3])


def _vinfo(canonical: str, quad: tuple[int, int, int, int]) -> str:
    a, b, c, d = quad
    # формат ресурса версии PyInstaller (VSVersionInfo). Кавычки и запятые критичны.
    return f"""# UTF-8 — сгенерировано tools/set_version.py, руками не править
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({a}, {b}, {c}, {d}),
    prodvers=({a}, {b}, {c}, {d}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040904B0', [
        StringStruct(u'CompanyName', u'{COMPANY}'),
        StringStruct(u'FileDescription', u'{DESCRIPTION}'),
        StringStruct(u'FileVersion', u'{canonical}'),
        StringStruct(u'InternalName', u'{APP_NAME}'),
        StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
        StringStruct(u'ProductName', u'{APP_NAME}'),
        StringStruct(u'ProductVersion', u'{canonical}')
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else _read_current()
    canonical, quad = _normalize(raw)
    with open(VERSION_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(canonical + "\n")
    with open(VINFO_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(_vinfo(canonical, quad))
    print(f"VERSION={canonical}  quad={quad}")
    print(f"  -> {VERSION_FILE}")
    print(f"  -> {VINFO_FILE}")
    print("SET_VERSION_OK")


if __name__ == "__main__":
    main()
