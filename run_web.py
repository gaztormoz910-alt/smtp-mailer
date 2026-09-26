"""Запуск веб-интерфейса Pinion (pywebview + HTML/CSS/JS).

Старый интерфейс на CustomTkinter доступен через `python main.py ctk`.
Этот файл — прямая точка входа в веб-интерфейс (то же, что `python main.py`).
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent
for d in ("data", "data/presets", "logs"):
    (BASE / d).mkdir(parents=True, exist_ok=True)

from webui.host import main

if __name__ == "__main__":
    main()
