"""Точка входа SMTP MAILER.

По умолчанию `python main.py` открывает НОВЫЙ веб-интерфейс (pywebview + HTML/CSS/JS).
Старый интерфейс на CustomTkinter сохранён и доступен через `python main.py ctk`.
(Прежний запрет на правку main.py снят владельцем — миграция на веб как основной вход.)
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
for d in ("data", "data/presets", "logs"):
    (BASE / d).mkdir(parents=True, exist_ok=True)


def run_web() -> None:
    # Новый интерфейс. customtkinter здесь НЕ импортируется — вебу он не нужен.
    from webui.host import main as web_main
    web_main()


def run_ctk() -> None:
    # Старый интерфейс на CustomTkinter (без изменений; gui/ не трогаем).
    import customtkinter as ctk
    from gui.window import App

    # Патч скроллбара CTkScrollableFrame: авто-скрытие и корректные отступы.
    original_init = ctk.CTkScrollableFrame.__init__

    def __init__(self, *args, **kwargs):
        from gui.theme import COLOR_BORDER, COLOR_TEXT_DIM
        kwargs.setdefault("scrollbar_fg_color", "transparent")
        kwargs.setdefault("scrollbar_button_color", COLOR_BORDER)
        kwargs.setdefault("scrollbar_button_hover_color", COLOR_TEXT_DIM)

        original_init(self, *args, **kwargs)

        corner = self._parent_frame.cget("corner_radius")
        border = self._parent_frame.cget("border_width")
        if isinstance(corner, str): corner = 0 if not corner.isdigit() else int(corner)
        if isinstance(border, str): border = 0 if not border.isdigit() else int(border)

        spacing = self._apply_widget_scaling(corner + border)
        pad_x = 6
        pad_y = spacing

        if self._orientation == "vertical":
            self._scrollbar.grid(padx=(0, pad_x), pady=pad_y)
        else:
            self._scrollbar.grid(pady=(0, pad_x), padx=pad_y)

        original_set = self._scrollbar.set

        def _set(first, last):
            if float(first) <= 0.0 and float(last) >= 1.0:
                self._scrollbar.grid_remove()
                if self._orientation == "vertical":
                    self._parent_canvas.grid(padx=spacing)
                else:
                    self._parent_canvas.grid(pady=spacing)
            else:
                self._scrollbar.grid()
                if self._orientation == "vertical":
                    self._parent_canvas.grid(padx=(spacing, 0))
                else:
                    self._parent_canvas.grid(pady=(spacing, 0))
            original_set(first, last)

        self._scrollbar.set = _set
        if self._orientation == "vertical":
            self._parent_canvas.configure(yscrollcommand=_set)
        else:
            self._parent_canvas.configure(xscrollcommand=_set)
        _set(0.0, 1.0)

    ctk.CTkScrollableFrame.__init__ = __init__

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    App().mainloop()


def main() -> None:
    # `python main.py ctk` → старый CTk; иначе (по умолчанию) → новый веб-интерфейс.
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if arg in ("ctk", "old", "tk", "gui"):
        run_ctk()
    else:
        run_web()


if __name__ == "__main__":
    main()
