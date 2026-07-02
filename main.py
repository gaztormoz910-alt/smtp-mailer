"""
CHARLY MAILER — точка входа.
Запуск: python main.py
"""

from pathlib import Path

import customtkinter as ctk

from gui.window import App

# Гарантируем наличие рабочих директорий
BASE = Path(__file__).resolve().parent
for d in ("data", "data/presets", "logs"):
    (BASE / d).mkdir(parents=True, exist_ok=True)


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
