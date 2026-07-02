"""Вкладка Send — тестовая отправка + управление массовой рассылкой.

Тест: одиночная отправка на указанный адрес.
Кампания: СТАРТ / СТОП / ПАУЗА с настройкой задержки и jitter.
Превью полностью собранного письма.
"""

from __future__ import annotations

import threading

import customtkinter as ctk

from core.content import ContentManager
from core.logger import JsonLogger
from core.proxy_manager import ProxyManager
from core.queue_manager import Recipient
from core.sender import (
    CampaignSender,
    clear_queue_state,
    generate_preview,
    load_queue_state,
    send_test,
)
from core.smtp_manager import SmtpManager
from core.stats import SendStats
from gui.theme import (
    COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_BTN, COLOR_BTN_HVR,
    COLOR_ERROR, COLOR_FRAME, COLOR_TEXT, COLOR_TEXT_DIM, COLOR_WARN,
    FONT_FAMILY, FONT_MONO,
)


class SendTab:
    """Содержимое вкладки Send."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        content_mgr: ContentManager,
        smtp_mgr: SmtpManager,
        proxy_mgr: ProxyManager,
        stats: SendStats,
        campaign_tab=None,
    ) -> None:
        self.parent = parent
        self.content_mgr = content_mgr
        self.smtp_mgr = smtp_mgr
        self.proxy_mgr = proxy_mgr
        self.stats = stats
        self.logger = JsonLogger()
        self.campaign_tab = campaign_tab

        self._campaign: CampaignSender | None = None
        self._recipients: list[Recipient] = []  # заполняется из Campaign-таба

        self._build_layout()
        self._check_resume_state()

    # ══════════════════════════════════════════════════════
    #  LAYOUT
    # ══════════════════════════════════════════════════════

    def _build_layout(self) -> None:
        outer = ctk.CTkFrame(self.parent, fg_color="transparent")
        outer.pack(fill="both", expand=True)

        self._build_test(outer)
        self._build_controls(outer)
        self._build_preview(outer)

    # ── 1. Test Send ─────────────────────────────────────

    def _build_test(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(
            frame, text="🧪  Тестовая отправка",
            font=(FONT_FAMILY, 14, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 6))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 6))

        ctk.CTkLabel(
            row, text="Кому:", font=(FONT_FAMILY, 12), text_color=COLOR_TEXT_DIM,
        ).pack(side="left", padx=(0, 6))

        self.test_email_entry = ctk.CTkEntry(
            row, width=250, height=30, placeholder_text="test@example.com",
            font=(FONT_FAMILY, 12), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER, corner_radius=8,
        )
        self.test_email_entry.pack(side="left", padx=(0, 10))

        self.btn_test = ctk.CTkButton(
            row, text="📨  ОТПРАВИТЬ ТЕСТ", width=140, height=32,
            fg_color="#166534", hover_color="#15803d",
            text_color="#4ade80", font=(FONT_FAMILY, 13, "bold"),
            border_color=COLOR_ACCENT, border_width=2, corner_radius=8,
            command=self._on_test_send,
        )
        self.btn_test.pack(side="left", padx=(0, 10))

        self.test_result = ctk.CTkLabel(
            row, text="", font=(FONT_FAMILY, 12),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.test_result.pack(side="left", fill="x", expand=True)

    # ── 2. Campaign Controls ─────────────────────────────

    def _build_controls(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(
            frame, text="📨  Управление кампанией",
            font=(FONT_FAMILY, 14, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 6))

        # ── Задержка ──
        delay_row = ctk.CTkFrame(frame, fg_color="transparent")
        delay_row.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(delay_row, text="Задержка:", font=(FONT_FAMILY, 12),
                     text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 4))
        self.delay_entry = ctk.CTkEntry(
            delay_row, width=50, height=28, placeholder_text="5",
            font=(FONT_FAMILY, 12), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER,
            corner_radius=6, justify="center",
        )
        self.delay_entry.pack(side="left", padx=(0, 4))
        self.delay_entry.insert(0, "5")
        ctk.CTkLabel(delay_row, text="сек", font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(delay_row, text="±Разброс:", font=(FONT_FAMILY, 12),
                     text_color=COLOR_TEXT_DIM).pack(side="left", padx=(0, 4))
        self.jitter_entry = ctk.CTkEntry(
            delay_row, width=50, height=28, placeholder_text="2",
            font=(FONT_FAMILY, 12), fg_color=COLOR_BG,
            text_color=COLOR_TEXT, border_color=COLOR_BORDER,
            corner_radius=6, justify="center",
        )
        self.jitter_entry.pack(side="left", padx=(0, 4))
        self.jitter_entry.insert(0, "2")
        ctk.CTkLabel(delay_row, text="сек", font=(FONT_FAMILY, 11),
                     text_color=COLOR_TEXT_DIM).pack(side="left")

        # ── Кнопки ──
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 12))

        self.btn_preview = ctk.CTkButton(
            btn_row, text="👁  Предпросмотр", width=110, height=34,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_TEXT, font=(FONT_FAMILY, 12, "bold"),
            corner_radius=8, command=self._on_preview,
        )
        self.btn_preview.pack(side="left", padx=(0, 8))

        self.btn_start = ctk.CTkButton(
            btn_row, text="▶  СТАРТ", width=130, height=34,
            fg_color="#166534", hover_color="#15803d",
            text_color="#4ade80", font=(FONT_FAMILY, 14, "bold"),
            border_color=COLOR_ACCENT, border_width=2, corner_radius=8,
            command=self._on_start,
        )
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            btn_row, text="■  СТОП", width=110, height=34,
            fg_color="#7f1d1d", hover_color="#991b1b",
            text_color=COLOR_ERROR, font=(FONT_FAMILY, 13, "bold"),
            border_color=COLOR_ERROR, border_width=2, corner_radius=8,
            state="disabled", command=self._on_stop,
        )
        self.btn_stop.pack(side="left", padx=(0, 8))

        self.btn_pause = ctk.CTkButton(
            btn_row, text="⏸  ПАУЗА", width=120, height=34,
            fg_color="#78350f", hover_color="#92400e",
            text_color=COLOR_WARN, font=(FONT_FAMILY, 13, "bold"),
            border_color=COLOR_WARN, border_width=2, corner_radius=8,
            state="disabled", command=self._on_pause,
        )
        self.btn_pause.pack(side="left")

        # ── Статус ──
        self.campaign_status = ctk.CTkLabel(
            frame, text="Готов  ·  Загрузите получателей и SMTP для старта",
            font=(FONT_FAMILY, 12), text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self.campaign_status.pack(fill="x", padx=14, pady=(0, 10))

    # ── 3. Preview area ──────────────────────────────────

    def _build_preview(self, container: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(
            container, fg_color=COLOR_FRAME,
            corner_radius=10, border_color=COLOR_BORDER, border_width=1,
        )
        frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=14, pady=(10, 4))
        
        ctk.CTkLabel(
            header_frame, text="📄 Предпросмотр письма / Лог",
            font=(FONT_FAMILY, 13, "bold"), text_color=COLOR_TEXT, anchor="w",
        ).pack(side="left")
        
        ctk.CTkButton(
            header_frame, text="Копировать", width=80, height=24,
            font=(FONT_FAMILY, 11), fg_color="#333333", hover_color="#444444",
            text_color="#AAAAAA", command=lambda: self._copy_preview()
        ).pack(side="right")

        self.preview_box = ctk.CTkTextbox(
            frame, fg_color=COLOR_BG,
            text_color=COLOR_ACCENT, font=(FONT_MONO, 12),
            corner_radius=8, border_color=COLOR_BORDER, border_width=1,
            state="disabled", wrap="word",
        )
        self.preview_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    # ══════════════════════════════════════════════════════
    #  ОБРАБОТЧИКИ
    # ══════════════════════════════════════════════════════

    # ── Test ──────────────────────────────────────────────

    def _on_test_send(self) -> None:
        to = self.test_email_entry.get().strip()
        if not to or "@" not in to:
            self.test_result.configure(text="✗  Введите корректный email",
                                       text_color=COLOR_ERROR)
            return
        self.btn_test.configure(state="disabled", text="Отправка…")
        self.test_result.configure(text="", text_color=COLOR_TEXT_DIM)

        def _do() -> None:
            ok, info = send_test(
                to, self.content_mgr, self.smtp_mgr, self.proxy_mgr, self.logger,
            )
            def _upd() -> None:
                self.btn_test.configure(state="normal", text="📨  ОТПРАВИТЬ ТЕСТ")
                if ok:
                    self.test_result.configure(text=f"✓  {info}", text_color=COLOR_ACCENT)
                else:
                    self.test_result.configure(text=f"✗  {info}", text_color=COLOR_ERROR)
            self.parent.after(0, _upd)

        threading.Thread(target=_do, daemon=True).start()

    # ── Preview ──────────────────────────────────────────

    def _on_preview(self) -> None:
        text = generate_preview(self.content_mgr, self.smtp_mgr)
        self._set_preview(text)

    # ── Start ────────────────────────────────────────────

    def _on_start(self) -> None:
        if not self._recipients:
            self.campaign_status.configure(
                text="✗  Получатели не загружены — перейдите во вкладку Кампания",
                text_color=COLOR_ERROR)
            return
        if self.smtp_mgr.count_alive == 0:
            self.campaign_status.configure(
                text="✗  Нет живых SMTP — перейдите во вкладку Настройки",
                text_color=COLOR_ERROR)
            return

        delay = self._float(self.delay_entry, 5.0)
        jitter = self._float(self.jitter_entry, 2.0)

        # CC/BCC из Campaign-таба
        cc_addrs, cc_pct = [], 0
        bcc_addrs, bcc_pct = [], 0
        if self.campaign_tab:
            cc_addrs, cc_pct = self.campaign_tab.get_cc_config()
            bcc_addrs, bcc_pct = self.campaign_tab.get_bcc_config()

        self._campaign = CampaignSender(
            recipients=self._recipients,
            content_mgr=self.content_mgr,
            smtp_mgr=self.smtp_mgr,
            proxy_mgr=self.proxy_mgr,
            stats=self.stats,
            logger=self.logger,
            cc_addrs=cc_addrs,
            bcc_addrs=bcc_addrs,
            cc_percent=cc_pct,
            bcc_percent=bcc_pct,
            on_status=lambda t: self.parent.after(0, lambda: self.campaign_status.configure(
                text=t, text_color=COLOR_ACCENT)),
            on_finished=lambda: self.parent.after(0, self._on_campaign_done),
        )
        self._campaign.start(delay=delay, jitter=jitter)

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_pause.configure(state="normal")

        cc_info = f"  CC:{cc_pct}%" if cc_pct else ""
        bcc_info = f"  BCC:{bcc_pct}%" if bcc_pct else ""
        self.campaign_status.configure(
            text=f"▶  Отправка {len(self._recipients)} получателям…{cc_info}{bcc_info}",
            text_color=COLOR_ACCENT)
        self._set_preview(f"Кампания начата: {len(self._recipients)} получателей\n"
                          f"Delay: {delay}s ±{jitter}s{cc_info}{bcc_info}")

    # ── Stop ─────────────────────────────────────────────

    def _on_stop(self) -> None:
        if self._campaign:
            self._campaign.stop()
        self.btn_stop.configure(state="disabled")
        self.btn_pause.configure(state="disabled")
        self.btn_start.configure(state="normal")
        self.campaign_status.configure(text="■  Остановлено", text_color=COLOR_ERROR)

    # ── Pause / Resume ───────────────────────────────────

    def _on_pause(self) -> None:
        if not self._campaign:
            return
        if self._campaign.paused:
            self._campaign.resume()
            self.btn_pause.configure(text="⏸  ПАУЗА", text_color=COLOR_WARN)
            self.campaign_status.configure(text="▶  Возобновлено", text_color=COLOR_ACCENT)
        else:
            self._campaign.pause()
            self.btn_pause.configure(text="▶  ПРОДОЛЖИТЬ", text_color=COLOR_ACCENT)
            self.campaign_status.configure(text="⏸  На паузе", text_color=COLOR_WARN)

    # ── Campaign done callback ───────────────────────────

    def _on_campaign_done(self) -> None:
        self.btn_stop.configure(state="disabled")
        self.btn_pause.configure(state="disabled", text="⏸  ПАУЗА", text_color=COLOR_WARN)
        self.btn_start.configure(state="normal")
        snap = self.stats.snapshot
        self.campaign_status.configure(
            text=f"✓  Завершено — Отправлено: {snap['sent']}  Ошибок: {snap['errors']}",
            text_color=COLOR_ACCENT)
        clear_queue_state()

    # ── Resume state check ───────────────────────────────

    def _check_resume_state(self) -> None:
        state = load_queue_state()
        if not state:
            return
        remaining = state.get("remaining", [])
        if not remaining:
            return
        self.parent.after(500, lambda: self._show_resume_dialog(remaining, state))

    def _show_resume_dialog(self, remaining: list[str], state: dict) -> None:
        dialog = ctk.CTkToplevel(self.parent)
        dialog.title("Resume Campaign")
        dialog.geometry("420x200")
        dialog.configure(fg_color=COLOR_FRAME)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        total = state.get("total", len(remaining))
        sent = state.get("sent_count", 0)

        ctk.CTkLabel(
            dialog, text="⚡ Обнаружена прерванная кампания",
            font=(FONT_FAMILY, 15, "bold"), text_color=COLOR_TEXT,
        ).pack(pady=(20, 8))

        ctk.CTkLabel(
            dialog,
            text=f"Отправлено: {sent} / {total}  ·  Осталось: {len(remaining)}",
            font=(FONT_MONO, 12), text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 16))

        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(pady=10)

        def _resume() -> None:
            self._recipients = remaining
            self.campaign_status.configure(
                text=f"↻  Очередь возобновлена: {len(remaining)} получателей",
                text_color=COLOR_ACCENT)
            dialog.destroy()

        def _discard() -> None:
            clear_queue_state()
            dialog.destroy()

        ctk.CTkButton(
            row, text="▶  Возобновить", width=120, height=34,
            fg_color="#166534", hover_color="#15803d",
            text_color=COLOR_ACCENT, font=(FONT_FAMILY, 13, "bold"),
            corner_radius=8, command=_resume,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            row, text="✕  Сбросить", width=120, height=34,
            fg_color="#7f1d1d", hover_color="#991b1b",
            text_color=COLOR_ERROR, font=(FONT_FAMILY, 13, "bold"),
            corner_radius=8, command=_discard,
        ).pack(side="left", padx=10)

    # ══════════════════════════════════════════════════════
    #  ПУБЛИЧНОЕ API (вызывается из Campaign-таба)
    # ══════════════════════════════════════════════════════

    def set_recipients(self, recipients: list[Recipient]) -> None:
        """Устанавливает список получателей из Campaign-таба."""
        self._recipients = list(recipients)
        count = len(self._recipients)
        if count:
            self.campaign_status.configure(
                text=f"Готов  ·  Загружено {count} получателей",
                text_color=COLOR_ACCENT)
        else:
            self.campaign_status.configure(
                text="Готов  ·  Загрузите получателей для старта",
                text_color=COLOR_TEXT_DIM)

    # ══════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════

    def _set_preview(self, text: str) -> None:
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("1.0", text)
        self.preview_box.configure(state="disabled")

    def _copy_preview(self) -> None:
        text = self.preview_box.get("1.0", "end-1c")
        if text:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(text)

    @staticmethod
    def _float(entry: ctk.CTkEntry, default: float) -> float:
        try:
            return max(0.1, float(entry.get().strip()))
        except (ValueError, AttributeError):
            return default
