import os
import sys
from pathlib import Path

from core.appenv import writable_base, APP_NAME, app_version

_ORIG_CWD = Path.cwd()

BASE = writable_base()
try:
    os.chdir(BASE)
except Exception:
    pass
for d in ("data", "data/presets", "logs"):
    (BASE / d).mkdir(parents=True, exist_ok=True)


def _set_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.App")
    except Exception:
        pass


def run_web() -> None:
    _set_app_user_model_id()
    from webui.host import main as web_main
    web_main()


def run_ctk() -> None:
    _set_app_user_model_id()
    import customtkinter as ctk
    from gui.window import App

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


def run_selftest(log_path: str, core_only: bool = False) -> int:
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

    def warn(name: str, cond: bool, detail: str = "") -> None:
        lines.append(f"[{'OK' if cond else 'WARN'}] {name}{(' — ' + detail) if detail else ''}")

    try:
        check("version", bool(app_version()), app_version())

        import importlib
        for mod in ("requests", "socks", "core.proxy_manager", "core.smtp_manager",
                    "core.sender", "core.content", "core.queue_manager", "webui.letter_score"):
            try:
                importlib.import_module(mod)
                check(f"import {mod}", True)
            except Exception as e:
                check(f"import {mod}", False, repr(e))

        if not core_only:
            for mod in ("webview", "clr", "customtkinter", "gui.window", "webui.host"):
                try:
                    importlib.import_module(mod)
                    warn(f"import {mod}", True)
                except Exception as e:
                    warn(f"import {mod}", False, repr(e))
        else:
            lines.append("[SKIP] GUI-бэкенд (webview/clr/customtkinter/gui/host) — "
                         "не проверяется в CI; упаковка доказана локальным install+run")

        from core.content import spin, substitute, substitute_links, is_html
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
    if arg in ("--selftest", "--selftest-core"):
        raw = sys.argv[2] if len(sys.argv) > 2 else str(BASE / "selftest.log")
        log = raw if os.path.isabs(raw) else str(_ORIG_CWD / raw)
        sys.exit(run_selftest(log, core_only=(arg == "--selftest-core")))
    if arg in ("ctk", "old", "tk", "gui"):
        run_ctk()
    else:
        run_web()


if __name__ == "__main__":
    main()
