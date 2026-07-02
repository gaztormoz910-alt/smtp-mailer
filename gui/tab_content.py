"""Вкладка Content — темы, тела, ссылки, имена отправителей.

Layout (2×2 + sandbox):
  ┌─ Subjects ─┐  ┌─ Bodies ──┐
  ├─ Links ────┤  ├─ Senders ─┤
  └─ Sandbox (full width) ────┘
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.content import ContentManager
from core.logger import JsonLogger
from gui.theme import (
    COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_BTN, COLOR_BTN_HVR,
    COLOR_ERROR, COLOR_FRAME, COLOR_TEXT, COLOR_TEXT_DIM, COLOR_WARN,
    FONT_FAMILY, FONT_MONO,
)


class ContentTab:
    """Содержимое вкладки Content."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        content_mgr: ContentManager | None = None,
    ) -> None:
        self.parent = parent
        self.content_mgr = content_mgr or ContentManager()
        self.logger = JsonLogger()

        # Трекинг файлов (для пресетов)
        self._subjects_file: str = ""
        self._bodies_file: str = ""
        self._senders_file: str = ""
        self._link_file_paths: list[str] = []

        self._build_layout()

    # ══════════════════════════════════════════════════════
    #  LAYOUT
    # ══════════════════════════════════════════════════════


    def _copy_text(self, tb) -> None:
        text = tb.get("1.0", "end-1c")
        if text:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(text)

    def _build_layout(self) -> None:
        outer = ctk.CTkFrame(self.parent, fg_color="transparent")
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=3)   # 2×2 grid
        outer.grid_rowconfigure(1, weight=2)   # sandbox

        # ── Top 2×2 ────────────────────────────────────
        top = ctk.CTkFrame(outer, fg_color="transparent")
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_columnconfigure(0, weight=1, uniform="col")
        top.grid_columnconfigure(1, weight=1, uniform="col")
        top.grid_rowconfigure(0, weight=1, uniform="row")
        top.grid_rowconfigure(1, weight=1, uniform="row")

        self._build_subjects(top, 0, 0)
        self._build_bodies(top, 0, 1)
        self._build_links(top, 1, 0)
        self._build_senders(top, 1, 1)

        # ── Sandbox (full width) ──────────────────────
        self._build_sandbox(outer)

    # ══════════════════════════════════════════════════════
    #  SUBJECTS  (0,0)
    # ══════════════════════════════════════════════════════

    def _build_subjects(self, c: ctk.CTkFrame, r: int, col: int) -> None:
        f = self._frame(c, r, col, pad_right=(r == 0 and col == 0))
        ctk.CTkLabel(f, text="📝  Темы (Subjects)", font=(FONT_FAMILY, 13, "bold"),
                     text_color=COLOR_TEXT, anchor="w").pack(fill="x", padx=12, pady=(10, 4))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 3))
        self._btn(row, "Загрузить", self._on_load_subjects, 80).pack(side="left", padx=(0, 4))
        self._btn(row, "Очистить", self._on_clear_subjects, 48, COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))
        self.subj_counter = ctk.CTkLabel(row, text="0 загружено", font=(FONT_MONO, 10),
                                         text_color=COLOR_TEXT_DIM, anchor="w")
        self.subj_counter.pack(side="left")
        self._btn(row, "Копировать", lambda: self._copy_text(self.subj_preview), 80, COLOR_TEXT_DIM).pack(side="right")

        self.subj_preview = self._textbox(f, h=50)
        self.subj_preview.pack(fill="both", expand=True, padx=12, pady=(0, 3))
        self.subj_action = self._status(f)

    # ══════════════════════════════════════════════════════
    #  BODIES  (0,1)
    # ══════════════════════════════════════════════════════

    def _build_bodies(self, c: ctk.CTkFrame, r: int, col: int) -> None:
        f = self._frame(c, r, col)
        ctk.CTkLabel(f, text="📄  Тексты писем", font=(FONT_FAMILY, 13, "bold"),
                     text_color=COLOR_TEXT, anchor="w").pack(fill="x", padx=12, pady=(10, 4))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 3))
        self._btn(row, "Загрузить", self._on_load_bodies, 80).pack(side="left", padx=(0, 4))
        self._btn(row, "Очистить", self._on_clear_bodies, 48, COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))
        self.body_counter = ctk.CTkLabel(row, text="0 загружено", font=(FONT_MONO, 10),
                                         text_color=COLOR_TEXT_DIM, anchor="w")
        self.body_counter.pack(side="left")
        self._btn(row, "Копировать", lambda: self._copy_text(self.body_preview), 80, COLOR_TEXT_DIM).pack(side="right")

        self.body_preview = self._textbox(f, h=50)
        self.body_preview.pack(fill="both", expand=True, padx=12, pady=(0, 3))
        self.body_action = self._status(f)

    # ══════════════════════════════════════════════════════
    #  LINKS  (1,0)
    # ══════════════════════════════════════════════════════

    def _build_links(self, c: ctk.CTkFrame, r: int, col: int) -> None:
        f = self._frame(c, r, col, pad_right=True)
        ctk.CTkLabel(f, text="🔗  Ссылки", font=(FONT_FAMILY, 13, "bold"),
                     text_color=COLOR_TEXT, anchor="w").pack(fill="x", padx=12, pady=(10, 4))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 3))
        self._btn(row, "Загрузить", self._on_load_links, 80).pack(side="left", padx=(0, 4))
        self._btn(row, "Очистить", self._on_clear_links, 48, COLOR_TEXT_DIM).pack(side="left")
        
        self.btn_link_copy = self._btn(row, "Копировать", self._on_copy_links, 80, COLOR_TEXT_DIM)
        self.btn_link_copy.pack(side="right")

        self.consistent_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            f, text="Единые ссылки для каждого письма",
            variable=self.consistent_var, font=(FONT_FAMILY, 10),
            text_color=COLOR_TEXT_DIM, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            checkmark_color=COLOR_ACCENT, border_color=COLOR_BORDER,
            corner_radius=4, width=18, command=self._on_consistent_toggle,
        ).pack(fill="x", padx=12, pady=(2, 3))

        self.link_list = ctk.CTkScrollableFrame(
            f, fg_color=COLOR_BG, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
        )
        self.link_list.pack(fill="both", expand=True, padx=12, pady=(0, 3))
        self.link_action = self._status(f)

    # ══════════════════════════════════════════════════════
    #  SENDERS  (1,1)
    # ══════════════════════════════════════════════════════

    def _build_senders(self, c: ctk.CTkFrame, r: int, col: int) -> None:
        f = self._frame(c, r, col)
        ctk.CTkLabel(f, text="👤  Имена отправителей", font=(FONT_FAMILY, 13, "bold"),
                     text_color=COLOR_TEXT, anchor="w").pack(fill="x", padx=12, pady=(10, 4))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 3))
        self._btn(row, "Загрузить", self._on_load_senders, 80).pack(side="left", padx=(0, 4))
        self._btn(row, "Очистить", self._on_clear_senders, 48, COLOR_TEXT_DIM).pack(side="left", padx=(0, 6))
        self.sender_counter = ctk.CTkLabel(row, text="0 загружено", font=(FONT_MONO, 10),
                                           text_color=COLOR_TEXT_DIM, anchor="w")
        self.sender_counter.pack(side="left")
        self._btn(row, "Копировать", lambda: self._copy_text(self.sender_preview), 80, COLOR_TEXT_DIM).pack(side="right")

        self.email_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            f, text="Только email (без имени отправителя)",
            variable=self.email_only_var, font=(FONT_FAMILY, 10),
            text_color=COLOR_TEXT_DIM, fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            checkmark_color=COLOR_ACCENT, border_color=COLOR_BORDER,
            corner_radius=4, width=18, command=self._on_email_only_toggle,
        ).pack(fill="x", padx=12, pady=(2, 3))

        self.sender_preview = self._textbox(f, h=40)
        self.sender_preview.pack(fill="both", expand=True, padx=12, pady=(0, 3))
        self.sender_action = self._status(f)

    # ══════════════════════════════════════════════════════
    #  SANDBOX
    # ══════════════════════════════════════════════════════

    def _build_sandbox(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

        ctk.CTkLabel(
            frame, text="🎲  Песочница — Предпросмотр",
            font=(FONT_FAMILY, 13, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        fields = ctk.CTkFrame(frame, fg_color="transparent")
        fields.pack(fill="x", padx=12, pady=(0, 5))

        self._flbl(fields, "Email:").pack(side="left")
        self.test_email = self._ent(fields, "user@example.com", 130)
        self.test_email.pack(side="left", padx=(4, 10))
        self._flbl(fields, "Имя:").pack(side="left")
        self.test_name = self._ent(fields, "John", 100)
        self.test_name.pack(side="left", padx=(4, 14))

        self.btn_generate = ctk.CTkButton(
            fields, text="🎲  Сгенерировать", width=120, height=26,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_WARN, font=(FONT_FAMILY, 12, "bold"),
            border_color=COLOR_WARN, border_width=2, corner_radius=8,
            command=self._on_generate,
        )
        self.btn_generate.pack(side="right")
        self._btn(fields, "Копировать", lambda: self._copy_text(self.sandbox_out), 80, COLOR_TEXT_DIM).pack(side="right", padx=(0, 8))

        self.sandbox_out = ctk.CTkTextbox(
            frame, fg_color=COLOR_BG,
            text_color=COLOR_ACCENT, font=(FONT_MONO, 11),
            corner_radius=8, border_color=COLOR_BORDER, border_width=1,
            state="disabled", wrap="word",
        )
        self.sandbox_out.pack(fill="both", expand=True, padx=12, pady=(0, 5))
        self.sandbox_action = self._status(frame)

    # ══════════════════════════════════════════════════════
    #  HANDLERS — SUBJECTS
    # ══════════════════════════════════════════════════════

    def _on_load_subjects(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл с темами",
            filetypes=[("Text files", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return

        def _do() -> None:
            try:
                count = self.content_mgr.load_subjects(path)
                self._subjects_file = path
                self.logger.info(f"Loaded {count} subjects", source="content", file=str(path))
                self.parent.after(0, lambda: self._subj_done(count))
            except Exception as e:
                self.parent.after(0, lambda: self.subj_action.configure(
                    text=f"✗  {e}", text_color=COLOR_ERROR))
        threading.Thread(target=_do, daemon=True).start()

    def _subj_done(self, count: int) -> None:
        self.subj_counter.configure(text=f"{count} загружено")
        lines = self.content_mgr.subjects[:5]
        self._set_tb(self.subj_preview, "\n".join(lines) if lines else "(пусто)")
        self.subj_action.configure(text=f"✓  {count} тем", text_color=COLOR_ACCENT)

    def _on_clear_subjects(self) -> None:
        self.content_mgr.clear_subjects()
        self.subj_counter.configure(text="0 загружено")
        self._set_tb(self.subj_preview, "")
        self.subj_action.configure(text="✓  Очищено", text_color=COLOR_TEXT_DIM)

    # ══════════════════════════════════════════════════════
    #  HANDLERS — BODIES
    # ══════════════════════════════════════════════════════

    def _on_load_bodies(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл с текстами писем",
            filetypes=[("Text / HTML", "*.txt *.html"), ("All", "*.*")],
        )
        if not path:
            return

        def _do() -> None:
            try:
                count = self.content_mgr.load_bodies(path)
                self._bodies_file = path
                self.logger.info(f"Loaded {count} bodies", source="content", file=str(path))
                self.parent.after(0, lambda: self._body_done(count))
            except Exception as e:
                self.parent.after(0, lambda: self.body_action.configure(
                    text=f"✗  {e}", text_color=COLOR_ERROR))
        threading.Thread(target=_do, daemon=True).start()

    def _body_done(self, count: int) -> None:
        self.body_counter.configure(text=f"{count} загружено")
        bodies = self.content_mgr.bodies
        if bodies:
            first_lines = bodies[0].splitlines()[:8]
            preview = "\n".join(first_lines)
            if len(bodies[0].splitlines()) > 8:
                preview += "\n  …"
        else:
            preview = "(пусто)"
        self._set_tb(self.body_preview, preview)
        self.body_action.configure(text=f"✓  {count} писем", text_color=COLOR_ACCENT)

    def _on_clear_bodies(self) -> None:
        self.content_mgr.clear_bodies()
        self.body_counter.configure(text="0 загружено")
        self._set_tb(self.body_preview, "")
        self.body_action.configure(text="✓  Очищено", text_color=COLOR_TEXT_DIM)

    # ══════════════════════════════════════════════════════
    #  HANDLERS — LINKS
    # ══════════════════════════════════════════════════════

    def _on_load_links(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите файлы со ссылками",
            filetypes=[("Text files", "*.txt"), ("All", "*.*")],
        )
        if not paths:
            return

        def _do() -> None:
            loaded: list[str] = []
            for p in paths:
                try:
                    key, count = self.content_mgr.load_links_file(p)
                    if p not in self._link_file_paths:
                        self._link_file_paths.append(p)
                    macro = f"[[LINK{key}]]"
                    self.logger.info(f"Loaded {count} links → {macro}", source="content", file=str(p))
                    loaded.append(f"{Path(p).name}: {count} → {macro}")
                except Exception as e:
                    loaded.append(f"{Path(p).name}: error — {e}")
            self.parent.after(0, lambda: self._links_done(loaded))
        threading.Thread(target=_do, daemon=True).start()

    def _links_done(self, msgs: list[str]) -> None:
        self._refresh_link_list()
        self.link_action.configure(text=f"✓  {len(msgs)} файл(ов)", text_color=COLOR_ACCENT)

    def _on_clear_links(self) -> None:
        self.content_mgr.clear_links()
        self._refresh_link_list()
        self.link_action.configure(text="✓  Очищено", text_color=COLOR_TEXT_DIM)

    def _on_consistent_toggle(self) -> None:
        self.content_mgr.consistent_links = self.consistent_var.get()

    def _on_copy_links(self) -> None:
        links_data = []
        for filename, key, count in self.content_mgr.link_files:
            links_data.append(f"{filename}: {count} → [[LINK{key}]]")
        text = "\n".join(links_data)
        if text:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(text)
            self.link_action.configure(text="✓  Скопировано", text_color=COLOR_ACCENT)

    def _refresh_link_list(self) -> None:
        for w in self.link_list.winfo_children():
            w.destroy()
        for filename, key, count in self.content_mgr.link_files:
            macro = f"[[LINK{key}]]"
            text = f"  {filename}  {count} → {macro}"
            ctk.CTkLabel(self.link_list, text=text, font=(FONT_MONO, 10),
                         text_color=COLOR_TEXT_DIM, anchor="w", height=18).pack(fill="x", padx=4, pady=1)

    # ══════════════════════════════════════════════════════
    #  HANDLERS — SENDERS
    # ══════════════════════════════════════════════════════

    def _on_load_senders(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл имен отправителей",
            filetypes=[("Text files", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return

        def _do() -> None:
            try:
                count = self.content_mgr.load_sender_names(path)
                self._senders_file = path
                self.logger.info(f"Loaded {count} sender names", source="content", file=str(path))
                self.parent.after(0, lambda: self._senders_done(count))
            except Exception as e:
                self.parent.after(0, lambda: self.sender_action.configure(
                    text=f"✗  {e}", text_color=COLOR_ERROR))
        threading.Thread(target=_do, daemon=True).start()

    def _senders_done(self, count: int) -> None:
        self.sender_counter.configure(text=f"{count} загружено")
        names = self.content_mgr.sender_names[:5]
        self._set_tb(self.sender_preview, "\n".join(names) if names else "(пусто)")
        self.sender_action.configure(text=f"✓  {count} имен", text_color=COLOR_ACCENT)

    def _on_clear_senders(self) -> None:
        self.content_mgr.clear_sender_names()
        self.sender_counter.configure(text="0 загружено")
        self._set_tb(self.sender_preview, "")
        self.sender_action.configure(text="✓  Очищено", text_color=COLOR_TEXT_DIM)

    def _on_email_only_toggle(self) -> None:
        self.content_mgr.email_only = self.email_only_var.get()

    # ══════════════════════════════════════════════════════
    #  SANDBOX
    # ══════════════════════════════════════════════════════

    def _on_generate(self) -> None:
        has_subj = self.content_mgr.subject_count > 0
        has_body = self.content_mgr.body_count > 0
        if not has_subj and not has_body:
            self.sandbox_action.configure(text="✗  Сначала загрузите темы / тексты",
                                          text_color=COLOR_ERROR)
            return

        sender_name = self.content_mgr.get_random_sender_name()

        variables = {
            "email": self.test_email.get().strip() or "user@example.com",
            "name": self.test_name.get().strip() or "John",
            "senderName": sender_name,
        }
        cache = {} if self.content_mgr.consistent_links else None
        parts: list[str] = []

        try:
            # From
            from_info = f"Отправитель: {sender_name}" if sender_name else "Отправитель: (только email)"
            parts.append(from_info)

            if has_subj:
                subj = self.content_mgr.get_random_subject(variables, link_cache=cache)
                parts.append(f"Тема:  {subj}")
            else:
                parts.append("Тема:  (темы не загружены)")

            if has_body:
                body_text, html = self.content_mgr.get_random_body(variables, link_cache=cache)
                fmt = "HTML" if html else "Обычный текст"
                parts.append(f"Формат:   {fmt}")
                parts.append("─" * 55)
                parts.append(body_text)
            else:
                parts.append("Формат:   —")
                parts.append("─" * 55)
                parts.append("(тексты не загружены)")

        except ValueError as exc:
            self.sandbox_action.configure(text=f"✗  {exc}", text_color=COLOR_ERROR)
            self.logger.warning(str(exc), source="content")
            return

        self._set_tb(self.sandbox_out, "\n".join(parts))
        self.sandbox_action.configure(text="✓  Предпросмотр сгенерирован", text_color=COLOR_ACCENT)

    # ══════════════════════════════════════════════════════
    #  WIDGET FACTORIES
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _frame(parent, row, col, pad_right=False) -> ctk.CTkFrame:
        px = (8, 4) if pad_right else ((4, 8) if col == 1 else (8, 4))
        if col == 0 and row == 0:
            px = (8, 4)
        elif col == 1 and row == 0:
            px = (4, 8)
        elif col == 0:
            px = (8, 4)
        else:
            px = (4, 8)
        py = (8, 4) if row == 0 else (4, 4)
        f = ctk.CTkFrame(parent, fg_color=COLOR_FRAME, corner_radius=10,
                         border_color=COLOR_BORDER, border_width=1)
        f.grid(row=row, column=col, sticky="nsew", padx=px, pady=py)
        return f

    @staticmethod
    def _btn(parent, text, cmd, w=80, tc=COLOR_ACCENT) -> ctk.CTkButton:
        return ctk.CTkButton(parent, text=text, width=w, height=24,
                             fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
                             text_color=tc, font=(FONT_FAMILY, 11),
                             corner_radius=8, command=cmd)

    @staticmethod
    def _textbox(parent, h=50) -> ctk.CTkTextbox:
        return ctk.CTkTextbox(parent, height=h, fg_color=COLOR_BG,
                              text_color=COLOR_TEXT_DIM, font=(FONT_MONO, 10),
                              corner_radius=8, border_color=COLOR_BORDER,
                              border_width=1, state="disabled", wrap="word")

    @staticmethod
    def _status(parent) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(parent, text="", font=(FONT_FAMILY, 10),
                           text_color=COLOR_TEXT_DIM, anchor="w")
        lbl.pack(fill="x", padx=12, pady=(0, 6))
        return lbl

    @staticmethod
    def _flbl(parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(parent, text=text, font=(FONT_FAMILY, 11), text_color=COLOR_TEXT_DIM)

    @staticmethod
    def _ent(parent, ph: str, w: int = 130) -> ctk.CTkEntry:
        return ctk.CTkEntry(parent, width=w, height=24, placeholder_text=ph,
                            font=(FONT_FAMILY, 11), fg_color=COLOR_BG,
                            text_color=COLOR_TEXT, border_color=COLOR_BORDER, corner_radius=6)

    @staticmethod
    def _set_tb(tb: ctk.CTkTextbox, text: str) -> None:
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        tb.insert("1.0", text)
        tb.configure(state="disabled")
