"""Запуск нового веб-интерфейса SMTP MAILER (pywebview + HTML/CSS/JS).

Старый интерфейс на CustomTkinter по-прежнему доступен через `python main.py`.
Этот файл — точка входа для новой версии интерфейса на время миграции.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent
for d in ("data", "data/presets", "logs"):
    (BASE / d).mkdir(parents=True, exist_ok=True)

from webui.host import main

if __name__ == "__main__":
    main()
