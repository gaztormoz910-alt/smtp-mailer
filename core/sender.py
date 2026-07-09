"""sender.py — движок отправки писем.

Формирование MIME (CC/BCC), тестовая отправка, цикл массовой рассылки
с ``threading.Event`` для stop/pause, сохранение прогресса.
"""

from __future__ import annotations

import html
import json
import random
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Any, Callable

from core.content import ContentManager
from core.logger import JsonLogger
from core.proxy_manager import ProxyManager
from core.queue_manager import Recipient
from core.smtp_manager import SmtpManager, SmtpStatus, connect_smtp
from core.stats import SendStats

STATE_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_FILE = STATE_DIR / "queue-state.json"


# ── X-Mailer ротация (имитация реальных клиентов) ─────────

_MAILERS = [
    "Microsoft Outlook 16.0",
    "Mozilla Thunderbird 115.0",
    "Apple Mail (2.3774.200.91)",
    "Mozilla/5.0",
    "Postbox 7.0.61",
    "The Bat! 11.3",
    "eM Client 9.2",
]


# ── MIME-сообщение ────────────────────────────────────────


def build_message(
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
    is_html: bool,
    sender_name: str = "",
    cc_addrs: list[str] | None = None,
) -> MIMEMultipart:
    """Формирует MIMEMultipart с антиспам-заголовками.

    ``formataddr`` корректно энкодит кириллицу и спецсимволы
    в имени отправителя по RFC 2047.

    **CC** попадает в заголовки.
    **BCC** категорически запрещено добавлять в заголовки —
    адреса BCC передаются только в конверт (``sendmail to_addrs``).

    ``Message-ID`` генерируется с доменом отправителя (SPF/DKIM trust).
    ``X-Mailer`` рандомизируется, чтобы не палить массовую рассылку.
    """
    if is_html:
        msg = MIMEMultipart("alternative")
        # Для HTML писем обязательно нужна plain-text альтернатива (иначе спам-фильтры банят)
        import re
        plain_body = re.sub(r'<[^>]+>', ' ', body) # Простая очистка от тегов
        plain_body = re.sub(r'\s+', ' ', plain_body).strip()
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        # Автоматически создаём HTML-версию с кликабельными ссылками
        import re
        html_body = html.escape(body).replace("\n", "<br>\n")
        
        # 1. Поддержка Markdown-ссылок: [Текст ссылки](URL) -> <a href="URL">Текст ссылки</a>
        html_body = re.sub(r'\[([^\]]+)\]\((https?://[^\s<)]+)\)', r'<a href="\2">\1</a>', html_body)
        
        # 2. Оборачиваем остальные сырые ссылки в <a> (но не трогаем те, что уже внутри <a>)
        parts = re.split(r'(<a\s[^>]+>.*?</a>)', html_body)
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r'(https?://[^\s<]+)', r'<a href="\1">\1</a>', parts[i])
        html_body = "".join(parts)
        
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    if sender_name:
        msg["From"] = formataddr((sender_name, from_email))
    else:
        msg["From"] = from_email

    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)

    # Message-ID с доменом отправителя (а не hostname машины)
    sender_domain = from_email.split("@")[-1] if "@" in from_email else "localhost"
    msg["Message-ID"] = make_msgid(domain=sender_domain)

    msg["MIME-Version"] = "1.0"
    msg["X-Mailer"] = random.choice(_MAILERS)

    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)

    return msg


def _envelope_recipients(
    to_email: str,
    cc_addrs: list[str] | None = None,
    bcc_addrs: list[str] | None = None,
) -> list[str]:
    """Собирает полный список получателей конверта."""
    addrs = [to_email]
    if cc_addrs:
        addrs.extend(cc_addrs)
    if bcc_addrs:
        addrs.extend(bcc_addrs)
    return addrs


# ── Тестовая отправка ─────────────────────────────────────


