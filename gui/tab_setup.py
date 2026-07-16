"""Вкладка Setup — прокси (задача 2) + SMTP-аккаунты (задача 3).

Два фрейма в две колонки: слева Proxy Configuration, справа SMTP Configuration.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.logger import JsonLogger
from core.proxy_manager import ProxyManager, ProxyStatus
from core.smtp_manager import SmtpManager, SmtpStatus, SmtpAccount
from gui.theme import (
    COLOR_ACCENT, COLOR_ACCENT_HVR, COLOR_BG, COLOR_BORDER,
    COLOR_BTN, COLOR_BTN_HVR, COLOR_ERROR, COLOR_FRAME,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_WARN, FONT_FAMILY, FONT_MONO,
)
from gui.validation import register_int_validation, register_url_validation


class SetupTab:
    """Содержимое вкладки Setup."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        proxy_mgr: ProxyManager | None = None,
        smtp_mgr: SmtpManager | None = None,
    ) -> None:
        self.parent = parent
        self.proxy_mgr = proxy_mgr or ProxyManager()
        self.smtp_mgr = smtp_mgr or SmtpManager()
        self.logger = JsonLogger()

        # Трекинг файлов (для пресетов)
        self._proxy_file: str = ""
        self._smtp_file: str = ""

        # Трекинг виджетов
        self._proxy_label_map: dict[int, ctk.CTkLabel] = {}
        self._smtp_card_map: dict[int, dict] = {}
        self._proxy_checking = False
        self._smtp_checking = False
        self._px_page = 0
        self._sm_page = 0
        self._items_per_page = 40

        self._build_layout()

    # ══════════════════════════════════════════════════════
    #  LAYOUT — две колонки
    # ══════════════════════════════════════════════════════

    def _build_layout(self) -> None:
        container = ctk.CTkFrame(self.parent, fg_color="transparent")
        container.pack(fill="both", expand=True)

        container.grid_columnconfigure(0, weight=1, uniform="col")
        container.grid_columnconfigure(1, weight=1, uniform="col")
        container.grid_rowconfigure(0, weight=1)

        self._build_proxy_ui(container)
        self._build_smtp_ui(container)

    # ══════════════════════════════════════════════════════
    #  PROXY UI  (левая колонка)
    # ══════════════════════════════════════════════════════

    def _build_proxy_ui(self, container: ctk.CTkFrame) -> None:
        self.proxy_frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        self.proxy_frame.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)

        # ── Заголовок ─────────────────────────────────
        ctk.CTkLabel(
            self.proxy_frame, text="⚡  Настройки прокси",
            font=(FONT_FAMILY, 15, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            self.proxy_frame, text=".txt · формат: protocol://host:port или host:port",
            font=(FONT_MONO, 8), text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 4))

        # ── Строка 1: файл + URL ─────────────────────
        row1 = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(0, 5))

        self.btn_px_file = self._btn(row1, "📁 Загрузить файл", self._on_px_load_file, w=110)
        self.btn_px_file.pack(side="left", padx=(0, 6))

        self.px_url_entry = ctk.CTkEntry(
            row1, height=30, placeholder_text="https://…/proxy-list.txt",
            font=(FONT_FAMILY, 12), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER, corner_radius=8,
        )
        self.px_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        register_url_validation(self.px_url_entry)

        self.btn_px_url = self._btn(row1, "🌐 URL", self._on_px_load_url, w=80)
        self.btn_px_url.pack(side="left")

        # ── Строка 2: авто-обновление ────────────────
        row2 = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 5))

        self.px_auto_var = ctk.BooleanVar(value=False)
        self.px_auto_cb = ctk.CTkCheckBox(
            row2, text="Авто-обновление", variable=self.px_auto_var,
            font=(FONT_FAMILY, 11), text_color=COLOR_TEXT_DIM,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            checkmark_color=COLOR_ACCENT, border_color=COLOR_BORDER,
            corner_radius=4, width=20, command=self._on_px_auto_toggle,
        )
        self.px_auto_cb.pack(side="left")

        self.px_auto_min = ctk.CTkEntry(
            row2, width=40, height=26, placeholder_text="10",
            font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER,
            corner_radius=6, justify="center",
        )
        self.px_auto_min.pack(side="left", padx=4)
        register_int_validation(self.px_auto_min)

        ctk.CTkLabel(row2, text="мин", font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 10))

        # ── Строка 3: действия ────────────────
        row3 = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=(0, 5))

        self.btn_px_check = ctk.CTkButton(
            row3, text="⚡ Проверить все", width=105, height=28,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_WARN, font=(FONT_FAMILY, 12, "bold"),
            border_color=COLOR_WARN, border_width=2, corner_radius=8,
            command=self._on_px_check_all,
        )
        self.btn_px_check.pack(side="left", padx=(0, 6))

        self.btn_px_dead = self._btn(row3, "✕ Мертвые", self._on_px_remove_dead, w=70,
                                     text_color=COLOR_ERROR)
        self.btn_px_dead.pack(side="left", padx=(0, 4))

        self.btn_px_clear = self._btn(row3, "Очистить", self._on_px_clear, w=60,
                                      text_color=COLOR_TEXT_DIM)
        self.btn_px_clear.pack(side="left")

        self.btn_px_copy = self._btn(row3, "Копировать", self._on_px_copy, w=80,
                                      text_color=COLOR_TEXT_DIM)
        self.btn_px_copy.pack(side="right")

        # ── Статистика ───────────────────────────────
        self.px_stats = ctk.CTkLabel(
            self.proxy_frame,
            text="Всего: 0  ·  Живых: 0  ·  Мертвых: 0",
            font=(FONT_MONO, 11), text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.px_stats.pack(fill="x", padx=16, pady=(0, 2))

        self.px_action = ctk.CTkLabel(
            self.proxy_frame, text="", font=(FONT_FAMILY, 11),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.px_action.pack(fill="x", padx=16, pady=(0, 4))

        # ── Список прокси ────────────────────────────
        self.px_list = ctk.CTkScrollableFrame(
            self.proxy_frame, fg_color=COLOR_BG, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
            scrollbar_fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_TEXT_DIM
        )
        self.px_list.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        # ── Пагинация прокси ─────────────────────────
        self.px_page_frame = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")

        self.btn_px_prev = ctk.CTkButton(
            self.px_page_frame, text="< Назад", width=70, height=24,
            command=self._px_page_prev, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR, text_color=COLOR_TEXT
        )
        self.btn_px_prev.pack(side="left")

        self.lbl_px_page = ctk.CTkLabel(
            self.px_page_frame, text="Стр. 1 из 1", font=(FONT_FAMILY, 11), text_color=COLOR_TEXT
        )
        self.lbl_px_page.pack(side="left", expand=True)

        self.btn_px_next = ctk.CTkButton(
            self.px_page_frame, text="Вперед >", width=70, height=24,
            command=self._px_page_next, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR, text_color=COLOR_TEXT
        )
        self.btn_px_next.pack(side="right")

    # ── Proxy handlers ───────────────────────────────────

    def _on_px_load_file(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите список прокси",
            filetypes=[("Текст / CSV", "*.txt *.csv"), ("Все файлы", "*.*")],
        )
        if not paths:
            return
        self._px_set_state("disabled")

        def _do() -> None:
            try:
                total_count = 0
                for path in paths:
                    total_count += self.proxy_mgr.load_from_file(path)
                self._proxy_file = "; ".join(Path(p).name for p in paths)
                self.logger.info(f"Loaded {total_count} proxies from files",
                                 source="proxy")
                
                disp_name = f"{len(paths)} файлов" if len(paths) > 1 else Path(paths[0]).name
                self.parent.after(0, lambda: self._px_load_done(total_count, disp_name))
            except Exception as e:
                self.parent.after(0, lambda: self._px_load_err(str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _on_px_load_url(self) -> None:
        url = self.px_url_entry.get().strip()
        if not url:
            self.px_action.configure(text="✗  Сначала введите URL", text_color=COLOR_ERROR)
            return
        self._px_set_state("disabled")

        def _do() -> None:
            try:
                count = self.proxy_mgr.load_from_url(url)
                self.logger.info(f"Loaded {count} proxies from URL",
                                 source="proxy", url=url)
                self.parent.after(0, lambda: self._px_load_done(count, "URL"))
            except Exception as e:
                self.parent.after(0, lambda: self._px_load_err(str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _px_load_done(self, count: int, source: str) -> None:
        self._px_set_state("normal")
        self._px_page = 0
        self._px_refresh()
        
        # Проверяем, были ли HTTP прокси которые мы перевели в SOCKS5
        http_replaced = sum(1 for p in self.proxy_mgr.proxies if p.protocol == "socks5" and getattr(p, "_was_http", False))
        
        if http_replaced > 0:
            self.px_action.configure(
                text=f"⚠ Загружено {count} (в т.ч. {http_replaced} HTTP переведено в SOCKS5)",
                text_color=COLOR_WARN)
        else:
            self.px_action.configure(text=f"✓  Загружено {count} из {source}",
                                     text_color=COLOR_ACCENT)

    def _px_load_err(self, msg: str) -> None:
        self._px_set_state("normal")
        self.px_action.configure(text=f"✗  {msg}", text_color=COLOR_ERROR)
        self.logger.network_error(f"Proxy load error: {msg}", source="proxy")

    def _on_px_check_all(self) -> None:
        if self._proxy_checking or self.proxy_mgr.count_total == 0:
            return
        self._proxy_checking = True
        self.proxy_mgr.reset_all()
        self._px_refresh()
        self._px_set_state("disabled")
        self.btn_px_dead.configure(state="normal")
        self.btn_px_check.configure(text="0 %", state="disabled")

        last_pct = -1
        def stats_loop():
            if self._proxy_checking:
                self._px_update_stats()
                self.parent.after(200, stats_loop)
        stats_loop()

        def on_prog(checked: int, total: int, proxy) -> None:
            nonlocal last_pct
            pct = int(checked / total * 100) if total else 0
            lbl_exists = id(proxy) in self._proxy_label_map
            pct_changed = pct != last_pct

            if lbl_exists or pct_changed:
                def _u(p=proxy, c=checked, p_changed=pct_changed, curr_pct=pct) -> None:
                    nonlocal last_pct
                    if p_changed:
                        self.btn_px_check.configure(text=f"{curr_pct} %")
                        last_pct = curr_pct
                    lbl = self._proxy_label_map.get(id(p))
                    if lbl:
                        lbl.configure(text=self._px_row(p), text_color=self._px_color(p.status))
                self.parent.after(0, _u)

        def on_done() -> None:
            def _f() -> None:
                self._proxy_checking = False
                self.btn_px_check.configure(text="⚡ Проверить все", state="normal")
                self._px_set_state("normal")
                self._px_update_stats()
                a, d = self.proxy_mgr.count_alive, self.proxy_mgr.count_dead
                self.px_action.configure(
                    text=f"✓  Готово — Живых: {a}  Мертвых: {d}", text_color=COLOR_ACCENT)
                self.logger.info(f"Proxy check done: alive={a}, dead={d}",
                                 source="proxy")
            self.parent.after(0, _f)

        self.proxy_mgr.check_all(on_progress=on_prog, on_done=on_done)

    def _on_px_remove_dead(self) -> None:
        n = self.proxy_mgr.remove_dead()
        self._px_page = 0
        self._px_refresh()
        self.px_action.configure(text=f"✓  Удалено {n} мертвых", text_color=COLOR_ACCENT)

    def _on_px_clear(self) -> None:
        self.proxy_mgr.clear()
        self._px_page = 0
        self._px_refresh()
        self.px_action.configure(text="🧹  Очищено", text_color=COLOR_TEXT_DIM)

    def _on_px_copy(self) -> None:
        text = "\n".join(p.url for p in self.proxy_mgr.proxies)
        if text:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(text)

    def _on_px_auto_toggle(self) -> None:
        if self.px_auto_var.get():
            url = self.px_url_entry.get().strip()
            if not url:
                self.px_auto_var.set(False)
                self.px_action.configure(text="✗  Введите URL для авто-обновления",
                                         text_color=COLOR_ERROR)
                return
            try:
                mins = max(1, int(self.px_auto_min.get() or "10"))
            except ValueError:
                mins = 10
            self.proxy_mgr.start_auto_refresh(
                url, mins,
                on_refresh=lambda c: self.parent.after(0, lambda: (
                    self._px_refresh(),
                    self.px_action.configure(
                        text=f"↻  Обновлено: {c} прокси", text_color=COLOR_ACCENT),
                )),
            )
            self.px_action.configure(text=f"↻  Авто-обновление ВКЛ ({mins} мин)",
                                     text_color=COLOR_ACCENT)
        else:
            self.proxy_mgr.stop_auto_refresh()
            self.px_action.configure(text="↻  Авто-обновление ВЫКЛ",
                                     text_color=COLOR_TEXT_DIM)

    # ── Proxy helpers ────────────────────────────────────

    def _px_page_prev(self) -> None:
        if self._px_page > 0:
            self._px_page -= 1
            self._px_refresh()

    def _px_page_next(self) -> None:
        total_pages = max(1, (self.proxy_mgr.count_total + self._items_per_page - 1) // self._items_per_page)
        if self._px_page < total_pages - 1:
            self._px_page += 1
            self._px_refresh()

    def _px_refresh(self) -> None:
        for lbl in self._proxy_label_map.values():
            lbl.destroy()
        self._proxy_label_map.clear()
        
        start = self._px_page * self._items_per_page
        end = start + self._items_per_page
        page_items = self.proxy_mgr.proxies[start:end]
        
        for proxy in page_items:
            lbl = ctk.CTkLabel(
                self.px_list, text=self._px_row(proxy),
                font=(FONT_MONO, 11), text_color=self._px_color(proxy.status),
                anchor="w", height=20,
            )
            lbl.pack(fill="x", padx=4, pady=1)
            self._proxy_label_map[id(proxy)] = lbl
            
        total_pages = max(1, (self.proxy_mgr.count_total + self._items_per_page - 1) // self._items_per_page)
        
        if total_pages <= 1:
            self.px_page_frame.pack_forget()
        else:
            self.px_page_frame.pack(fill="x", padx=16, pady=(0, 14))
            
        self.lbl_px_page.configure(text=f"Стр. {self._px_page + 1} из {total_pages}")
        self.btn_px_prev.configure(state="normal" if self._px_page > 0 else "disabled")
        self.btn_px_next.configure(state="normal" if self._px_page < total_pages - 1 else "disabled")
        
        self.px_list._parent_canvas.yview_moveto(0)
        self._px_update_stats()

    def _px_update_stats(self) -> None:
        t = self.proxy_mgr.count_total
        a = self.proxy_mgr.count_alive
        d = self.proxy_mgr.count_dead
        self.px_stats.configure(text=f"Всего: {t}  ·  Живых: {a}  ·  Мертвых: {d}")

    @staticmethod
    def _px_row(p) -> str:
        server_info = f"  ✓ {p.passed_server}" if getattr(p, "passed_server", "") else ""
        geo = ""
        ping = ""
        if p.status.name == "ALIVE":
            geo_code = getattr(p, "country", "")
            if geo_code:
                from core.countries import COUNTRIES_RU
                geo_name = COUNTRIES_RU.get(geo_code.upper(), geo_code)
                geo = f" [{geo_name}]"
            else:
                geo = " [?]"
            ping = f" {p.ping_ms}ms" if getattr(p, "ping_ms", 0) else ""
        return f" [{p.protocol.upper():6s}] {p.host}:{p.port:<6}  {p.status.value}{ping}{geo}{server_info}"

    @staticmethod
    def _px_color(status: ProxyStatus) -> str:
        if status == ProxyStatus.ALIVE:
            return COLOR_ACCENT
        if status == ProxyStatus.DEAD:
            return COLOR_ERROR
        return COLOR_TEXT_DIM

    def _px_set_state(self, state: str) -> None:
        for w in (self.btn_px_file, self.btn_px_url, self.btn_px_clear, self.btn_px_dead):
            w.configure(state=state)
        if state == "normal" and not self._proxy_checking:
            self.btn_px_check.configure(state="normal")

    # ══════════════════════════════════════════════════════
    #  SMTP UI  (правая колонка)
    # ══════════════════════════════════════════════════════

    def _build_smtp_ui(self, container: ctk.CTkFrame) -> None:
        self.smtp_frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        self.smtp_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)

        # ── Заголовок ─────────────────────────────────
        ctk.CTkLabel(
            self.smtp_frame, text="📧  Настройки SMTP",
            font=(FONT_FAMILY, 15, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            self.smtp_frame, text=".txt · формат: host:port:email:password",
            font=(FONT_MONO, 8), text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 4))

        # ── Кнопки ───────────────────────────────────
        row1 = ctk.CTkFrame(self.smtp_frame, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(0, 5))

        self.btn_sm_file = self._btn(row1, "📁 Загрузить файл",
                                     self._on_sm_load_file, w=140)
        self.btn_sm_file.pack(side="left", padx=(0, 6))

        # ── Строка 2: действия ────────────────
        row2 = ctk.CTkFrame(self.smtp_frame, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 5))

        self.btn_sm_check = ctk.CTkButton(
            row2, text="⚡ Проверить все", width=110, height=30,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_WARN, font=(FONT_FAMILY, 12, "bold"),
            border_color=COLOR_WARN, border_width=2, corner_radius=8,
            command=self._on_sm_check_all,
        )
        self.btn_sm_check.pack(side="left", padx=(0, 6))

        self.btn_sm_dead = self._btn(row2, "✕ Мертвые", self._on_sm_remove_dead, w=70,
                                     text_color=COLOR_ERROR)
        self.btn_sm_dead.pack(side="left", padx=(0, 4))

        self.btn_sm_clear = self._btn(row2, "Очистить", self._on_sm_clear, w=60,
                                      text_color=COLOR_TEXT_DIM)
        self.btn_sm_clear.pack(side="left")
        
        self.btn_sm_copy = self._btn(row2, "Копировать", self._on_sm_copy, w=80,
                                      text_color=COLOR_TEXT_DIM)
        self.btn_sm_copy.pack(side="right")

        # ── Статистика ───────────────────────────────
        self.sm_stats = ctk.CTkLabel(
            self.smtp_frame,
            text="Всего: 0  ·  Живых: 0  ·  Мертвых: 0",
            font=(FONT_MONO, 11), text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.sm_stats.pack(fill="x", padx=16, pady=(0, 2))

        self.sm_action = ctk.CTkLabel(
            self.smtp_frame, text="", font=(FONT_FAMILY, 11),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.sm_action.pack(fill="x", padx=16, pady=(0, 4))

        # ── Список-карточки ──────────────────────────
        self.sm_list = ctk.CTkScrollableFrame(
            self.smtp_frame, fg_color=COLOR_BG, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
            scrollbar_fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_TEXT_DIM
        )
        self.sm_list.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        # ── Пагинация SMTP ───────────────────────────
        self.sm_page_frame = ctk.CTkFrame(self.smtp_frame, fg_color="transparent")

        self.btn_sm_prev = ctk.CTkButton(
            self.sm_page_frame, text="< Назад", width=70, height=24,
            command=self._sm_page_prev, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR, text_color=COLOR_TEXT
        )
        self.btn_sm_prev.pack(side="left")

        self.lbl_sm_page = ctk.CTkLabel(
            self.sm_page_frame, text="Стр. 1 из 1", font=(FONT_FAMILY, 11), text_color=COLOR_TEXT
        )
        self.lbl_sm_page.pack(side="left", expand=True)

        self.btn_sm_next = ctk.CTkButton(
            self.sm_page_frame, text="Вперед >", width=70, height=24,
            command=self._sm_page_next, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR, text_color=COLOR_TEXT
        )
        self.btn_sm_next.pack(side="right")

    # ── SMTP handlers ────────────────────────────────────

    def _on_sm_load_file(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите файл SMTP аккаунтов",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")],
        )
        if not paths:
            return
        self._sm_set_state("disabled")

        def _do() -> None:
            try:
                total_count = 0
                for path in paths:
                    total_count += self.smtp_mgr.load_from_file(path)
                self._smtp_file = "; ".join(Path(p).name for p in paths)
                self.logger.info(f"Loaded {total_count} SMTP accounts from {len(paths)} files",
                                 source="smtp")
                disp_name = f"{len(paths)} файлов" if len(paths) > 1 else Path(paths[0]).name
                self.parent.after(0, lambda: self._sm_load_done(total_count, disp_name))
            except Exception as e:
                self.parent.after(0, lambda: self._sm_load_err(str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _sm_load_done(self, count: int, name: str) -> None:
        self._sm_set_state("normal")
        self._sm_page = 0
        self._sm_refresh()
        
        # Устанавливаем уникальные SMTP хосты как цели для проверки прокси
        from core.proxy_manager import set_user_smtp_targets
        set_user_smtp_targets(self.smtp_mgr.accounts)
        
        self.sm_action.configure(text=f"✓  Loaded {count} from {name}",
                                 text_color=COLOR_ACCENT)

    def _sm_load_err(self, msg: str) -> None:
        self._sm_set_state("normal")
        self.sm_action.configure(text=f"✗  {msg}", text_color=COLOR_ERROR)

    def _on_sm_check_all(self) -> None:
        if self._smtp_checking or self.smtp_mgr.count_total == 0:
            return
        self._smtp_checking = True
        self.smtp_mgr.reset_all()
        self._sm_refresh()
        self._sm_set_state("disabled")
        self.btn_sm_dead.configure(state="normal")
        self.btn_sm_check.configure(text="0 %", state="disabled")

        def proxy_getter():
            return self.proxy_mgr.get_next()  # None если нет живых прокси

        last_pct = -1
        def sm_stats_loop():
            if self._smtp_checking:
                self._sm_update_stats()
                self.parent.after(200, sm_stats_loop)
        sm_stats_loop()

        def on_prog(checked: int, total: int, acc: SmtpAccount) -> None:
            nonlocal last_pct
            pct = int(checked / total * 100) if total else 0
            card_exists = id(acc) in self._smtp_card_map
            pct_changed = pct != last_pct

            if card_exists or pct_changed:
                def _u(a=acc, c=checked, p_changed=pct_changed, curr_pct=pct) -> None:
                    nonlocal last_pct
                    if p_changed:
                        self.btn_sm_check.configure(text=f"{curr_pct} %")
                        last_pct = curr_pct
                    if id(a) in self._smtp_card_map:
                        self._sm_update_card(a)
                self.parent.after(0, _u)

        def on_done() -> None:
            def _f() -> None:
                self._smtp_checking = False
                self.btn_sm_check.configure(text="⚡ Проверить все", state="normal")
                self._sm_set_state("normal")
                self._sm_update_stats()
                a, d = self.smtp_mgr.count_alive, self.smtp_mgr.count_dead
                self.sm_action.configure(
                    text=f"✓  Готово — Живых: {a}  Мертвых: {d}",
                    text_color=COLOR_ACCENT)
                self.logger.info(f"SMTP check done: alive={a}, dead={d}",
                                 source="smtp")
            self.parent.after(0, _f)

        self.smtp_mgr.check_all(
            proxy_getter=proxy_getter,
            max_workers=15,
            on_progress=on_prog,
            on_done=on_done,
        )

    def _on_sm_test_single(self, acc: SmtpAccount) -> None:
        """Тест-логин одного аккаунта в фоне."""
        card = self._smtp_card_map.get(id(acc))
        if not card:
            return
        card["test_btn"].configure(state="disabled", text="…")

        def _do() -> None:
            proxy = self.proxy_mgr.get_next()
            self.smtp_mgr.check_single(acc, proxy=proxy)
            if acc.status == SmtpStatus.ALIVE:
                self.logger.success(f"SMTP login OK: {acc.email}",
                                    source="smtp", host=acc.display_host)
            else:
                self.logger.auth_error(f"SMTP login fail: {acc.email}: {acc.last_error}",
                                       source="smtp", host=acc.display_host)
            
            def _ui_update():
                self._sm_update_card(acc)
                self._sm_update_stats()
                if card["test_btn"].winfo_exists():
                    card["test_btn"].configure(state="normal", text="Тест")
            
            self.parent.after(0, _ui_update)

        threading.Thread(target=_do, daemon=True).start()

    def _on_sm_remove_dead(self) -> None:
        n = self.smtp_mgr.remove_dead()
        self._sm_page = 0
        self._sm_refresh()
        self.sm_action.configure(text=f"✓  Удалено {n} мертвых", text_color=COLOR_ACCENT)

    def _on_sm_clear(self) -> None:
        self.smtp_mgr.clear()
        self._sm_page = 0
        self._sm_refresh()
        self.sm_action.configure(text="🧹  Очищено", text_color=COLOR_TEXT_DIM)

    def _on_sm_copy(self) -> None:
        lines = []
        for a in self.smtp_mgr.accounts:
            line = f"{a.host}:{a.port}:{a.email}:{a.password}"
            if a.status.name != "UNTESTED" or a.last_error:
                line += f" | {a.status.value}"
                if a.last_error:
                    err = a.last_error.replace('\n', ' ').replace('\r', '')
                    line += f" | {err}"
            lines.append(line)
        text = "\n".join(lines)
        if text:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(text)

    # ── SMTP helpers ─────────────────────────────────────

    def _sm_page_prev(self) -> None:
        if self._sm_page > 0:
            self._sm_page -= 1
            self._sm_refresh()

    def _sm_page_next(self) -> None:
        total_pages = max(1, (self.smtp_mgr.count_total + self._items_per_page - 1) // self._items_per_page)
        if self._sm_page < total_pages - 1:
            self._sm_page += 1
            self._sm_refresh()

    def _sm_refresh(self) -> None:
        """Пересоздаёт карточки SMTP-аккаунтов."""
        for data in self._smtp_card_map.values():
            data["card"].destroy()
        self._smtp_card_map.clear()

        start = self._sm_page * self._items_per_page
        end = start + self._items_per_page
        page_items = self.smtp_mgr.accounts[start:end]

        for acc in page_items:
            self._sm_create_card(acc)
            
        total_pages = max(1, (self.smtp_mgr.count_total + self._items_per_page - 1) // self._items_per_page)
        
        if total_pages <= 1:
            self.sm_page_frame.pack_forget()
        else:
            self.sm_page_frame.pack(fill="x", padx=16, pady=(0, 14))
            
        self.lbl_sm_page.configure(text=f"Стр. {self._sm_page + 1} из {total_pages}")
        self.btn_sm_prev.configure(state="normal" if self._sm_page > 0 else "disabled")
        self.btn_sm_next.configure(state="normal" if self._sm_page < total_pages - 1 else "disabled")
        
        self.sm_list._parent_canvas.yview_moveto(0)
        self._sm_update_stats()

    def _sm_create_card(self, acc: SmtpAccount) -> None:
        """Создаёт одну карточку аккаунта внутри sm_list."""
        card = ctk.CTkFrame(
            self.sm_list, fg_color=COLOR_FRAME, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
        )
        card.pack(fill="x", padx=4, pady=3)

        # ── Верхняя строка: email + статус ────────────
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 2))

        email_lbl = ctk.CTkLabel(
            top, text=f"📧  {acc.email}",
            font=(FONT_FAMILY, 12, "bold"), text_color=COLOR_TEXT, anchor="w",
        )
        email_lbl.pack(side="left", fill="x", expand=True)

        status_lbl = ctk.CTkLabel(
            top, text=f"●  {acc.status.value}",
            font=(FONT_FAMILY, 11), text_color=self._sm_color(acc.status),
            anchor="e",
        )
        status_lbl.pack(side="right")

        # ── Средняя строка: host + encryption + sent ──
        mid = ctk.CTkFrame(card, fg_color="transparent")
        mid.pack(fill="x", padx=10, pady=1)

        ping_str = f" {acc.ping_ms}ms" if getattr(acc, "ping_ms", 0) else ""
        host_lbl = ctk.CTkLabel(
            mid, text=f"{acc.display_host}  [{acc.encryption}]{ping_str}",
            font=(FONT_MONO, 11), text_color=COLOR_TEXT_DIM, anchor="w",
        )
        host_lbl.pack(side="left")

        sent_lbl = ctk.CTkLabel(
            mid, text=f"Отправлено: {acc.sent_count}",
            font=(FONT_MONO, 11), text_color=COLOR_TEXT_DIM, anchor="e",
        )
        sent_lbl.pack(side="right")

        # ── Нижняя строка: test + error ───────────────
        bot = ctk.CTkFrame(card, fg_color="transparent")
        bot.pack(fill="x", padx=10, pady=(2, 8))

        test_btn = ctk.CTkButton(
            bot, text="Тест", width=65, height=24,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_ACCENT, font=(FONT_FAMILY, 11),
            corner_radius=6, command=lambda a=acc: self._on_sm_test_single(a),
        )
        test_btn.pack(side="left", padx=(0, 8))

        error_lbl = ctk.CTkLabel(
            bot, text=acc.last_error or "",
            font=(FONT_FAMILY, 10), text_color=COLOR_ERROR, anchor="w",
            wraplength=250,
        )
        error_lbl.pack(side="left", fill="x", expand=True)

        self._smtp_card_map[id(acc)] = {
            "card": card,
            "email_lbl": email_lbl,
            "status_lbl": status_lbl,
            "host_lbl": host_lbl,
            "sent_lbl": sent_lbl,
            "test_btn": test_btn,
            "error_lbl": error_lbl,
        }

    def _sm_update_card(self, acc: SmtpAccount) -> None:
        """Обновляет визуал одной карточки по текущему состоянию аккаунта."""
        data = self._smtp_card_map.get(id(acc))
        if not data:
            return
        color = self._sm_color(acc.status)
        data["status_lbl"].configure(text=f"●  {acc.status.value}", text_color=color)
        data["sent_lbl"].configure(text=f"Отправлено: {acc.sent_count}")
        data["error_lbl"].configure(text=acc.last_error or "")
        ping_str = f" {acc.ping_ms}ms" if getattr(acc, "ping_ms", 0) else ""
        data["host_lbl"].configure(text=f"{acc.display_host}  [{acc.encryption}]{ping_str}")

    def _sm_update_stats(self) -> None:
        t = self.smtp_mgr.count_total
        a = self.smtp_mgr.count_alive
        d = self.smtp_mgr.count_dead
        self.sm_stats.configure(text=f"Всего: {t}  ·  Живых: {a}  ·  Мертвых: {d}")

    @staticmethod
    def _sm_color(status: SmtpStatus) -> str:
        if status == SmtpStatus.ALIVE:
            return COLOR_ACCENT
        if status == SmtpStatus.DEAD:
            return COLOR_ERROR
        return COLOR_TEXT_DIM

    def _sm_set_state(self, state: str) -> None:
        for w in (self.btn_sm_file, self.btn_sm_clear, self.btn_sm_dead):
            w.configure(state=state)
        if state == "normal" and not self._smtp_checking:
            self.btn_sm_check.configure(state="normal")

    # ══════════════════════════════════════════════════════
    #  UI LOCKING
    # ══════════════════════════════════════════════════════
    def set_ui_locked(self, locked: bool) -> None:
        px_state = "disabled" if (locked or self._proxy_checking) else "normal"
        self.btn_px_file.configure(state=px_state)
        self.px_url_entry.configure(state=px_state)
        self.btn_px_url.configure(state=px_state)
        self.btn_px_check.configure(state=px_state)
        self.btn_px_dead.configure(state=px_state)
        self.btn_px_clear.configure(state=px_state)
        self.btn_px_copy.configure(state=px_state)
        self.btn_px_prev.configure(state="disabled" if (locked or self._proxy_checking or self._px_page <= 0) else "normal")
        total_pages = max(1, (self.proxy_mgr.count_total + self._items_per_page - 1) // self._items_per_page)
        self.btn_px_next.configure(state="disabled" if (locked or self._proxy_checking or self._px_page >= total_pages - 1) else "normal")
        self.px_auto_cb.configure(state=px_state)
        self.px_auto_min.configure(state=px_state)

        sm_state = "disabled" if (locked or self._smtp_checking) else "normal"
        self.btn_sm_file.configure(state=sm_state)
        self.btn_sm_check.configure(state=sm_state)
        self.btn_sm_dead.configure(state=sm_state)
        self.btn_sm_clear.configure(state=sm_state)
        self.btn_sm_copy.configure(state=sm_state)
        self.btn_sm_prev.configure(state="disabled" if (locked or self._smtp_checking or self._sm_page <= 0) else "normal")
        total_sm_pages = max(1, (self.smtp_mgr.count_total + self._items_per_page - 1) // self._items_per_page)
        self.btn_sm_next.configure(state="disabled" if (locked or self._smtp_checking or self._sm_page >= total_sm_pages - 1) else "normal")

    # ══════════════════════════════════════════════════════
    #  ПРОКСИ (Логика)
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _btn(
        parent,
        text: str,
        command,
        w: int = 100,
        text_color: str = COLOR_TEXT,
    ) -> ctk.CTkButton:
        """Фабрика кнопок в едином стиле."""
        return ctk.CTkButton(
            parent, text=text, width=w, height=30,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=text_color, font=(FONT_FAMILY, 12),
            corner_radius=8, command=command,
        )
