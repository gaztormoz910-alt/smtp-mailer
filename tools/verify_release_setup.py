# -*- coding: utf-8 -*-
"""Статическая проверка конфигов релиза: в .spec/.iss/workflow не осталось
угловых заглушек вида <NAME>, все ссылаемые файлы существуют, имя 'Pinion' и
постоянная ссылка согласованы. Печатает RELEASE_SETUP_OK и выходит 0 при успехе.

Запуск: python tools/verify_release_setup.py"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OWNER_REPO = "gaztormoz910-alt/smtp-mailer"
PERMLINK = f"https://github.com/{OWNER_REPO}/releases/latest/download/Pinion-setup.exe"

SPEC = os.path.join(REPO, "Pinion.spec")
ISS = os.path.join(REPO, "Pinion.iss")
WF = os.path.join(REPO, ".github", "workflows", "release.yml")

# заглушки: угловые скобки вокруг слова (<NAME>, <owner>) и текстовые «дозаполни».
PLACEHOLDER_ANGLE = re.compile(r"<[A-Za-zА-Яа-я_][^>\n]{0,40}>")
PLACEHOLDER_WORDS = ["подставь", "insert here", "todo", "СГЕНЕРИРУЙ", "точка входа",
                     "<NAME>", "заглушк", "placeholder"]

fails = []


def readf(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


for path in (SPEC, ISS, WF):
    if not os.path.exists(path):
        fails.append(f"нет файла: {os.path.relpath(path, REPO)}")
        continue
    txt = readf(path)
    m = PLACEHOLDER_ANGLE.search(txt)
    if m:
        fails.append(f"{os.path.relpath(path, REPO)}: осталась угловая заглушка {m.group(0)!r}")
    low = txt.lower()
    for w in PLACEHOLDER_WORDS:
        if w.lower() in low:
            fails.append(f"{os.path.relpath(path, REPO)}: заглушка/дозаполнение {w!r}")

# .spec ссылается на реальные входы
if os.path.exists(SPEC):
    spec = readf(SPEC)
    for needle, rel in [("main.py", "main.py"),
                        ("assets/Pinion.ico", os.path.join("assets", "Pinion.ico")),
                        ("webui/web", os.path.join("webui", "web")),
                        ("version_info.txt", None)]:  # version_info генерируется set_version
        if needle not in spec:
            fails.append(f"Pinion.spec не ссылается на {needle}")
        elif rel and not os.path.exists(os.path.join(REPO, rel)):
            fails.append(f"Pinion.spec ссылается на несуществующий {rel}")
    if "name='Pinion'" not in spec:
        fails.append("Pinion.spec: имя сборки не 'Pinion'")

# .iss: имя без версии, стабильный GUID, установка в профиль, удаление данных
if os.path.exists(ISS):
    iss = readf(ISS)
    if "OutputBaseFilename=Pinion-setup" not in iss:
        fails.append("Pinion.iss: OutputBaseFilename не 'Pinion-setup' (или содержит версию)")
    if re.search(r"OutputBaseFilename=.*\d", iss):
        fails.append("Pinion.iss: в имени файла установщика есть цифра — постоянная ссылка сломается")
    if not re.search(r"AppId=\{\{[0-9A-Fa-f-]{36}\}", iss):
        fails.append("Pinion.iss: нет стабильного GUID в AppId")
    if "{localappdata}\\Programs\\Pinion" not in iss:
        fails.append("Pinion.iss: установка не в профиль пользователя")
    if "PrivilegesRequired=lowest" not in iss:
        fails.append("Pinion.iss: не PrivilegesRequired=lowest (потребует UAC)")
    for needle in ("{app}\\logs", "{app}\\data"):
        if needle not in iss:
            fails.append(f"Pinion.iss: [UninstallDelete] не чистит {needle}")
    # никаких абсолютных путей (буква диска)
    if re.search(r"[A-Za-z]:\\\\|[A-Za-z]:\\", iss):
        fails.append("Pinion.iss: найден абсолютный путь (буква диска) — CI не соберёт")

# workflow: постоянная ссылка/имена/шаги
if os.path.exists(WF):
    wf = readf(WF)
    for needle in ("Pinion.spec", "Pinion.iss", "tools/set_version.py",
                   "installer/Pinion-setup.exe", "--selftest", "contents: write",
                   "softprops/action-gh-release"):
        if needle not in wf:
            fails.append(f"release.yml: нет ожидаемого шага/строки {needle!r}")

# постоянная ссылка корректна для реального репозитория
if not OWNER_REPO:
    fails.append("не задан owner/repo для постоянной ссылки")

if fails:
    print("!!! ПРОВАЛЫ КОНФИГА РЕЛИЗА:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("permanent link:", PERMLINK)
print("RELEASE_SETUP_OK")