def send_test(
    to_email: str,
    content_mgr: ContentManager,
    smtp_mgr: SmtpManager,
    proxy_mgr: ProxyManager,
    logger: JsonLogger,
) -> tuple[bool, str]:
    """Одиночная тестовая отправка.  Возвращает ``(ok, info_msg)``."""
    t0 = time.time()

    smtp_acc = smtp_mgr.get_next()
    if not smtp_acc:
        return False, "No alive SMTP accounts"

    proxy = proxy_mgr.get_next()
    proxy_addr = f"{proxy.host}:{proxy.port}" if proxy else ""

    variables = {
        "email": to_email,
        "name": "Тестовый_Пользователь",
        "senderName": "",
    }

    sender_name = content_mgr.get_random_sender_name()
    variables["senderName"] = sender_name

    link_cache = {} if content_mgr.consistent_links else None

    try:
        subject = content_mgr.get_random_subject(variables, link_cache=link_cache)
        if not subject:
            subject = "(no subjects loaded)"
        body, is_html = content_mgr.get_random_body(variables, link_cache=link_cache)
        if not body:
            body, is_html = "(no body loaded)", False
    except ValueError as exc:
        return False, str(exc)

    conn = None
    try:
        msg = build_message(smtp_acc.email, to_email, subject, body, is_html, sender_name)
        conn = connect_smtp(smtp_acc, proxy=proxy)
        conn.sendmail(smtp_acc.email, [to_email], msg.as_string())
        conn.quit()
        conn = None
        elapsed = round(time.time() - t0, 2)
        smtp_acc.sent_count += 1

        info = f"Sent in {elapsed}s via {smtp_acc.email}"
        if proxy_addr:
            info += f" through {proxy_addr}"

        logger.log(
            "test_send", f"Test → {to_email}",
            recipient=to_email, smtp=smtp_acc.email,
            proxy=proxy_addr, subject=subject, elapsed=elapsed,
        )
        return True, info

    except Exception as exc:
        logger.log(
            "test_send_error", f"Test fail → {to_email}: {exc}",
            recipient=to_email, smtp=smtp_acc.email,
            proxy=proxy_addr, error=str(exc),
        )
        return False, f"{exc}"
    finally:
        if conn:
            try:
                conn.quit()
            except Exception:
                pass


# ── Генерация превью письма ───────────────────────────────


def generate_preview(
    content_mgr: ContentManager,
    smtp_mgr: SmtpManager,
    to_sample: str = "recipient@example.com",
) -> str:
    """Генерирует текстовый превью полностью собранного письма."""
    smtp_acc = smtp_mgr.get_next()
    from_email = smtp_acc.email if smtp_acc else "smtp@not-loaded"

    sender_name = content_mgr.get_random_sender_name()

    variables = {
        "email": to_sample,
        "name": "Тестовый_Пользователь",
        "senderName": sender_name,
    }

    link_cache = {} if content_mgr.consistent_links else None

    try:
        subject = content_mgr.get_random_subject(variables, link_cache=link_cache) or "(no subjects)"
        body, is_html = content_mgr.get_random_body(variables, link_cache=link_cache)
        if not body:
            body = "(no body loaded)"
    except ValueError as exc:
        return f"Error: {exc}"

    fmt = "HTML" if is_html else "Plain Text"
    from_line = formataddr((sender_name, from_email)) if sender_name else from_email

    lines = [
        f"From:      {from_line}",
        f"To:        {to_sample}",
        f"Subject:   {subject}",
        f"Format:    {fmt}",
        "─" * 55,
        body,
    ]
    return "\n".join(lines)


# ── Save / Load state ────────────────────────────────────


