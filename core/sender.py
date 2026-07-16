"""sender.py — движок отправки писем.

Формирование MIME (CC/BCC), тестовая отправка, цикл массовой рассылки
с ``threading.Event`` для stop/pause, сохранение прогресса.
"""

from __future__ import annotations

import html
import json
import queue
import random
import threading
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from collections import defaultdict
from itertools import zip_longest
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

import re
_STRIP_TAGS_RE = re.compile(r'<[^>]+>')
_WHITESPACE_RE = re.compile(r'\s+')
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s<)]+)\)')
_A_TAG_SPLIT_RE = re.compile(r'(<a\s[^>]+>.*?</a>)', re.IGNORECASE)
_RAW_URL_RE = re.compile(r'(https?://[^\s<]+)')

def interleave_by_domain(recipients: list[Recipient]) -> list[Recipient]:
    """Группирует получателей по домену и перемешивает их (Round-Robin),
    чтобы одинаковые домены не шли подряд."""
    by_domain = defaultdict(list)
    for r in recipients:
        domain = r.email.split("@")[-1].lower() if "@" in r.email else "unknown"
        by_domain[domain].append(r)
        
    # Сортируем списки доменов по убыванию длины для более равномерного распределения
    sorted_lists = sorted(by_domain.values(), key=len, reverse=True)
    
    # Zip longest берет по одному элементу из каждого списка доменов по очереди
    interleaved = []
    for group in zip_longest(*sorted_lists):
        for r in group:
            if r is not None:
                interleaved.append(r)
    return interleaved

def split_evenly(items: list[Recipient], n: int) -> list[list[Recipient]]:
    """Делит список получателей на N примерно равных частей."""
    if n <= 0:
        return [items]
    k, m = divmod(len(items), n)
    return [items[i * k + min(i, m) : (i + 1) * k + min(i + 1, m)] for i in range(n)]


# ── X-Mailer ротация (имитация реальных клиентов) ─────────

import string
import time as time_module

_MAILERS = [
    "Microsoft Outlook 16.0",
    "Mozilla Thunderbird 115.0",
    "Apple Mail (2.3774.200.91)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Postbox 7.0.61",
    "The Bat! 11.3",
    "eM Client 9.2",
    "Evolution 3.44.4",
    "KMail/5.20.3",
    "Pegasus Mail/4.73",
    "Foxmail 7.2.20.273",
]

_ZERO_WIDTH = ["\u200B", "\u200C", "\u200D", "\uFEFF"]

def inject_zero_width(text: str, is_html: bool = False) -> str:
    """Вставляет невидимые символы между буквами, не ломая HTML и пробелы."""
    if not text:
        return text
    rnd = random.SystemRandom()
    
    def _mutate_word(m: re.Match) -> str:
        word = m.group(0)
        if len(word) > 3 and rnd.random() < 0.3:
            insert_pos = rnd.randint(1, len(word) - 1)
            char = rnd.choice(_ZERO_WIDTH)
            return word[:insert_pos] + char + word[insert_pos:]
        return word

    if is_html:
        # Для HTML мутируем только текст ВНЕ тегов
        parts = re.split(r'(<[^>]*>)', text)
        for i in range(0, len(parts), 2):
            if parts[i]:
                parts[i] = re.sub(r'[A-Za-zА-Яа-яЁё]+', _mutate_word, parts[i])
        return "".join(parts)
    else:
        return re.sub(r'[A-Za-zА-Яа-яЁё]+', _mutate_word, text)

def generate_invisible_block() -> str:
    """Генерирует скрытый div со случайным текстом."""
    rnd = random.SystemRandom()
    styles = [
        "display:none;",
        "height:0;width:0;overflow:hidden;",
        "font-size:0px;color:#ffffff;",
        "opacity:0;position:absolute;left:-9999px;",
        "visibility:hidden;height:1px;",
    ]
    style = rnd.choice(styles)
    # Генерируем случайный набор слов (простой фейк)
    words = ["hello", "world", "project", "test", "update", "info", "data", "report", "check", "system"]
    fake_text = " ".join(rnd.choice(words) for _ in range(rnd.randint(5, 15)))
    return f'<div style="{style}">{fake_text}</div>'

