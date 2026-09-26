"""Точка входа Pinion (бывш. SMTP MAILER).

По умолчанию `python main.py` открывает веб-интерфейс (pywebview + HTML/CSS/JS).
Старый интерфейс на CustomTkinter доступен через `python main.py ctk` (gui/ не трогаем).
Режим `python main.py --selftest <лог>` прогоняет ядро headless (для CI/проверок).
"""
import os
import sys
from pathlib import Path

from core.appenv import writable_base, APP_NAME, app_version

# Каталоги данных/логов создаём РЯДОМ С .exe (в заморозке) или в корне исходников.
# chdir туда же: часть кода пишет по относительным путям — так они не разъедутся.
BASE = writable_base()
try:
    os.chdir(BASE)
except Exception:
    pass
for d in ("data", "data/presets", "logs"):
    (BASE / d).mkdir(parents=True, exist_ok=True)


def _set_app_user_model_id() -> None:
    # Иначе при запуске из исходников Windows рисует на панели задач иконку python.exe.
    # У собранного .exe иконка берётся из ресурса самого файла, но AUMID не мешает.
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.App")
    except Exception:
        pass


def run_web() -> None:
    # Новый интерфейс. customtkinter здесь НЕ импортируется — вебу он не нужен.
    _set_app_user_model_id()
    from webui.host import main as web_main
    web_main()


def run_ctk() -> None:
    # Старый интерфейс на CustomTkinter (без изменений; gui/ не трогаем).
    _set_app_user_model_id()
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


def run_selftest(log_path: str) -> int:
    """Прогон РЕАЛЬНОГО пути ядра на укороченных данных без сети и GUI.

    Запуск окна почти ничего не доказывает: рендер контента, сборка MIME и скоринг
    подключаются позже. Здесь мы дергаем именно их. Вывод пишем в файл: у сборки с
    console=False sys.stdout/err равны None, прямая печать упала бы."""
    # Часть 6.1: без utf-8 вывод падает в cmd.exe (cp1252) на кириллице — тогда токен
    # SELFTEST_OK не печатается, хотя код 0. Реконфигурируем прежде любой печати.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    lines: list[str] = []
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        lines.append(f"[{'OK' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        if not cond:
            ok = False

    try:
        check("version", bool(app_version()), app_version())

        # Проверка «зависимости реально в сборке» (Часть 6.4): импортируем ВЕСЬ рантайм-набор,
        # включая GUI-бэкенд (webview+clr) и ленивые сторонние (requests/socks). Если что-то не
        # положено в сборку — падение видно здесь, а не у пользователя посреди работы. Окна не
        # создаём — только импорт.
        import importlib
        for mod in ("requests", "socks", "webview", "clr", "customtkinter",
                    "core.proxy_manager", "core.smtp_manager", "core.sender",
                    "webui.host", "webui.letter_score", "gui.window"):
            try:
                importlib.import_module(mod)
                check(f"import {mod}", True)
            except Exception as e:
                check(f"import {mod}", False, repr(e))

        from core.content import spin, substitute, substitute_links, is_html
        # spin намеренно СОХРАНЯЕТ {{переменные}} (подставляются позже) — поэтому
        # раскрытие спинтакс-скобок проверяем на шаблоне БЕЗ переменных.
        spun = spin("{Привет|Здравствуй}, друг! {Как дела|Как ты}?")
        check("spin: скобки раскрыты", "{" not in spun and "}" not in spun and "|" not in spun, spun)
        check("spin: выбрана ветка", spun.startswith(("Привет", "Здравствуй")), spun)
        subd = substitute("Привет, {{name}}!", {"name": "Алекс"})
        check("substitute: имя подставлено", "Алекс" in subd and "{{" not in subd, subd)

        from core.sender import build_message, interleave_by_domain
        body = "Привет, Алекс! Загляни: https://example.com/x"
        msg = build_message("from@example.com", "to@gmail.com", "Тестовая тема",
                            body, is_html(body), sender_name="Алекс", plain_text_only=True)
        raw = msg.as_string()
        check("build_message: собрано письмо", "Subject" in raw and "from@example.com" in raw,
              f"{len(raw)} байт")

        from core.queue_manager import Recipient
        rcpts = [Recipient(email=f"u{i}@{d}", name=f"U{i}")
                 for i, d in enumerate(["gmail.com", "yahoo.com", "outlook.com"] * 4)]
        mixed = interleave_by_domain(rcpts)
        check("interleave_by_domain: сохранил всех", len(mixed) == len(rcpts),
              f"{len(mixed)}/{len(rcpts)}")

        try:
            from webui.letter_score import score_letter
        except ImportError:
            from letter_score import score_letter
        res = score_letter("Тестовая тема письма про встречу", body)
        check("score_letter: вернул оценку", isinstance(res, dict) and len(res) > 0,
              str(list(res)[:5]) if isinstance(res, dict) else type(res).__name__)
    except Exception as exc:
        import traceback
        lines.append("EXCEPTION: " + repr(exc))
        lines.append(traceback.format_exc())
        ok = False

    lines.append("SELFTEST_OK" if ok else "SELFTEST_FAIL")
    text = "\n".join(lines) + "\n"
    try:
        Path(log_path).write_text(text, encoding="utf-8")
    except Exception:
        pass
    if sys.stdout:
        try:
            sys.stdout.write(text)
        except Exception:
            pass
    return 0 if ok else 1


def main() -> None:
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if arg == "--selftest":
        log = sys.argv[2] if len(sys.argv) > 2 else str(BASE / "selftest.log")
        sys.exit(run_selftest(log))
    if arg in ("ctk", "old", "tk", "gui"):
        run_ctk()
    else:
        run_web()


if __name__ == "__main__":
    main()