def save_queue_state(
    remaining: list[Recipient],
    sent_count: int,
    total: int,
) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "remaining": [r.to_dict() for r in remaining],
        "sent_count": sent_count,
        "total": total,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_queue_state() -> dict | None:
    """Возвращает dict с ``remaining`` как ``list[Recipient]`` или ``None``."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        raw = data.get("remaining")
        if not raw:
            return None
        recipients: list[Recipient] = []
        for item in raw:
            if isinstance(item, str):
                recipients.append(Recipient(email=item))
            elif isinstance(item, dict):
                recipients.append(Recipient.from_dict(item))
        data["remaining"] = recipients
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def clear_queue_state() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink(missing_ok=True)


# ── Массовая рассылка ────────────────────────────────────


class CampaignSender:
    """Движок массовой рассылки.

    ``stop_event`` и ``pause_event`` (``threading.Event``) обеспечивают
    корректную остановку и паузу без крашей.
    """

    def __init__(
        self,
        recipients: list[Recipient],
        content_mgr: ContentManager,
        smtp_mgr: SmtpManager,
        proxy_mgr: ProxyManager,
        stats: SendStats,
        logger: JsonLogger,
        cc_addrs: list[str] | None = None,
        bcc_addrs: list[str] | None = None,
        cc_percent: int = 0,
        bcc_percent: int = 0,
        on_status: Callable[[str], Any] | None = None,
        on_finished: Callable[[], Any] | None = None,
    ) -> None:
        self.recipients = list(recipients)
        self.content_mgr = content_mgr
        self.smtp_mgr = smtp_mgr
        self.proxy_mgr = proxy_mgr
        self.stats = stats
        self.logger = logger

        self.cc_addrs = cc_addrs or []
        self.bcc_addrs = bcc_addrs or []
        self.cc_percent = max(0, min(100, cc_percent))
        self.bcc_percent = max(0, min(100, bcc_percent))

        self.on_status = on_status
        self.on_finished = on_finished

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

        self._thread: threading.Thread | None = None
        self._idx: int = 0
        self._save_counter: int = 0
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def paused(self) -> bool:
        return not self.pause_event.is_set()

    # ── управление ───────────────────────────────────────

    def start(self, delay: float = 5.0, jitter: float = 2.0) -> None:
        if self._running:
            return
        self.stop_event.clear()
        self.pause_event.set()
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, args=(delay, jitter), daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.pause_event.set()
        self._save_state()

    def pause(self) -> None:
        self.pause_event.clear()
        self.stats.pause()
        self._save_state()

    def resume(self) -> None:
        self.pause_event.set()
        self.stats.resume()

    # ── рабочий цикл ─────────────────────────────────────

    def _worker(self, delay: float, jitter: float) -> None:
        total = len(self.recipients)
        self.stats.start(total)
        self._emit("Sending started")

        while self._idx < total:
            if self.stop_event.is_set():
                self._emit("Stopped by user")
                break

            self.pause_event.wait()
            if self.stop_event.is_set():
                break

            rcpt = self.recipients[self._idx]
            tag = "[CONTROL] " if rcpt.is_control else ""

            # ── SMTP ──
            smtp_acc = self.smtp_mgr.get_next()
            if not smtp_acc:
                self._emit("No alive SMTP — stopping")
                break

            proxy = self.proxy_mgr.get_next()
            proxy_addr = f"{proxy.host}:{proxy.port}" if proxy else ""

            # ── Контент ──
            variables = {
                "email": rcpt.email,
                "name": rcpt.name or rcpt.email.split("@")[0],
                "senderName": "",
            }
            sender_name = self.content_mgr.get_random_sender_name()
            variables["senderName"] = sender_name

            link_cache = {} if self.content_mgr.consistent_links else None

            try:
                subject = self.content_mgr.get_random_subject(
                    variables, link_cache=link_cache) or "(no subject)"
                body, is_html = self.content_mgr.get_random_body(
                    variables, link_cache=link_cache)
                if not body:
                    body, is_html = "(empty body)", False
            except ValueError as exc:
                self._emit(f"{tag}Content error: {exc}")
                self._record_error(rcpt, smtp_acc.email, proxy_addr, str(exc))
                self._idx += 1
                continue

            # ── CC / BCC (вероятностные) ──
            use_cc = bool(self.cc_addrs and random.randint(1, 100) <= self.cc_percent)
            use_bcc = bool(self.bcc_addrs and random.randint(1, 100) <= self.bcc_percent)
            actual_cc = self.cc_addrs if use_cc else None
            actual_bcc = self.bcc_addrs if use_bcc else None

            # ── Отправка ──
            try:
                msg = build_message(
                    smtp_acc.email, rcpt.email, subject, body, is_html,
                    sender_name, cc_addrs=actual_cc,
                )
                envelope_to = _envelope_recipients(
                    rcpt.email, cc_addrs=actual_cc, bcc_addrs=actual_bcc,
                )

                conn = connect_smtp(smtp_acc, proxy=proxy)
                try:
                    conn.sendmail(smtp_acc.email, envelope_to, msg.as_string())
                finally:
                    try:
                        conn.quit()
                    except Exception:
                        pass

                smtp_acc.sent_count += 1
                self.stats.record_sent(smtp_acc.email, proxy_addr)
                self.logger.log_send(
                    rcpt.email, smtp_acc.email, proxy_addr, subject, "sent",
                    control=rcpt.is_control,
                    had_cc=use_cc, had_bcc=use_bcc,
                )
                self._emit(f"{tag}✓ → {rcpt.email}")

            except Exception as exc:
                err_str = str(exc)
                smtp_code = getattr(exc, "smtp_code", 0)
                if smtp_code and smtp_code >= 500:
                    smtp_acc.status = SmtpStatus.DEAD
                    smtp_acc.last_error = err_str
                    self.stats.record_error(
                        smtp_acc.email, proxy_addr, smtp_dead=True)
                else:
                    self.stats.record_error(smtp_acc.email, proxy_addr)

                self.logger.log_send(
                    rcpt.email, smtp_acc.email, proxy_addr, subject,
                    "error", error_text=err_str, control=rcpt.is_control,
                    had_cc=use_cc, had_bcc=use_bcc,
                )
                self._emit(f"{tag}✗ → {rcpt.email}: {err_str[:80]}")

            # ── Прогресс ──
            self._idx += 1
            self._save_counter += 1
            if self._save_counter >= 15:
                self._save_state()
                self._save_counter = 0

            # ── Задержка ──
            actual_delay = max(0.5, delay + random.uniform(-jitter, jitter))
            if self.stop_event.wait(actual_delay):
                break

        self.stats.stop()
        self._running = False
        self._save_state()
        if self.on_finished:
            self.on_finished()

    # ── helpers ──────────────────────────────────────────

    def _emit(self, text: str) -> None:
        if self.on_status:
            self.on_status(text)

    def _record_error(self, rcpt: Recipient, smtp: str, proxy: str, err: str) -> None:
        self.stats.record_error(smtp, proxy)
        self.logger.log_send(
            rcpt.email, smtp, proxy, "", "error",
            error_text=err, control=rcpt.is_control,
        )

    def _save_state(self) -> None:
        remaining = self.recipients[self._idx:]
        save_queue_state(remaining, self._idx, len(self.recipients))
