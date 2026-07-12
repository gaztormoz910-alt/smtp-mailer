"""Вкладка Campaign — база получателей, control inject, CC/BCC, пресеты.

Загрузка CSV/TXT, превью, контрольные адреса, CC/BCC,
сохранение/загрузка пресетов.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from core.logger import JsonLogger
from core.presets import save_preset, load_preset
from core.queue_manager import Recipient, build_queue, load_recipients
from core.sender import clear_queue_state
from gui.theme import (
    COLOR_ACCENT, COLOR_ACCENT_HVR, COLOR_BG, COLOR_BORDER,
    COLOR_BTN, COLOR_BTN_HVR, COLOR_ERROR, COLOR_FRAME,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_WARN,
    FONT_FAMILY, FONT_MONO,
)


class CampaignTab:
    """Содержимое вкладки Campaign."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        on_queue_ready: Callable[[list[Recipient]], None] | None = None,
    ) -> None:
        self.parent = parent
        self.logger = JsonLogger()
        self.on_queue_ready = on_queue_ready

        self._recipients: list[Recipient] = []
        self._recipients_file: str = ""
        self._db_page = 0
        self._items_per_page = 40

        self._build_layout()

    # ══════════════════════════════════════════════════════
    #  LAYOUT
    # ══════════════════════════════════════════════════════

    def _build_layout(self) -> None:
        outer = ctk.CTkFrame(self.parent, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=3)   # recipients
        outer.grid_rowconfigure(1, weight=0)   # CC/BCC
        outer.grid_rowconfigure(2, weight=1)   # control + presets

        self._build_recipients(outer)
        self._build_ccbcc(outer)
        self._build_bottom(outer)

    # ── Recipients ───────────────────────────────────────

    def _build_recipients(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            frame, text="📋  База получателей",
            font=(FONT_FAMILY, 14, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            frame, text=".txt (email по одному на строку) или .csv (колонки: email, name)",
            font=(FONT_MONO, 8), text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 2))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 4))

        self.btn_db_load = ctk.CTkButton(
            row, text="📁  Загрузить получателей", width=155, height=28,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_ACCENT, font=(FONT_FAMILY, 12, "bold"),
            border_color=COLOR_ACCENT, border_width=1, corner_radius=8,
            command=self._on_load,
        )
        self.btn_db_load.pack(side="left", padx=(0, 6))

        self.btn_db_clear = ctk.CTkButton(
            row, text="Очистить", width=50, height=28,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_TEXT_DIM, font=(FONT_FAMILY, 11),
            corner_radius=8, command=self._on_clear,
        )
        self.btn_db_clear.pack(side="left", padx=(0, 8))

        self.count_label = ctk.CTkLabel(
            row, text="0 получателей", font=(FONT_MONO, 11),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.count_label.pack(side="left")

        # превью (заголовок)
        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(2, 0))
        ctk.CTkLabel(hdr, text="Email", width=260, font=(FONT_MONO, 10, "bold"),
                     text_color=COLOR_TEXT_DIM, anchor="w").pack(side="left")
        ctk.CTkLabel(hdr, text="Имя", width=160, font=(FONT_MONO, 10, "bold"),
                     text_color=COLOR_TEXT_DIM, anchor="w").pack(side="left")

        self.preview_list = ctk.CTkScrollableFrame(
            frame, fg_color=COLOR_BG, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
            scrollbar_fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_TEXT_DIM
        )
        self.preview_list.pack(fill="both", expand=True, padx=14, pady=(1, 4))

        # ── Пагинация БД ─────────────────────────────
        self.db_page_frame = ctk.CTkFrame(frame, fg_color="transparent")

        self.btn_db_prev = ctk.CTkButton(
            self.db_page_frame, text="< Назад", width=70, height=24,
            command=self._db_page_prev, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR, text_color=COLOR_TEXT
        )
        self.btn_db_prev.pack(side="left")

        self.lbl_db_page = ctk.CTkLabel(
            self.db_page_frame, text="Стр. 1 из 1", font=(FONT_FAMILY, 11), text_color=COLOR_TEXT
        )
        self.lbl_db_page.pack(side="left", expand=True)

        self.btn_db_next = ctk.CTkButton(
            self.db_page_frame, text="Вперед >", width=70, height=24,
            command=self._db_page_next, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR, text_color=COLOR_TEXT
        )
        self.btn_db_next.pack(side="right")

        self.action_label = ctk.CTkLabel(
            frame, text="", font=(FONT_FAMILY, 10),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.action_label.pack(fill="x", padx=14, pady=(0, 6))

    # ── CC / BCC ─────────────────────────────────────────

    def _build_ccbcc(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        ctk.CTkLabel(
            frame, text="📬  Копии (CC / BCC)",
            font=(FONT_FAMILY, 14, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 4))

        # CC row
        cc_row = ctk.CTkFrame(frame, fg_color="transparent")
        cc_row.pack(fill="x", padx=14, pady=(0, 3))

        ctk.CTkLabel(cc_row, text="CC:", width=30, font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left")
        self.cc_entry = ctk.CTkEntry(
            cc_row, height=26, placeholder_text="cc1@mail.com, cc2@mail.com",
            font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER, corner_radius=6,
        )
        self.cc_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))

        ctk.CTkLabel(cc_row, text="%:", font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left")
        self.cc_pct = ctk.CTkEntry(
            cc_row, width=42, height=26, placeholder_text="0",
            font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER,
            corner_radius=6, justify="center",
        )
        self.cc_pct.pack(side="left", padx=(4, 0))
        self.cc_pct.insert(0, "0")

        # BCC row
        bcc_row = ctk.CTkFrame(frame, fg_color="transparent")
        bcc_row.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(bcc_row, text="BCC:", width=30, font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left")
        self.bcc_entry = ctk.CTkEntry(
            bcc_row, height=26, placeholder_text="bcc@hidden.com",
            font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER, corner_radius=6,
        )
        self.bcc_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))

        ctk.CTkLabel(bcc_row, text="%:", font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left")
        self.bcc_pct = ctk.CTkEntry(
            bcc_row, width=42, height=26, placeholder_text="0",
            font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER,
            corner_radius=6, justify="center",
        )
        self.bcc_pct.pack(side="left", padx=(4, 0))
        self.bcc_pct.insert(0, "0")

    # ── Bottom: Control Inject + Presets ──────────────────

    def _build_bottom(self, container: ctk.CTkFrame) -> None:
        wrap = ctk.CTkFrame(container, fg_color="transparent")
        wrap.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        wrap.grid_columnconfigure(0, weight=3)
        wrap.grid_columnconfigure(1, weight=2)
        wrap.grid_rowconfigure(0, weight=1)

        self._build_control(wrap)
        self._build_presets(wrap)

    def _build_control(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=(4, 8))

        ctk.CTkLabel(
            frame, text="🎯  Контрольные адреса (Control Inject)",
            font=(FONT_FAMILY, 13, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        r1 = ctk.CTkFrame(frame, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(0, 3))
        ctk.CTkLabel(r1, text="Каждые:", font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 4))
        self.inject_n_entry = ctk.CTkEntry(
            r1, width=50, height=26, font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER,
            corner_radius=6, justify="center",
        )
        self.inject_n_entry.pack(side="left", padx=(0, 4))
        self.inject_n_entry.insert(0, "100")
        ctk.CTkLabel(r1, text="писем (0=выкл)", font=(FONT_FAMILY, 10),
                     text_color=COLOR_TEXT_DIM).pack(side="left")

        r2 = ctk.CTkFrame(frame, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=(0, 3))
        ctk.CTkLabel(r2, text="Адреса:", font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 4))
        self.ctrl_emails_entry = ctk.CTkEntry(
            r2, height=26, placeholder_text="ctrl1@gmail.com, ctrl2@yahoo.com",
            font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER, corner_radius=6,
        )
        self.ctrl_emails_entry.pack(side="left", fill="x", expand=True)

        r3 = ctk.CTkFrame(frame, fg_color="transparent")
        r3.pack(fill="x", padx=12, pady=(4, 8))
        self.btn_queue = ctk.CTkButton(
            r3, text="🔄 Создать очередь", width=120, height=26,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_WARN, font=(FONT_FAMILY, 11, "bold"),
            border_color=COLOR_WARN, border_width=1, corner_radius=8,
            command=self._on_build_queue,
        )
        self.btn_queue.pack(side="left", padx=(0, 8))

        self.queue_label = ctk.CTkLabel(
            r3, text="", font=(FONT_FAMILY, 10),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.queue_label.pack(side="left", fill="x")

    def _build_presets(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=(4, 8))

        ctk.CTkLabel(
            frame, text="⚙  Пресеты",
            font=(FONT_FAMILY, 13, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 8))

        self.btn_preset_save = ctk.CTkButton(
            frame, text="💾  Сохранить пресет", width=150, height=32,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_ACCENT, font=(FONT_FAMILY, 13, "bold"),
            border_color=COLOR_ACCENT, border_width=1, corner_radius=8,
            command=self._on_save_preset,
        )
        self.btn_preset_save.pack(padx=12, pady=(0, 6))

        self.btn_preset_load = ctk.CTkButton(
            frame, text="📂  Загрузить пресет", width=150, height=32,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_WARN, font=(FONT_FAMILY, 13, "bold"),
            border_color=COLOR_WARN, border_width=1, corner_radius=8,
            command=self._on_load_preset,
        )
        self.btn_preset_load.pack(padx=12, pady=(0, 6))

        self.preset_label = ctk.CTkLabel(
            frame, text="", font=(FONT_FAMILY, 10),
            text_color=COLOR_TEXT_DIM, anchor="w", wraplength=180,
        )
        self.preset_label.pack(fill="x", padx=12, pady=(0, 8))

    # ══════════════════════════════════════════════════════
    #  HANDLERS — Recipients
    # ══════════════════════════════════════════════════════

    def _on_load(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите файлы получателей",
            filetypes=[("CSV / TXT", "*.csv *.txt"), ("All", "*.*")],
        )
        if not paths:
            return
        
        def _do() -> None:
            try:
                all_recs = []
                for p in paths:
                    all_recs.extend(load_recipients(p))
                self.logger.info(f"Loaded {len(all_recs)} recipients from {len(paths)} files",
                                 source="campaign")
                disp_path = f"{len(paths)} файлов" if len(paths) > 1 else Path(paths[0]).name
                self.parent.after(0, lambda: self._load_done(all_recs, disp_path))
            except Exception as e:
                self.parent.after(0, lambda: self.action_label.configure(
                    text=f"✗  {e}", text_color=COLOR_ERROR))
        threading.Thread(target=_do, daemon=True).start()

    def _load_done(self, recs: list[Recipient], path: str) -> None:
        self._recipients.extend(recs)
        # Keep track of all loaded files in a list if needed, or just append the name to _recipients_file
        if self._recipients_file:
            self._recipients_file += f"; {path}"
        else:
            self._recipients_file = path
        self.count_label.configure(text=f"{len(self._recipients)} получателей")
        self._db_page = 0
        self._refresh_preview()
        clear_queue_state()
        self.action_label.configure(
            text=f"✓  Добавлено {len(recs)} из {Path(path).name} (Всего: {len(self._recipients)})",
            text_color=COLOR_ACCENT)
        self._on_build_queue()

    def _on_clear(self) -> None:
        self._recipients.clear()
        self._recipients_file = ""
        self.count_label.configure(text="0 получателей")
        self._db_page = 0
        self._refresh_preview()
        self.action_label.configure(text="✓  Очищено", text_color=COLOR_TEXT_DIM)
        self.queue_label.configure(text="")
        if self.on_queue_ready:
            self.on_queue_ready([])

    def _on_build_queue(self) -> None:
        if not self._recipients:
            self.queue_label.configure(text="✗  Сначала загрузите получателей", text_color=COLOR_ERROR)
            return

        ctrl_n = self._int(self.inject_n_entry, 0)
        ctrl_raw = self.ctrl_emails_entry.get().strip()
        ctrl_emails = [e.strip() for e in ctrl_raw.split(",")
                       if "@" in e.strip()] if ctrl_raw else []

        queue = build_queue(self._recipients, ctrl_emails, ctrl_n)
        ctrl_count = sum(1 for r in queue if r.is_control)
        regular_count = len(queue) - ctrl_count

        info = f"{regular_count} обычных"
        if ctrl_count:
            info += f" + {ctrl_count} контр."
        info += f" = {len(queue)}"
        self.queue_label.configure(text=f"✓  {info}", text_color=COLOR_ACCENT)

        if self.on_queue_ready:
            self.on_queue_ready(queue)

    # ══════════════════════════════════════════════════════
    #  HANDLERS — Presets
    # ══════════════════════════════════════════════════════

    def gather_preset(self) -> dict:
        """Собирает текущие настройки в dict для сохранения."""
        return {
            "recipients_file": self._recipients_file,
            "control_every_n": self._int(self.inject_n_entry, 0),
            "control_emails": self.ctrl_emails_entry.get().strip(),
            "cc_addrs": self.cc_entry.get().strip(),
            "cc_percent": self._int(self.cc_pct, 0),
            "bcc_addrs": self.bcc_entry.get().strip(),
            "bcc_percent": self._int(self.bcc_pct, 0),
        }

    def apply_preset(self, data: dict) -> list[str]:
        """Применяет настройки из dict. Возвращает список предупреждений."""
        warnings: list[str] = []

        # Control inject
        self._set_entry(self.inject_n_entry, str(data.get("control_every_n", 100)))
        self._set_entry(self.ctrl_emails_entry, data.get("control_emails", ""))

        # CC/BCC
        self._set_entry(self.cc_entry, data.get("cc_addrs", ""))
        self._set_entry(self.cc_pct, str(data.get("cc_percent", 0)))
        self._set_entry(self.bcc_entry, data.get("bcc_addrs", ""))
        self._set_entry(self.bcc_pct, str(data.get("bcc_percent", 0)))

        # Recipients
        rfile = data.get("recipients_file", "")
        if rfile:
            if Path(rfile).exists():
                self._load_done(load_recipients(rfile), Path(rfile).name)
            else:
                warnings.append(f"Recipients file not found: {rfile}")

        return warnings

    def _on_save_preset(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Сохранить пресет",
            defaultextension=".json",
            initialdir=str(Path(__file__).resolve().parent.parent / "data" / "presets"),
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        # Собираем из всех вкладок через App
        app = self._get_app()
        if app:
            data = app.gather_full_preset()
        else:
            data = self.gather_preset()
        try:
            save_preset(path, data)
            self.preset_label.configure(
                text=f"✓ Сохранено: {Path(path).name}", text_color=COLOR_ACCENT)
        except Exception as e:
            self.preset_label.configure(text=f"✗ {e}", text_color=COLOR_ERROR)

    def _on_load_preset(self) -> None:
        path = filedialog.askopenfilename(
            title="Загрузить пресет",
            initialdir=str(Path(__file__).resolve().parent.parent / "data" / "presets"),
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            data = load_preset(path)
            app = self._get_app()
            if app:
                warnings = app.apply_full_preset(data)
            else:
                warnings = self.apply_preset(data)
            if warnings:
                messagebox.showwarning(
                    "Предупреждения пресета",
                    "Некоторые файлы не найдены:\n\n" + "\n".join(warnings),
                )
            self.preset_label.configure(
                text=f"✓ Загружено: {Path(path).name}", text_color=COLOR_ACCENT)
        except Exception as e:
            self.preset_label.configure(text=f"✗ {e}", text_color=COLOR_ERROR)

    def _get_app(self):
        """Поднимается по виджетам до App."""
        w = self.parent
        while w:
            if hasattr(w, "gather_full_preset"):
                return w
            w = getattr(w, "master", None)
        return None

    # ══════════════════════════════════════════════════════
    #  CC/BCC  API (для Send-таба)
    # ══════════════════════════════════════════════════════

    def get_cc_config(self) -> tuple[list[str], int]:
        raw = self.cc_entry.get().strip()
        addrs = [e.strip() for e in raw.split(",") if "@" in e.strip()] if raw else []
        pct = self._int(self.cc_pct, 0)
        return addrs, pct

    def get_bcc_config(self) -> tuple[list[str], int]:
        raw = self.bcc_entry.get().strip()
        addrs = [e.strip() for e in raw.split(",") if "@" in e.strip()] if raw else []
        pct = self._int(self.bcc_pct, 0)
        return addrs, pct

    # ══════════════════════════════════════════════════════
    #  UI LOCKING
    # ══════════════════════════════════════════════════════

    def set_ui_locked(self, locked: bool) -> None:
        state = "disabled" if locked else "normal"
        self.btn_db_load.configure(state=state)
        self.btn_db_clear.configure(state=state)
        
        # Disable pagination unless we have pages and are not locked
        self.btn_db_prev.configure(state="disabled" if (locked or self._db_page <= 0) else "normal")
        total_pages = max(1, (len(self._recipients) + self._items_per_page - 1) // self._items_per_page)
        self.btn_db_next.configure(state="disabled" if (locked or self._db_page >= total_pages - 1) else "normal")
        
        self.cc_entry.configure(state=state)
        self.cc_pct.configure(state=state)
        self.bcc_entry.configure(state=state)
        self.bcc_pct.configure(state=state)
        
        self.inject_n_entry.configure(state=state)
        self.ctrl_emails_entry.configure(state=state)
        self.btn_queue.configure(state=state)
        
        self.btn_preset_save.configure(state=state)
        self.btn_preset_load.configure(state=state)

    # ══════════════════════════════════════════════════════
    #  HANDLERS
    # ══════════════════════════════════════════════════════

    def _db_page_prev(self) -> None:
        if self._db_page > 0:
            self._db_page -= 1
            self._refresh_preview()

    def _db_page_next(self) -> None:
        total_pages = max(1, (len(self._recipients) + self._items_per_page - 1) // self._items_per_page)
        if self._db_page < total_pages - 1:
            self._db_page += 1
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        for w in self.preview_list.winfo_children():
            w.destroy()
            
        start = self._db_page * self._items_per_page
        end = start + self._items_per_page
        page_items = self._recipients[start:end]
            
        for r in page_items:
            row = ctk.CTkFrame(self.preview_list, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=1)
            ctk.CTkLabel(row, text=r.email, width=260, font=(FONT_MONO, 10),
                         text_color=COLOR_TEXT, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=r.name or "—", width=160, font=(FONT_MONO, 10),
                         text_color=COLOR_TEXT_DIM, anchor="w").pack(side="left")
                         
        total_pages = max(1, (len(self._recipients) + self._items_per_page - 1) // self._items_per_page)
        
        if total_pages <= 1:
            self.db_page_frame.pack_forget()
        else:
            self.db_page_frame.pack(fill="x", padx=14, pady=(0, 4), before=self.action_label)
            
        self.lbl_db_page.configure(text=f"Стр. {self._db_page + 1} из {total_pages}")
        
        self.btn_db_prev.configure(state="normal" if self._db_page > 0 else "disabled")
        self.btn_db_next.configure(state="normal" if self._db_page < total_pages - 1 else "disabled")
        
        self.preview_list._parent_canvas.yview_moveto(0)

    @staticmethod
    def _int(entry: ctk.CTkEntry, default: int) -> int:
        try:
            return max(0, int(entry.get().strip()))
        except (ValueError, AttributeError):
            return default

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)