def get_random_boundary() -> str:
    """Генерирует уникальный boundary для MIME."""
    rnd = random.SystemRandom()
    if rnd.random() < 0.5:
        # Стиль 1: ----=_Part_X_Y
        return f"----=_Part_{rnd.randint(1000,9999)}_{rnd.randint(100000,999999)}"
    else:
        # Стиль 2: ============_X==
        chars = "".join(rnd.choice(string.ascii_letters + string.digits) for _ in range(16))
        return f"==============_{chars}=="

def build_message(
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
    is_html: bool,
    sender_name: str = "",
    cc_addrs: list[str] | None = None,
    plain_text_only: bool = False,
) -> Any:
    """Формирует MIME с тотальной уникализацией."""
    rnd = random.SystemRandom()

    # 1. Мутация текста (Zero-width chars) — ТОЛЬКО в body, НЕ в subject!
    # Zero-width символы в Subject — это красный флаг для Gmail/Outlook.
    if rnd.random() < 0.7:
        body = inject_zero_width(body, is_html=is_html)

    # 2. Формирование структуры
    if plain_text_only:
        msg = MIMEText(body, "plain", "utf-8")
    else:
        msg = MIMEMultipart("alternative", boundary=get_random_boundary())
        
        plain_body = _STRIP_TAGS_RE.sub(' ', body) if is_html else body
        plain_body = _WHITESPACE_RE.sub(' ', plain_body).strip()
        
        if is_html:
            html_body = body
        else:
            html_body = html.escape(body).replace("\n", "<br>\n")
            html_body = _MD_LINK_RE.sub(r'<a href="\2">\1</a>', html_body)
            parts = _A_TAG_SPLIT_RE.split(html_body)
            for i in range(0, len(parts), 2):
                parts[i] = _RAW_URL_RE.sub(r'<a href="\1">\1</a>', parts[i])
            html_body = "".join(parts)
            
        # Отключаем невидимые блоки, так как Google (Gmail) их жестко пессимизирует (spam flag).
        # if rnd.random() < 0.8:
        #     html_body = generate_invisible_block() + html_body + generate_invisible_block()

        part_plain = MIMEText(plain_body, "plain", "utf-8")
        part_html = MIMEText(html_body, "html", "utf-8")
        
        # Динамический Content-Transfer-Encoding (email.mime.text делает base64 по умолчанию для utf-8)
        # Мы оставляем стандартный механизм email.mime, т.к. он сам выбирает base64
        
        # По RFC 2046 порядок ВСЕГДА должен быть от наименее сложного к наиболее сложному.
        # То есть СНАЧАЛА text/plain, а ЗАТЕМ text/html.
        # Если их поменять местами, мобильные клиенты (например, iOS/Android) отобразят plain text,
        # а спам-фильтры (особенно Gmail) моментально пометят письмо как спам за нарушение стандарта.
        msg.attach(part_plain)
        msg.attach(part_html)

    # 3. Форматирование отправителя (Строго по RFC)
    if sender_name:
        # formataddr корректно энкодит кириллицу
        msg["From"] = formataddr((sender_name, from_email))
    else:
        msg["From"] = from_email

    msg["To"] = to_email
    msg["Subject"] = subject
    
    # 4. Header Jitter
    # Date jitter: +/- 30 сек (было ±300 — слишком агрессивно, спам-фильтры ловят)
    jitter_sec = rnd.randint(-30, 30)
    jitter_time = time_module.time() + jitter_sec
    msg["Date"] = formatdate(timeval=jitter_time, localtime=True)

    sender_domain = from_email.split("@")[-1] if "@" in from_email else "localhost"
    msg["Message-ID"] = make_msgid(domain=sender_domain)

    # MIME-Version НЕ добавляем вручную — MIMEMultipart/MIMEText уже ставят его.
    # Дублирование MIME-Version — аномалия для спам-фильтров.

    msg["X-Mailer"] = rnd.choice(_MAILERS)

    # X-Priority, X-MSMail-Priority, Thread-Index УБРАНЫ:
    # Случайные значения этих заголовков — прямой спам-сигнал для Gmail/Outlook.

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
        self._retry_counts: dict[str, int] = {}  # email → retry count
        self._retry_lock = threading.Lock()
        self._max_retries = 3  # Максимум 3 попытки на одного получателя
        self._sent_atomic = 0  # Атомарный счётчик отправленных
        self._sent_lock = threading.Lock()  # Lock для sent_count

    @property
    def running(self) -> bool:
        return self._running

    @property
    def paused(self) -> bool:
        return not self.pause_event.is_set()

    # ── управление ───────────────────────────────────────

    def start(self, delay: float = 1.0, jitter: float = 0.5, max_threads: int = 0, 
              max_per_conn: int = 50, max_per_acc: int = 0) -> None:
        """Запускает многопоточную рассылку (Global Queue)."""
        if self._running:
            return
        self._running = True
        self.stop_event.clear()
        self.pause_event.set()
        self.stats.resume()

        threading.Thread(
            target=self._worker_dispatcher, args=(delay, jitter, max_threads, max_per_conn, max_per_acc), daemon=True,
        ).start()

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

    def _worker_dispatcher(self, delay: float, jitter: float, max_threads: int, max_per_conn: int, max_per_acc: int) -> None:
        total = len(self.recipients)
        self.stats.start(total)
        self._emit("Sending started (Multi-threaded)")

        alive_smtps = [a for a in self.smtp_mgr.accounts if a.status == SmtpStatus.ALIVE]
        if not alive_smtps:
            self._emit("No alive SMTP accounts — stopping")
            self.stats.stop()
            self._running = False
            if self.on_finished:
                self.on_finished()
            return

        num_workers = len(alive_smtps)
        if max_threads > 0:
            num_workers = min(num_workers, max_threads)
            
        self._emit(f"Spawning {num_workers} threads (Global Queue)...")

        # Domain Interleaving
        shuffled = interleave_by_domain(self.recipients)
        
        self.global_q = queue.Queue()
        for r in shuffled:
            self.global_q.put(r)

        # Start workers
        worker_threads = []
        
        # Shared state for limits
        self._acc_sent = defaultdict(int)
        self._acc_sent_lock = threading.RLock()
        
        # Shared lock for safe idx increment and state save
        state_lock = threading.Lock()
        
        def safe_save_progress():
            with state_lock:
                self._save_counter += 1
                if self._save_counter >= max(50, max_per_conn):
                    self._save_state()
                    self._save_counter = 0

        for i in range(num_workers):
            t = threading.Thread(
                target=self._smtp_worker_thread,
                args=(delay, jitter, max_per_conn, max_per_acc, safe_save_progress),
                daemon=True,
                name=f"SMTPWorker-{i+1}"
            )
            worker_threads.append(t)
            t.start()

        # Wait for all workers to finish
        for t in worker_threads:
            t.join()

        self.stats.stop()
        self._running = False
        self._save_state()
        if self.on_finished:
            self.on_finished()
            
    def _smtp_worker_thread(self, delay: float, jitter: float, max_per_conn: int, max_per_acc: int, on_progress: Callable) -> None:
        """Рабочий поток. Привязывается к конкретному SMTP аккаунту и обрабатывает адреса."""
        conn = None
        
        def get_valid_account() -> SmtpAccount | None:
            for _ in range(self.smtp_mgr.count_alive):
                acc = self.smtp_mgr.get_next()
                if not acc: return None
                if max_per_acc <= 0: return acc
                with self._acc_sent_lock:
                    if self._acc_sent[acc.email] < max_per_acc:
                        return acc
            return None
        
        # Получаем аккаунт и прокси ОДИН РАЗ при старте потока
        smtp_acc = get_valid_account()
        if not smtp_acc:
            return  # Нет живых аккаунтов для этого потока
            
        proxy = self.proxy_mgr.get_next()
        proxy_addr = f"{proxy.host}:{proxy.port}" if proxy else ""
        
        sent_on_conn = 0
        
        while True:
            if self.stop_event.is_set():
                break

            self.pause_event.wait()
            if self.stop_event.is_set():
                break

            try:
                rcpt = self.global_q.get(timeout=1.0)
            except queue.Empty:
                break
                
            # ── Check Account Limit ──
            if max_per_acc > 0:
                with self._acc_sent_lock:
                    if self._acc_sent[smtp_acc.email] >= max_per_acc:
                        new_acc = get_valid_account()
                        if not new_acc:
                            self.global_q.put(rcpt)
                            break
                        smtp_acc = new_acc
                        conn = None  # force reconnect
            
            # ── Connection Pooling ──
            if conn is None or (max_per_conn > 0 and sent_on_conn >= max_per_conn):
                if conn:
                    try:
                        conn.quit()
                    except Exception:
                        pass
                
                # При превышении лимита (max_per_conn) берем СЛЕДУЮЩИЙ аккаунт
                # Если отключим лимит (0), то будем шпарить до конца базы с одного
                if max_per_conn > 0 and sent_on_conn >= max_per_conn:
                    smtp_acc = get_valid_account()
                    if not smtp_acc:
                        self.global_q.put(rcpt)
                        break
                    proxy = self.proxy_mgr.get_next()
                    proxy_addr = f"{proxy.host}:{proxy.port}" if proxy else ""
                
                tag = f"{smtp_acc.email} "
                
                try:
                    conn = connect_smtp(smtp_acc, proxy=proxy)
                    sent_on_conn = 0
                except Exception as exc:
                    self._emit(f"{tag}Connect error: {exc}")
                    self.stats.record_error(smtp_acc.email, proxy_addr, smtp_dead=True)
                    self.global_q.put(rcpt)
                    conn = None
                    # Если умер при коннекте, сразу меняем аккаунт
                    smtp_acc = get_valid_account()
                    if not smtp_acc:
                        break
                    proxy = self.proxy_mgr.get_next()
                    proxy_addr = f"{proxy.host}:{proxy.port}" if proxy else ""
                    continue

            tag = f"{smtp_acc.email} "
            is_control = getattr(rcpt, "is_control", False)
            if is_control:
                tag = f"{tag}[CONTROL] "

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
                on_progress()
                self.global_q.task_done()
                continue

            # ── CC / BCC ──
            use_cc = bool(self.cc_addrs and random.SystemRandom().randint(1, 100) <= self.cc_percent)
            use_bcc = bool(self.bcc_addrs and random.SystemRandom().randint(1, 100) <= self.bcc_percent)
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

                conn.sendmail(smtp_acc.email, envelope_to, msg.as_string())
                
                sent_on_conn += 1
                with self._sent_lock:
                    smtp_acc.sent_count += 1
                if max_per_acc > 0:
                    with self._acc_sent_lock:
                        self._acc_sent[smtp_acc.email] += 1
                
                with self._sent_lock:
                    self._sent_atomic += 1
                
                self.stats.record_sent(smtp_acc.email, proxy_addr)
                self.logger.log_send(
                    rcpt.email, smtp_acc.email, proxy_addr, subject, "sent",
                    control=is_control,
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
                    conn = None 
                else:
                    self.stats.record_error(smtp_acc.email, proxy_addr)
                    conn = None

                self.logger.log_send(
                    rcpt.email, smtp_acc.email, proxy_addr, subject,
                    "error", error_text=err_str, control=is_control,
                    had_cc=use_cc, had_bcc=use_bcc,
                )
                self._emit(f"{tag}✗ → {rcpt.email}: {err_str[:80]}")
                
                # Retry с лимитом (макс. 3 попытки), а не бесконечно!
                with self._retry_lock:
                    retries = self._retry_counts.get(rcpt.email, 0)
                    if retries < self._max_retries:
                        self._retry_counts[rcpt.email] = retries + 1
                        self.global_q.put(rcpt)  # Вернуть в очередь
                    else:
                        self._emit(f"{tag}⚠ {rcpt.email}: исчерпаны попытки ({self._max_retries})")

            # ── Прогресс ──
            self.global_q.task_done()
            on_progress()

            # ── Индивидуальная задержка (Per-Thread) ──
            actual_delay = max(0.1, delay + random.SystemRandom().uniform(-jitter, jitter))
            self.stop_event.wait(actual_delay)
            
        # Cleanup
        if conn:
            try:
                conn.quit()
            except Exception:
                pass

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
        if not hasattr(self, "global_q"):
            return
        # Thread-safe копирование очереди
        remaining = []
        try:
            while True:
                try:
                    item = self.global_q.get_nowait()
                    remaining.append(item)
                except queue.Empty:
                    break
            # Вернуть элементы обратно
            for item in remaining:
                self.global_q.put(item)
        except Exception:
            pass
        with self._sent_lock:
            sent_count = self._sent_atomic
        save_queue_state(remaining, sent_count, len(self.recipients))
