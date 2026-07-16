"""Вкладка Stats — дашборд рассылки в реальном времени.

Прогресс-бар, глобальные метрики (скорость, ETA, sent, errors),
таблицы детализации по SMTP и прокси, экспорт логов.
UI обновляется через ``.after(1000)`` polling (потокобезопасно).
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.logger import JsonLogger
from core.stats import SendStats
from gui.theme import (
    COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_BTN, COLOR_BTN_HVR,
    COLOR_ERROR, COLOR_FRAME, COLOR_TEXT, COLOR_TEXT_DIM, COLOR_WARN,
    FONT_FAMILY, FONT_MONO,
)


class StatsTab:
    """Содержимое вкладки Stats."""

    def __init__(self, parent: ctk.CTkFrame, stats: SendStats | None = None) -> None:
        self.parent = parent
        self.stats = stats or SendStats()
        self.logger = JsonLogger()
        self._smtp_rows: dict[str, dict] = {}
        self._proxy_rows: dict[str, dict] = {}
        self._polling_active = False
        self._build_layout()

    # ══════════════════════════════════════════════════════
    #  LAYOUT
    # ══════════════════════════════════════════════════════

    def _build_layout(self) -> None:
        outer = ctk.CTkFrame(self.parent, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        self._build_progress(outer)
        self._build_metrics(outer)
        self._build_tables(outer)
        self._build_export(outer)

    # ── 1. Progress ──────────────────────────────────────

    def _build_progress(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.pack(fill="x", padx=8, pady=(8, 4))

        self.status_label = ctk.CTkLabel(
            frame, text="Ожидание",
            font=(FONT_FAMILY, 18, "bold"), text_color=COLOR_TEXT, anchor="w",
        )
        self.status_label.pack(fill="x", padx=16, pady=(14, 6))

        bar_row = ctk.CTkFrame(frame, fg_color="transparent")
        bar_row.pack(fill="x", padx=16, pady=(0, 14))

        self.progress_bar = ctk.CTkProgressBar(
            bar_row, height=16, corner_radius=8,
            fg_color=COLOR_BG, progress_color=COLOR_ACCENT,
            border_color=COLOR_BORDER, border_width=1,
        )
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)

        self.pct_label = ctk.CTkLabel(
            bar_row, text="0 %",
            font=(FONT_MONO, 13, "bold"), text_color=COLOR_ACCENT,
            width=55,
        )
        self.pct_label.pack(side="right")

    # ── 2. Metrics cards ─────────────────────────────────

    def _build_metrics(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.pack(fill="x", padx=8, pady=4)

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=10)

        for i in range(4):
            row.grid_columnconfigure(i, weight=1, uniform="metric")

        self.m_speed = self._metric_card(row, "⚡ Speed", "0 /мин", 0)
        self.m_eta   = self._metric_card(row, "⏱  ETA", "—", 1)
        self.m_sent  = self._metric_card(row, "✓  Sent", "0", 2, val_color=COLOR_ACCENT)
        self.m_err   = self._metric_card(row, "✗  Errors", "0", 3, val_color=COLOR_ERROR)

    def _metric_card(
        self, parent, title: str, value: str, col: int,
        val_color: str = COLOR_TEXT,
    ) -> ctk.CTkLabel:
        card = ctk.CTkFrame(
            parent, fg_color=COLOR_BG, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=4, pady=2)

        ctk.CTkLabel(
            card, text=title, font=(FONT_FAMILY, 11),
            text_color=COLOR_TEXT_DIM, anchor="center",
        ).pack(fill="x", padx=8, pady=(8, 2))

        lbl = ctk.CTkLabel(
            card, text=value,
            font=(FONT_MONO, 20, "bold"), text_color=val_color, anchor="center",
        )
        lbl.pack(fill="x", padx=8, pady=(0, 8))
        return lbl

    # ── 3. Detail tables (SMTP + Proxy) ──────────────────

    def _build_tables(self, container: ctk.CTkFrame) -> None:
        wrap = ctk.CTkFrame(container, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=8, pady=4)
        wrap.grid_columnconfigure(0, weight=1, uniform="tbl")
        wrap.grid_columnconfigure(1, weight=1, uniform="tbl")
        wrap.grid_rowconfigure(0, weight=1)

        # ── SMTP ─────────────────────────────────────
        smtp_frame = ctk.CTkFrame(
            wrap, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        smtp_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)

        ctk.CTkLabel(
            smtp_frame, text="📧  Аккаунты SMTP",
            font=(FONT_FAMILY, 13, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        # заголовок таблицы
        hdr = ctk.CTkFrame(smtp_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(0, 2))
        for txt, w in [("Email", 180), ("Отпр", 50), ("Ошиб", 45), ("Статус", 60)]:
            ctk.CTkLabel(
                hdr, text=txt, width=w, font=(FONT_MONO, 10, "bold"),
                text_color=COLOR_TEXT_DIM, anchor="w",
            ).pack(side="left")

        self.smtp_table = ctk.CTkScrollableFrame(
            smtp_frame, fg_color=COLOR_BG, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
        )
        self.smtp_table.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # ── Proxy ────────────────────────────────────
        proxy_frame = ctk.CTkFrame(
            wrap, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        proxy_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        ctk.CTkLabel(
            proxy_frame, text="🌐  Прокси",
            font=(FONT_FAMILY, 13, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        hdr2 = ctk.CTkFrame(proxy_frame, fg_color="transparent")
        hdr2.pack(fill="x", padx=12, pady=(0, 2))
        for txt, w in [("Адрес", 180), ("Исп", 50), ("Ошиб", 45), ("Статус", 60)]:
            ctk.CTkLabel(
                hdr2, text=txt, width=w, font=(FONT_MONO, 10, "bold"),
                text_color=COLOR_TEXT_DIM, anchor="w",
            ).pack(side="left")

        self.proxy_table = ctk.CTkScrollableFrame(
            proxy_frame, fg_color=COLOR_BG, corner_radius=8,
            border_color=COLOR_BORDER, border_width=1,
        )
        self.proxy_table.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    # ── 4. Export ────────────────────────────────────────

    def _build_export(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.pack(fill="x", padx=8, pady=(4, 8))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)

        ctk.CTkButton(
            row, text="📥  Экспорт JSON", width=130, height=30,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_ACCENT, font=(FONT_FAMILY, 12, "bold"),
            corner_radius=8, command=lambda: self._on_export("json"),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row, text="📥  Экспорт CSV", width=130, height=30,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_ACCENT, font=(FONT_FAMILY, 12, "bold"),
            corner_radius=8, command=lambda: self._on_export("csv"),
        ).pack(side="left", padx=(0, 12))

        self.export_action = ctk.CTkLabel(
            row, text="", font=(FONT_FAMILY, 11),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.export_action.pack(side="left", fill="x")

    # ══════════════════════════════════════════════════════
    #  POLLING  — потокобезопасное обновление UI
    # ══════════════════════════════════════════════════════

    def start_polling(self) -> None:
        """Запустить polling UI (вызывать при старте кампании)."""
        if not self._polling_active:
            self._polling_active = True
            self._update_ui()

    def stop_polling(self) -> None:
        """Остановить polling UI (вызывать при остановке кампании). Делает одно последнее обновление."""
        self._polling_active = False
        # Одно финальное обновление чтобы показать итоговый статус
        try:
            self._do_update_ui()
        except Exception:
            pass

    def _update_ui(self) -> None:
        """Раз в секунду читает snapshot из stats и обновляет виджеты."""
        if not self._polling_active:
            return
        self._do_update_ui()
        self.parent.after(1000, self._update_ui)

    def _do_update_ui(self) -> None:
        """Фактическое обновление виджетов."""
        snap = self.stats.snapshot

        # ── прогресс ──────────────────────────────────
        self.status_label.configure(text=snap["status_text"])
        pct = snap["progress"]
        self.progress_bar.set(min(pct, 1.0))
        self.pct_label.configure(text=f"{pct * 100:.1f} %")

        # ── метрики ───────────────────────────────────
        self.m_speed.configure(text=f"{snap['speed_per_min']} /мин")
        eta = snap["eta_min"]
        if eta > 0:
            if eta >= 60:
                eta_text = f"{eta / 60:.1f}h"
            else:
                eta_text = f"{eta:.0f}m"
        else:
            eta_text = "—"
        self.m_eta.configure(text=eta_text)
        self.m_sent.configure(text=str(snap["sent"]))
        self.m_err.configure(text=str(snap["errors"]))

        # ── SMTP-таблица ──────────────────────────────
        for item in snap["smtp"]:
            key = item["email"]
            if key not in self._smtp_rows:
                self._create_smtp_row(key)
            row = self._smtp_rows[key]
            row["sent"].configure(text=str(item["sent"]))
            row["err"].configure(text=str(item["errors"]))
            st_color = self._status_color(item["status"])
            row["status"].configure(text=item["status"], text_color=st_color)

        # ── Proxy-таблица ─────────────────────────────
        for item in snap["proxy"]:
            key = item["address"]
            if key not in self._proxy_rows:
                self._create_proxy_row(key)
            row = self._proxy_rows[key]
            row["used"].configure(text=str(item["used"]))
            row["err"].configure(text=str(item["errors"]))
            st_color = self._status_color(item["status"])
            row["status"].configure(text=item["status"], text_color=st_color)



    # ── создание строк таблиц ────────────────────────────

    def _create_smtp_row(self, email: str) -> None:
        row = ctk.CTkFrame(self.smtp_table, fg_color="transparent")
        row.pack(fill="x", padx=2, pady=1)

        lbl_email = ctk.CTkLabel(
            row, text=email, width=180, font=(FONT_MONO, 10),
            text_color=COLOR_TEXT, anchor="w",
        )
        lbl_email.pack(side="left")

        lbl_sent = ctk.CTkLabel(
            row, text="0", width=50, font=(FONT_MONO, 10),
            text_color=COLOR_ACCENT, anchor="w",
        )
        lbl_sent.pack(side="left")

        lbl_err = ctk.CTkLabel(
            row, text="0", width=45, font=(FONT_MONO, 10),
            text_color=COLOR_ERROR, anchor="w",
        )
        lbl_err.pack(side="left")

        lbl_st = ctk.CTkLabel(
            row, text="ожидание", width=60, font=(FONT_MONO, 10),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        lbl_st.pack(side="left")

        self._smtp_rows[email] = {
            "frame": row, "sent": lbl_sent, "err": lbl_err, "status": lbl_st,
        }

    def _create_proxy_row(self, address: str) -> None:
        row = ctk.CTkFrame(self.proxy_table, fg_color="transparent")
        row.pack(fill="x", padx=2, pady=1)

        lbl_addr = ctk.CTkLabel(
            row, text=address, width=180, font=(FONT_MONO, 10),
            text_color=COLOR_TEXT, anchor="w",
        )
        lbl_addr.pack(side="left")

        lbl_used = ctk.CTkLabel(
            row, text="0", width=50, font=(FONT_MONO, 10),
            text_color=COLOR_ACCENT, anchor="w",
        )
        lbl_used.pack(side="left")

        lbl_err = ctk.CTkLabel(
            row, text="0", width=45, font=(FONT_MONO, 10),
            text_color=COLOR_ERROR, anchor="w",
        )
        lbl_err.pack(side="left")

        lbl_st = ctk.CTkLabel(
            row, text="ожидание", width=60, font=(FONT_MONO, 10),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        lbl_st.pack(side="left")

        self._proxy_rows[address] = {
            "frame": row, "used": lbl_used, "err": lbl_err, "status": lbl_st,
        }

    # ── export handlers ──────────────────────────────────

    def _on_export(self, fmt: str) -> None:
        logs = self.logger.list_send_logs()
        if not logs:
            self.export_action.configure(
                text="✗  Логи отправки не найдены", text_color=COLOR_ERROR)
            return
        src = logs[0]  # самый свежий

        if fmt == "csv":
            dst = filedialog.asksaveasfilename(
                title="Экспорт CSV",
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile=src.stem + ".csv",
            )
        else:
            dst = filedialog.asksaveasfilename(
                title="Экспорт JSON",
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
                initialfile=src.stem + ".json",
            )
        if not dst:
            return

        def _do() -> None:
            try:
                if fmt == "csv":
                    count = self.logger.export_csv(src, Path(dst))
                else:
                    count = self.logger.export_json(src, Path(dst))
                self.parent.after(0, lambda: self.export_action.configure(
                    text=f"✓  Экспортировано {count} записей → {Path(dst).name}",
                    text_color=COLOR_ACCENT))
            except Exception as e:
                self.parent.after(0, lambda: self.export_action.configure(
                    text=f"✗  {e}", text_color=COLOR_ERROR))

        threading.Thread(target=_do, daemon=True).start()

    # ── helpers ──────────────────────────────────────────

    @staticmethod
    def _status_color(status: str) -> str:
        if status == "active":
            return COLOR_ACCENT
        if status == "dead":
            return COLOR_ERROR
        return COLOR_TEXT_DIM
