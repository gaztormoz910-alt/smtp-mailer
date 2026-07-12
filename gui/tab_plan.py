"""Вкладка План распределения.

Отображает расчет того, как письма будут распределены
между живыми SMTP аккаунтами.
"""

from __future__ import annotations

import math
import customtkinter as ctk

from gui.theme import (
    COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_BTN,
    COLOR_BTN_HVR, COLOR_FRAME, COLOR_TEXT, COLOR_TEXT_DIM,
    FONT_FAMILY
)
from core.smtp_manager import SmtpManager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.tab_send import SendTab


class PlanTab:
    """Содержимое вкладки План."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        smtp_mgr: SmtpManager,
        send_tab: SendTab,
    ) -> None:
        self.parent = parent
        self.smtp_mgr = smtp_mgr
        self.send_tab = send_tab

        self._build_layout()

    def _build_layout(self) -> None:
        outer = ctk.CTkFrame(self.parent, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        ctk.CTkLabel(
            outer,
            text="📊 План распределения писем",
            font=(FONT_FAMILY, 20, "bold"),
            text_color=COLOR_TEXT
        ).pack(anchor="w", pady=(0, 5))

        ctk.CTkLabel(
            outer,
            text="Здесь показано, как база получателей будет поделена между живыми SMTP аккаунтами.",
            font=(FONT_FAMILY, 12),
            text_color=COLOR_TEXT_DIM
        ).pack(anchor="w", pady=(0, 20))

        # Main frame
        self.info_frame = ctk.CTkFrame(
            outer, fg_color=COLOR_FRAME, corner_radius=10,
            border_color=COLOR_BORDER, border_width=1
        )
        self.info_frame.pack(fill="x", pady=(0, 20))

        # Stats labels
        self.lbl_smtps = ctk.CTkLabel(
            self.info_frame, text="Живых SMTP: ?", font=(FONT_FAMILY, 14), text_color=COLOR_TEXT
        )
        self.lbl_smtps.pack(anchor="w", padx=20, pady=(20, 5))

        self.lbl_recipients = ctk.CTkLabel(
            self.info_frame, text="Всего получателей: ?", font=(FONT_FAMILY, 14), text_color=COLOR_TEXT
        )
        self.lbl_recipients.pack(anchor="w", padx=20, pady=(0, 15))

        # Result frame
        res_frame = ctk.CTkFrame(self.info_frame, fg_color=COLOR_BG, corner_radius=8)
        res_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.lbl_result = ctk.CTkLabel(
            res_frame, text="Нажмите «Обновить расчет», чтобы увидеть распределение.",
            font=(FONT_FAMILY, 14, "bold"), text_color=COLOR_ACCENT,
            justify="left", wraplength=700
        )
        self.lbl_result.pack(padx=20, pady=20)

        # Update button
        self.btn_update = ctk.CTkButton(
            outer,
            text="🔄  Обновить расчет",
            width=200, height=36,
            fg_color=COLOR_BTN, hover_color=COLOR_BTN_HVR,
            text_color=COLOR_TEXT, font=(FONT_FAMILY, 14, "bold"),
            corner_radius=8,
            command=self.refresh_plan
        )
        self.btn_update.pack(anchor="center")

    def refresh_plan(self) -> None:
        """Пересчитывает план и обновляет UI."""
        alive = self.smtp_mgr.count_alive
        recipients = len(self.send_tab._recipients)

        self.lbl_smtps.configure(text=f"Живых SMTP: {alive}")
        self.lbl_recipients.configure(text=f"Всего получателей: {recipients}")

        if alive == 0:
            self.lbl_result.configure(text="Нет живых SMTP аккаунтов. Пожалуйста, загрузите и проверьте их.", text_color=COLOR_TEXT_DIM)
            return

        if recipients == 0:
            self.lbl_result.configure(text="Нет получателей. Пожалуйста, соберите очередь во вкладке «Кампания».", text_color=COLOR_TEXT_DIM)
            return

        if alive >= recipients:
            self.lbl_result.configure(
                text=f"Внимание: {recipients} аккаунтов отправят по 1 письму, а остальные {alive - recipients} аккаунтов отдыхают.",
                text_color=COLOR_ACCENT
            )
            return

        base_amount = recipients // alive
        remainder = recipients % alive

        if remainder == 0:
            if alive == 1:
                text = f"1 отправитель разошлет все {recipients} писем."
            else:
                text = f"{alive} отправителей разошлют ровно по {base_amount} писем."
        else:
            group1_count = remainder
            group1_amount = base_amount + 1
            group2_count = alive - remainder
            group2_amount = base_amount

            def plural_senders(n: int) -> str:
                if n % 10 == 1 and n % 100 != 11:
                    return f"{n} отправитель"
                elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
                    return f"{n} отправителя"
                else:
                    return f"{n} отправителей"

            def plural_emails(n: int) -> str:
                mod10 = n % 10
                mod100 = n % 100
                if mod10 == 1 and mod100 != 11:
                    return f"{n} письмо"
                elif 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
                    return f"{n} письма"
                else:
                    return f"{n} писем"

            p1 = f"{plural_senders(group1_count)} разошлют по {plural_emails(group1_amount)}"
            p2 = f"{plural_senders(group2_count)} разошлют по {plural_emails(group2_amount)}"
            text = f"{p1}, а {p2}."

        self.lbl_result.configure(text=text, text_color=COLOR_ACCENT)
        
        # Автоматически обновляем настройки во вкладке Отправка
        def _set_entry(entry, value):
            entry.delete(0, "end")
            entry.insert(0, value)

        optimal = math.ceil(recipients / alive)
        _set_entry(self.send_tab.threads_entry, str(alive))
        _set_entry(self.send_tab.conn_limit_entry, str(optimal))

    def set_ui_locked(self, locked: bool) -> None:
        state = "disabled" if locked else "normal"
        self.btn_update.configure(state=state)
