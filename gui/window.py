"""
Главное окно приложения CHARLY MAILER.

Инициализирует CTkTabview с пятью вкладками и маршрутизирует
содержимое каждой вкладки в отдельный модуль gui/tab_*.py.

Общие менеджеры (proxy, smtp, content, stats) создаются здесь
и передаются во все вкладки, которым они нужны.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from core.content import ContentManager
from core.proxy_manager import ProxyManager
from core.smtp_manager import SmtpManager
from core.stats import SendStats

from gui.theme import (
    COLOR_BG, COLOR_BG_SEC, COLOR_ACCENT, COLOR_ACCENT_HVR,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_BORDER, FONT_FAMILY,
)
from gui.tab_setup import SetupTab
from gui.tab_content import ContentTab
from gui.tab_campaign import CampaignTab
from gui.tab_send import SendTab
from gui.tab_stats import StatsTab
from gui.tab_plan import PlanTab


class App(ctk.CTk):
    """Корневое окно приложения."""

    def __init__(self) -> None:
        super().__init__()

        # ── Окно ──────────────────────────────────────────────
        self.title("CHARLY MAILER")
        self.geometry("940x640")
        self.minsize(780, 500)
        self.configure(fg_color=COLOR_BG)

        # ── Общие менеджеры ───────────────────────────────────
        self.proxy_mgr = ProxyManager()
        self.smtp_mgr = SmtpManager()
        self.content_mgr = ContentManager()
        self.stats = SendStats()

        # ── Заголовок удален ──────────────────────────────────

        # ── Табы ──────────────────────────────────────────────
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=COLOR_BG_SEC,
            segmented_button_fg_color="#18181b",
            segmented_button_selected_color=COLOR_ACCENT,
            segmented_button_selected_hover_color=COLOR_ACCENT_HVR,
            segmented_button_unselected_color="#18181b",
            segmented_button_unselected_hover_color="#27272a",
            text_color=COLOR_TEXT,
            text_color_disabled=COLOR_TEXT_DIM,
            border_color=COLOR_BORDER,
            border_width=1,
            corner_radius=10,
            command=self._on_tab_changed,
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Порядок вкладок фиксированный — не менять
        tab_names = ["Настройки", "Контент", "Кампания", "План", "Отправка", "Статистика"]
        for name in tab_names:
            self.tabview.add(name)

        # ── Монтируем содержимое вкладок ──────────────────────
        self.tab_setup = SetupTab(
            self.tabview.tab("Настройки"),
            proxy_mgr=self.proxy_mgr,
            smtp_mgr=self.smtp_mgr,
        )

        self.tab_content = ContentTab(
            self.tabview.tab("Контент"),
            content_mgr=self.content_mgr,
        )

        self.tab_campaign = CampaignTab(self.tabview.tab("Кампания"))

        self.tab_send = SendTab(
            self.tabview.tab("Отправка"),
            content_mgr=self.content_mgr,
            smtp_mgr=self.smtp_mgr,
            proxy_mgr=self.proxy_mgr,
            stats=self.stats,
            campaign_tab=self.tab_campaign,
        )

        self.tab_stats = StatsTab(
            self.tabview.tab("Статистика"),
            stats=self.stats,
        )

        self.tab_plan = PlanTab(
            self.tabview.tab("План"),
            smtp_mgr=self.smtp_mgr,
            send_tab=self.tab_send,
        )
        self.tab_send.plan_tab = self.tab_plan

        # ── Связь Campaign → Send (после создания обоих) ──────
        self.tab_campaign.on_queue_ready = self.tab_send.set_recipients

        # ── Hover и цвет текста табов ────────────────────────
        
        self._on_tab_changed()

    def _on_tab_changed(self):
        """Обновляет цвет текста табов при переключении."""
        current = self.tabview.get()
        for name, btn in self.tabview._segmented_button._buttons_dict.items():
            if name == current:
                btn.configure(text_color=COLOR_BG)
            else:
                btn.configure(text_color=COLOR_TEXT)

    # ══════════════════════════════════════════════════════
    #  UI LOCKING
    # ══════════════════════════════════════════════════════

    def set_ui_locked(self, locked: bool) -> None:
        """Блокирует или разблокирует весь UI во время рассылки."""
        self.tab_setup.set_ui_locked(locked)
        self.tab_content.set_ui_locked(locked)
        self.tab_campaign.set_ui_locked(locked)
        self.tab_plan.set_ui_locked(locked)
        self.tab_send.set_ui_locked(locked)

    # ══════════════════════════════════════════════════════
    #  PRESETS — gather / apply  (вызывается из CampaignTab)
    # ══════════════════════════════════════════════════════

    def gather_full_preset(self) -> dict:
        """Собирает ВСЕ настройки приложения в один dict."""
        data: dict = {}

        # Setup
        data["proxy_file"] = self.tab_setup._proxy_file
        data["smtp_file"] = self.tab_setup._smtp_file

        # Content
        data["subjects_file"] = self.tab_content._subjects_file
        data["bodies_file"] = self.tab_content._bodies_file
        data["senders_file"] = self.tab_content._senders_file
        data["link_files"] = list(self.tab_content._link_file_paths)
        data["consistent_links"] = self.content_mgr.consistent_links
        data["email_only"] = self.content_mgr.email_only

        # Campaign
        data.update(self.tab_campaign.gather_preset())

        # Send
        data["delay"] = self.tab_send._float(self.tab_send.delay_entry, 5.0)
        data["jitter"] = self.tab_send._float(self.tab_send.jitter_entry, 2.0)

        return data

    def apply_full_preset(self, data: dict) -> list[str]:
        """Применяет пресет. Возвращает список предупреждений."""
        warnings: list[str] = []

        # Setup — proxy
        pfile = data.get("proxy_file", "")
        if pfile:
            if Path(pfile).exists():
                try:
                    self.proxy_mgr.load_from_file(pfile)
                    self.tab_setup._proxy_file = pfile
                    self.tab_setup.parent.after(0, lambda: (
                        self.tab_setup._px_load_done(
                            self.proxy_mgr.count_total, Path(pfile).name),
                    ))
                except Exception as e:
                    warnings.append(f"Proxy: {e}")
            else:
                warnings.append(f"Файл прокси не найден: {pfile}")

        # Setup — smtp
        sfile = data.get("smtp_file", "")
        if sfile:
            if Path(sfile).exists():
                try:
                    self.smtp_mgr.load_from_file(sfile)
                    self.tab_setup._smtp_file = sfile
                    self.tab_setup.parent.after(0, lambda: (
                        self.tab_setup._sm_load_done(
                            self.smtp_mgr.count_total, Path(sfile).name),
                    ))
                except Exception as e:
                    warnings.append(f"SMTP: {e}")
            else:
                warnings.append(f"Файл SMTP не найден: {sfile}")

        # Content — subjects
        subj = data.get("subjects_file", "")
        if subj:
            if Path(subj).exists():
                try:
                    cnt = self.content_mgr.load_subjects(subj)
                    self.tab_content._subjects_file = subj
                    self.tab_content.parent.after(0, lambda: self.tab_content._subj_done(cnt))
                except Exception as e:
                    warnings.append(f"Subjects: {e}")
            else:
                warnings.append(f"Файл тем не найден: {subj}")

        # Content — bodies
        bod = data.get("bodies_file", "")
        if bod:
            if Path(bod).exists():
                try:
                    cnt = self.content_mgr.load_bodies(bod)
                    self.tab_content._bodies_file = bod
                    self.tab_content.parent.after(0, lambda: self.tab_content._body_done(cnt))
                except Exception as e:
                    warnings.append(f"Bodies: {e}")
            else:
                warnings.append(f"Файл писем не найден: {bod}")

        # Content — senders
        snd = data.get("senders_file", "")
        if snd:
            if Path(snd).exists():
                try:
                    cnt = self.content_mgr.load_sender_names(snd)
                    self.tab_content._senders_file = snd
                    self.tab_content.parent.after(0, lambda: self.tab_content._senders_done(cnt))
                except Exception as e:
                    warnings.append(f"Senders: {e}")
            else:
                warnings.append(f"Файл отправителей не найден: {snd}")

        # Content — links
        for lf in data.get("link_files", []):
            if Path(lf).exists():
                try:
                    self.content_mgr.load_links_file(lf)
                    if lf not in self.tab_content._link_file_paths:
                        self.tab_content._link_file_paths.append(lf)
                except Exception as e:
                    warnings.append(f"Links ({lf}): {e}")
            else:
                warnings.append(f"Файл ссылок не найден: {lf}")
        self.tab_content.parent.after(0, self.tab_content._refresh_link_list)

        # Content — flags
        self.content_mgr.consistent_links = data.get("consistent_links", False)
        self.content_mgr.email_only = data.get("email_only", False)
        self.tab_content.consistent_var.set(self.content_mgr.consistent_links)
        self.tab_content.email_only_var.set(self.content_mgr.email_only)

        # Campaign
        w = self.tab_campaign.apply_preset(data)
        warnings.extend(w)

        # Send — delay / jitter
        delay = str(data.get("delay", 5))
        jitter = str(data.get("jitter", 2))
        self.tab_send.delay_entry.delete(0, "end")
        self.tab_send.delay_entry.insert(0, delay)
        self.tab_send.jitter_entry.delete(0, "end")
        self.tab_send.jitter_entry.insert(0, jitter)

        return warnings
