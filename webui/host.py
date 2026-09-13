"""pywebview-хост нового веб-интерфейса SMTP MAILER (стек как в email-validator:
pywebview + HTML/CSS/JS фронтенд, Python-бэкенд через мост js_api).

Класс Api — это и есть мост: его методы вызываются из JavaScript как
`window.pywebview.api.<метод>(...)` и возвращают JSON-совместимые словари.
Единые менеджеры (прокси/SMTP/контент/статистика) живут здесь — состояние общее
для всех вкладок, как в старом окне. Импорт этого модуля НЕ запускает окно
(webview.start() вызывается только в main()), поэтому мост тестируется headless.

Долгие операции (проверка прокси/SMTP, сама рассылка) НЕ блокируют вызов моста:
и check_all, и CampaignSender сами поднимают фоновые потоки и сразу возвращают
управление. Прогресс складывается в защищённые локом словари, а фронт опрашивает
его короткими вызовами (check_progress/campaign_state). Так вызов моста никогда
не «висит», а GUI-поток остаётся отзывчивым.
"""
from __future__ import annotations

import html as _html
import re
import threading
import time
from pathlib import Path
from random import SystemRandom
from typing import Any

import webview

from core.content import (
    ContentManager,
    render as render_body, is_html as is_html_body, html_to_plain_text,
)
from core.proxy_manager import ProxyManager, ProxyStatus, set_user_smtp_targets
from core.smtp_manager import SmtpManager, SmtpStatus
from core.stats import SendStats
from core.logger import JsonLogger
from core.queue_manager import (
    load_recipients as _load_recipients, build_queue, Recipient,
)
from core.sender import (
    CampaignSender, send_test as _send_test,
    load_queue_state, clear_queue_state,
)

WEB_DIR = Path(__file__).resolve().parent / "web"
_rnd = SystemRandom()

# Диалог выбора файлов: одни и те же типы для всех загрузок данных.
_FILE_TYPES = ("Данные (*.txt;*.csv;*.html)", "Все файлы (*.*)")

# Enum-статус → строковый токен для бейджей во фронте (JSON-safe, без утечки Enum).
_PROXY_TOKEN = {ProxyStatus.ALIVE: "alive", ProxyStatus.DEAD: "dead", ProxyStatus.UNTESTED: "untested"}
_SMTP_TOKEN = {SmtpStatus.ALIVE: "alive", SmtpStatus.DEAD: "dead", SmtpStatus.UNTESTED: "untested"}


def _split_emails(raw: str) -> list[str]:
    # CC/BCC/контрольные адреса вводятся строкой; режем по запятой/;/пробелам и
    # оставляем только то, что похоже на email (иначе мусор уедет в конверт).
    if not raw:
        return []
    return [e.strip() for e in re.split(r"[,\s;]+", raw) if e.strip() and "@" in e]


def _to_int(v: Any, default: int = 0) -> int:
    # Устойчивый разбор целого из ввода UI: «0впук», пустая строка, None → не крашим,
    # а берём первое число или дефолт. Иначе int('0впук') роняет весь мост.
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        m = re.search(r"-?\d+", str(v if v is not None else ""))
        return int(m.group()) if m else default


def _to_float(v: Any, default: float = 0.0) -> float:
    s = str(v if v is not None else "").strip().replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group()) if m else default


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many


def _senders(n: int) -> str:
    return f"{n} " + _plural(n, "отправитель", "отправителя", "отправителей")


def _emails(n: int) -> str:
    return f"{n} " + _plural(n, "письмо", "письма", "писем")


def _verb(n: int) -> str:
    # Согласование глагола с числом отправителей: «1 отправитель разошлёт»,
    # «2 отправителя разошлют».
    return "разошлёт" if (n % 10 == 1 and n % 100 != 11) else "разошлют"


# Размер страницы по умолчанию. Фронт запрашивает у моста ТОЛЬКО текущую страницу,
# поэтому и передача через мост, и DOM остаются лёгкими на любом объёме данных
# (хоть 10, хоть миллион строк). Полные данные при этом лежат в менеджерах целиком.
_PAGE = 200


def _win(total: int, offset: Any, limit: Any) -> tuple[int, int]:
    # Нормализуем окно [offset, offset+limit) под фактический размер списка.
    off = max(0, min(int(offset or 0), total))
    lim = int(limit) if limit else _PAGE
    if lim <= 0:
        lim = _PAGE
    return off, lim


class Api:
    def __init__(self) -> None:
        self.proxy_mgr = ProxyManager()
        self.smtp_mgr = SmtpManager()
        self.content_mgr = ContentManager()
        self.stats = SendStats()
        self.logger = JsonLogger()
        self._recipients: list[Recipient] = []

        # Прогресс проверки прокси/SMTP: фоновые колбэки пишут сюда, фронт опрашивает.
        self._chk: dict[str, dict] = {
            "proxies": {"running": False, "done": 0, "total": 0},
            "smtp": {"running": False, "done": 0, "total": 0},
        }
        self._chk_lock = threading.Lock()

        # Кэш счётчиков «всего/живых/мёртвых». Подсчёт живых/мёртвых — это проход по
        # всему пулу (O(n)); на миллионе прокси это ~0.1 c. Чтобы листание страниц и
        # опрос при проверке не пересчитывали миллион на каждый чих, держим кэш:
        # None = «грязный» (пересчитать), иначе отдаём готовое O(1). Во время проверки
        # кэш освежается не чаще раза в секунду (статусы всё равно меняются постепенно).
        self._counts_cache: dict[str, dict | None] = {"proxies": None, "smtp": None}
        self._counts_ts: dict[str, float] = {"proxies": 0.0, "smtp": 0.0}
        self._counts_lock = threading.Lock()

        # Рассылка: движок + кольцевой буфер живого лога.
        self._sender: CampaignSender | None = None
        self._log: list[str] = []
        self._log_lock = threading.Lock()

        # Конфиг кампании (CC/BCC/контроль) — задаётся с вкладки «Кампания».
        self._cfg: dict[str, Any] = {
            "cc": [], "bcc": [], "cc_pct": 0, "bcc_pct": 0,
            "control": [], "control_every_n": 0,
        }
        # ВАЖНО: не храним объект окна в Api. pywebview сериализует атрибуты
        # js_api для моста и уходит в бесконечную рекурсию по нативному .NET-объекту
        # окна (window.native.…), из-за чего зависает GUI. Активное окно берём
        # по месту через webview.active_window().

    # ── сервис ──────────────────────────────────────────────────────────
    def ping(self) -> dict:
        return {"ok": True, "app": "SMTP MAILER"}

    def status(self) -> dict:
        return {
            "subjects": self.content_mgr.subject_count,
            "bodies": self.content_mgr.body_count,
            "senders": self.content_mgr.sender_name_count,
            "links": sum(len(v) for v in self.content_mgr.link_pools.values()),
            "recipients": len(self._recipients),
            "proxies": self._proxy_counts(),  # из кэша — дёшево даже на миллионе
            "smtp": self._smtp_counts(),
        }

    # ── контент ─────────────────────────────────────────────────────────
    # Загрузка возвращает ТОЛЬКО счётчики (не весь массив), а содержимое фронт
    # берёт постранично через page_content — так мост не тащит миллион строк за раз.
    def load_subjects(self, paths: list[str]) -> dict:
        added = sum(self.content_mgr.load_subjects(p) for p in paths)
        return {"added": added, "total": self.content_mgr.subject_count}

    def clear_subjects(self) -> dict:
        self.content_mgr.clear_subjects()
        return {"total": 0}

    def load_bodies(self, paths: list[str]) -> dict:
        added = sum(self.content_mgr.load_bodies(p) for p in paths)
        return {"added": added, "total": self.content_mgr.body_count}

    def clear_bodies(self) -> dict:
        self.content_mgr.clear_bodies()
        return {"total": 0}

    def load_senders(self, paths: list[str]) -> dict:
        added = sum(self.content_mgr.load_sender_names(p) for p in paths)
        return {"added": added, "total": self.content_mgr.sender_name_count}

    def clear_senders(self) -> dict:
        self.content_mgr.clear_sender_names()
        return {"total": 0}

    def load_links(self, paths: list[str]) -> dict:
        files = []
        for p in paths:
            key, count, _mode = self.content_mgr.load_links_file(p)
            macro = f"[[LINK{key}]]" if key else "[[LINK]]"
            files.append({"file": Path(p).name, "macro": macro, "count": count})
        total = sum(len(v) for v in self.content_mgr.link_pools.values())
        return {"files": files, "total": total, "mode": self.content_mgr.link_mode}

    def clear_links(self) -> dict:
        self.content_mgr.clear_links()
        return {"files": [], "total": 0}

    def _page_links(self, offset: Any = 0, limit: Any = _PAGE) -> dict:
        # Ссылки хранятся пулами (dict макрос→список URL). Отдаём окно по всем пулам
        # подряд, не материализуя весь список: пулов мало, срез каждого — O(окна).
        pools = self.content_mgr.link_pools
        order = sorted(pools.keys(), key=lambda k: int(k) if k.isdigit() else 0)
        total = sum(len(pools[k]) for k in order)
        off, lim = _win(total, offset, limit)
        out: list[str] = []
        idx, start, end = 0, off, off + lim
        for k in order:
            urls = pools[k]
            n = len(urls)
            if idx + n <= start:
                idx += n
                continue
            if idx >= end:
                break
            a = max(start, idx) - idx
            b = min(end, idx + n) - idx
            out.extend(urls[a:b])
            idx += n
        legend = " · ".join(
            f"{('[[LINK' + k + ']]') if k else '[[LINK]]'} ({len(pools[k])})" for k in order)
        return {"kind": "links", "total": total, "offset": off, "limit": lim,
                "text": "\n".join(out) or "(пусто)", "legend": legend}

    def page_content(self, kind: str, offset: Any = 0, limit: Any = _PAGE) -> dict:
        # Возвращает ТОЛЬКО текущую страницу содержимого (темы/тела/имена/ссылки).
        cm = self.content_mgr
        if kind == "links":
            return self._page_links(offset, limit)
        if kind == "subjects":
            total = cm.subject_count
            off, lim = _win(total, offset, limit)
            text = "\n".join(cm.slice_lines("subjects", off, lim))
        elif kind == "senders":
            total = cm.sender_name_count
            off, lim = _win(total, offset, limit)
            text = "\n".join(cm.slice_lines("senders", off, lim))
        elif kind == "bodies":
            total = cm.body_count
            off, lim = _win(total, offset, limit)
            # По каждому телу — первая строка (заголовок блока), считаем по окну.
            text = "\n".join((b.splitlines()[0] if b else "")
                             for b in cm.slice_lines("bodies", off, lim))
        else:
            total, off, lim, text = 0, 0, _PAGE, ""
        return {"kind": kind, "total": total, "offset": off, "limit": lim,
                "text": text or "(пусто)"}

    def set_consistent_links(self, value: bool) -> dict:
        self.content_mgr.consistent_links = bool(value)
        return {"ok": True}

    def set_email_only(self, value: bool) -> dict:
        self.content_mgr.email_only = bool(value)
        return {"ok": True}

    # ── счётчики (всего/живых/мёртвых) с кэшем ──────────────────────────
    def _counts(self, kind: str) -> dict:
        mgr = self.proxy_mgr if kind == "proxies" else self.smtp_mgr
        with self._chk_lock:
            running = self._chk[kind]["running"]
        with self._counts_lock:
            cached = self._counts_cache.get(kind)
            fresh_enough = cached is not None and not (
                running and time.time() - self._counts_ts.get(kind, 0.0) > 1.0)
            if fresh_enough:
                return dict(cached)
        # Пересчёт вне лока кэша (сам проход берёт лок менеджера).
        total, alive, dead = mgr.counts()
        c = {"total": total, "alive": alive, "dead": dead}
        with self._counts_lock:
            self._counts_cache[kind] = c
            self._counts_ts[kind] = time.time()
        return dict(c)

    def _dirty_counts(self, kind: str) -> None:
        # Пометить кэш «грязным» после изменения пула (загрузка/очистка/удаление),
        # чтобы следующий запрос пересчитал точные счётчики.
        with self._counts_lock:
            self._counts_cache[kind] = None

    # ── прокси ──────────────────────────────────────────────────────────
    def _demote_blacklisted(self, entry) -> None:
        # Политика владельца: «Живой» = жив И НЕ в блоклисте. Живой прокси, попавший
        # в DNSBL (blacklist_clean is False), для рассылки бесполезен (письма улетят в
        # спам), поэтому помечаем его МЁРТВЫМ. Неизвестный блоклист (None — проверка не
        # удалась) и чистый (True) статус живого не трогаем.
        if entry is not None and entry.status == ProxyStatus.ALIVE \
                and entry.blacklist_clean is False:
            entry.status = ProxyStatus.DEAD

    def _proxy_item(self, p) -> dict:
        return {
            "addr": f"{p.host}:{p.port}",
            "proto": p.protocol,
            "status": _PROXY_TOKEN.get(p.status, "untested"),
            "ping": p.ping_ms,
            "country": p.country or "",
            "blacklist": p.blacklist_clean,  # True/False/None
            "score": p.score,
        }

    def _proxy_counts(self) -> dict:
        return self._counts("proxies")

    def page_proxies(self, offset: Any = 0, limit: Any = _PAGE) -> dict:
        # Счётчики + окно элементов + прогресс проверки за один вызов. Срез пула —
        # O(размера страницы), поэтому отдаётся мгновенно даже на миллионе прокси.
        total = self.proxy_mgr.count_total
        off, lim = _win(total, offset, limit)
        items = [self._proxy_item(p) for p in self.proxy_mgr.slice(off, lim)]
        with self._chk_lock:
            chk = dict(self._chk.get("proxies", {}))
        return {**self._proxy_counts(), "offset": off, "limit": lim, "items": items,
                "running": chk.get("running", False), "done": chk.get("done", 0)}

    def load_proxies(self, paths: list[str]) -> dict:
        added = sum(self.proxy_mgr.load_from_file(p) for p in paths)
        self._dirty_counts("proxies")
        return {"added": added, **self._proxy_counts()}

    def load_proxies_url(self, url: str) -> dict:
        added = self.proxy_mgr.load_from_url(url)
        self._dirty_counts("proxies")
        return {"added": added, **self._proxy_counts()}

    def clear_proxies(self) -> dict:
        self.proxy_mgr.clear()
        self._dirty_counts("proxies")
        return self._proxy_counts()

    def remove_dead_proxies(self) -> dict:
        removed = self.proxy_mgr.remove_dead()
        self._dirty_counts("proxies")
        return {"removed": removed, **self._proxy_counts()}

    def check_proxies(self, threads: Any = None, timeout: Any = None) -> dict:
        with self._chk_lock:
            if self._chk["proxies"]["running"]:
                return {"busy": True}
            total = self.proxy_mgr.count_total
            if total == 0:
                return {"empty": True}
            self._chk["proxies"] = {"running": True, "done": 0, "total": total}
        workers = _clamp(_to_int(threads, 30) or 30, 1, 2000)
        _t = _to_float(timeout, 0.0)
        to = _t if _t > 0 else None
        # Перед ПЕРЕпроверкой стираем прошлые результаты: все прокси → «не пров.»,
        # обнуляем пинг/страну/блоклист. Иначе на экране во время новой проверки висят
        # СТАРЫЕ вердикты и переписываются по одному (эффект «был Живой → стал Мёртвый»).
        # Теперь сразу чистый лист, затем заполняется свежими результатами.
        self.proxy_mgr.reset_all()
        self._dirty_counts("proxies")
        # Проверка прокси гоняет TCP до реальных SMTP-хостов; добавляем хосты
        # пользовательских аккаунтов, чтобы «живой» прокси значил живой для НАШИХ серверов.
        set_user_smtp_targets(self.smtp_mgr.accounts)

        def on_prog(done: int, total: int, entry) -> None:
            # Живой-но-в-блоклисте сразу понижаем до мёртвого (по ходу проверки).
            self._demote_blacklisted(entry)
            with self._chk_lock:
                self._chk["proxies"]["done"] = done
                self._chk["proxies"]["total"] = total

        def on_done() -> None:
            with self._chk_lock:
                self._chk["proxies"]["running"] = False
            self._dirty_counts("proxies")  # точные финальные счётчики

        self.proxy_mgr.check_all(max_workers=workers, on_progress=on_prog,
                                on_done=on_done, timeout=to)
        return {"started": True, "total": total, "threads": workers, "timeout": to or 10}

    # ── SMTP ────────────────────────────────────────────────────────────
    def _smtp_item(self, a) -> dict:
        return {
            "host": f"{a.host}:{a.port}",
            "email": a.email,
            "enc": a.encryption,
            "status": _SMTP_TOKEN.get(a.status, "untested"),
            "ping": a.ping_ms,
            "error": a.last_error or "",
            "bound_proxy": bool(getattr(a, "bound_proxy", None)),
        }

    def _smtp_counts(self) -> dict:
        return self._counts("smtp")

    def page_smtp(self, offset: Any = 0, limit: Any = _PAGE) -> dict:
        total = self.smtp_mgr.count_total
        off, lim = _win(total, offset, limit)
        items = [self._smtp_item(a) for a in self.smtp_mgr.slice(off, lim)]
        with self._chk_lock:
            chk = dict(self._chk.get("smtp", {}))
        return {**self._smtp_counts(), "offset": off, "limit": lim, "items": items,
                "running": chk.get("running", False), "done": chk.get("done", 0)}

    def load_smtp(self, paths: list[str]) -> dict:
        added = sum(self.smtp_mgr.load_from_file(p) for p in paths)
        self._dirty_counts("smtp")
        return {"added": added, **self._smtp_counts()}

    def clear_smtp(self) -> dict:
        self.smtp_mgr.clear()
        self._dirty_counts("smtp")
        return self._smtp_counts()

    def remove_dead_smtp(self) -> dict:
        removed = self.smtp_mgr.remove_dead()
        self._dirty_counts("smtp")
        return {"removed": removed, **self._smtp_counts()}

    def check_smtp(self, threads: Any = None, timeout: Any = None) -> dict:
        with self._chk_lock:
            if self._chk["smtp"]["running"]:
                return {"busy": True}
            total = self.smtp_mgr.count_total
            if total == 0:
                return {"empty": True}
            self._chk["smtp"] = {"running": True, "done": 0, "total": total}
        workers = _clamp(_to_int(threads, 30) or 30, 1, 2000)
        _t = _to_int(timeout, 0)
        to = _t if _t > 0 else None
        # Перед ПЕРЕпроверкой стираем прошлые результаты: все аккаунты → «не пров.»,
        # обнуляем пинг и текст ошибки. Чистый лист, затем свежие результаты — без
        # эффекта «висел старый вердикт и сменился на новый».
        self.smtp_mgr.reset_all()
        self._dirty_counts("smtp")

        def on_prog(done: int, total: int, _entry) -> None:
            with self._chk_lock:
                self._chk["smtp"]["done"] = done
                self._chk["smtp"]["total"] = total

        def on_done() -> None:
            with self._chk_lock:
                self._chk["smtp"]["running"] = False
            self._dirty_counts("smtp")  # точные финальные счётчики

        # Аккаунты проверяются через общий пул прокси, если он есть (как в рассылке).
        # soft_retries: мягкий отказ логина (репутация/политика/троттлинг) — это про НАШ
        # выход, а не про пароль. Повторяем через ДРУГОЙ прокси до 2 раз, прежде чем
        # оставить «не пров.» — чтобы аккаунт не «умирал» из-за плохого прокси.
        getter = self.proxy_mgr.get_next if self.proxy_mgr.count_alive else None
        self.smtp_mgr.check_all(proxy_getter=getter, max_workers=workers,
                               on_progress=on_prog, on_done=on_done, timeout=to,
                               soft_retries=2 if getter else 0)
        return {"started": True, "total": total, "threads": workers, "timeout": to or 15}

    def check_progress(self, kind: str) -> dict:
        # Прогресс проверки + актуальные счётчики (без массива элементов — их фронт
        # берёт постранично через page_proxies/page_smtp, чтобы не тащить весь список).
        with self._chk_lock:
            st = dict(self._chk.get(kind, {"running": False, "done": 0, "total": 0}))
        counts = self._proxy_counts() if kind == "proxies" else self._smtp_counts()
        st.update(counts)
        return st

    # ── база получателей ────────────────────────────────────────────────
    def load_recipients(self, paths: list[str]) -> dict:
        recs: list[Recipient] = []
        for p in paths:
            recs.extend(_load_recipients(p))
        self._recipients = recs
        # Возвращаем только счётчик; строки базы фронт берёт постранично.
        return {"total": len(recs), "added": len(recs)}

    def page_recipients(self, offset: Any = 0, limit: Any = _PAGE) -> dict:
        total = len(self._recipients)
        off, lim = _win(total, offset, limit)
        rows = [{"email": r.email, "name": r.name}
                for r in self._recipients[off:off + lim]]
        return {"total": total, "offset": off, "limit": lim, "rows": rows}

    def clear_recipients(self) -> dict:
        self._recipients = []
        return {"total": 0}

    # ── превью письма (как charly.cash/letter-preview) ──────────────────
    def preview_email(self, opts: dict | None = None) -> dict:
        opts = opts or {}
        name = (opts.get("name") or "").strip() or "Анна"
        email = (opts.get("email") or "").strip() or "recipient@example.com"

        sender_name = self.content_mgr.get_random_sender_name()
        variables = {"email": email, "name": name, "senderName": sender_name}

        if self.smtp_mgr.count_alive:
            from_email = self.smtp_mgr.get_next().email
        elif self.smtp_mgr.count_total:
            from_email = self.smtp_mgr.accounts[0].email
        else:
            from_email = "sender@example.com"

        link_cache = {} if self.content_mgr.consistent_links else None

        # Тема
        try:
            subject = self.content_mgr.get_random_subject(variables, link_cache=link_cache) \
                or "(темы не загружены)"
        except ValueError as exc:
            subject = f"(ошибка тем: {exc})"

        # Тело: можно указать конкретный индекс, иначе случайное.
        bodies = self.content_mgr.bodies
        if not bodies:
            body, is_html_flag = "Тела писем ещё не загружены — загрузите их во вкладке «Контент».", False
        else:
            idx = opts.get("index", -1)
            template = bodies[idx] if isinstance(idx, int) and 0 <= idx < len(bodies) \
                else _rnd.choice(bodies)
            pools = self.content_mgr.link_pools or None
            try:
                body = render_body(template, variables, pools, link_cache,
                                   link_mode=self.content_mgr.link_mode)
                is_html_flag = is_html_body(body)
            except ValueError as exc:
                body, is_html_flag = f"(ошибка ссылок: {exc})", False

        if is_html_flag:
            body_html = body
            text = html_to_plain_text(body)
        else:
            text = body
            body_html = ("<pre style=\"white-space:pre-wrap;margin:0;"
                         "font:14px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif;"
                         "color:#1a1a1a\">" + _html.escape(body) + "</pre>")

        preheader = " ".join(text.split())[:120]
        metrics = {
            "html_size": len(body_html.encode("utf-8")),
            "text_len": len(text.strip()),
            "links": len(re.findall(r"href\s*=", body_html, re.I)) if is_html_flag
                     else len(re.findall(r"https?://", text)),
            "images": len(re.findall(r"<img\b", body_html, re.I)),
        }
        return {
            "from_name": sender_name, "from_email": from_email,
            "subject": subject, "preheader": preheader,
            "html": body_html, "is_html": is_html_flag,
            "format": "HTML" if is_html_flag else "Обычный текст",
            "metrics": metrics,
            "bodies": len(bodies), "subjects": self.content_mgr.subject_count,
        }

    def body_titles(self) -> dict:
        # Список загруженных тел для выпадашки в превью (первая строка как заголовок).
        titles = []
        for i, b in enumerate(self.content_mgr.bodies):
            first = (b.splitlines()[0] if b else "").strip()
            titles.append({"index": i, "title": (first[:60] or f"Тело #{i + 1}")})
        return {"items": titles}

    # ── план распределения ──────────────────────────────────────────────
    def plan(self) -> dict:
        accs_alive = [a for a in self.smtp_mgr.accounts if a.status == SmtpStatus.ALIVE]
        alive = len(accs_alive)
        total = len(self._recipients)
        rows: list[dict] = []
        threads, per_conn = alive, 0

        if alive == 0:
            text = "Нет живых SMTP-аккаунтов. Загрузите и проверьте их во вкладке «Настройки»."
        elif total == 0:
            text = "Нет получателей. Загрузите базу во вкладке «Кампания»."
        elif alive >= total:
            # Писем меньше, чем аккаунтов: часть отправит по 1, остальные отдыхают.
            per_conn = 1
            for i, a in enumerate(accs_alive):
                rows.append({"email": a.email, "count": 1 if i < total else 0})
            rest = alive - total
            text = (f"{_senders(total)} отправят по 1 письму"
                    + (f", а {_senders(rest)} останутся без нагрузки." if rest else "."))
        else:
            # Формулировка как в прежней (понятной) версии: сколько отправителей и
            # по сколько писем разошлёт каждая группа — с правильными склонениями.
            base, rem = divmod(total, alive)
            per_conn = -(-total // alive)  # ceil — оптимум «писем на коннект»
            for i, a in enumerate(accs_alive):
                rows.append({"email": a.email, "count": base + (1 if i < rem else 0)})
            if rem == 0:
                if alive == 1:
                    text = f"1 отправитель разошлёт все {_emails(total)}."
                else:
                    text = f"{_senders(alive)} разошлют ровно по {_emails(base)}."
            else:
                g1 = f"{_senders(rem)} {_verb(rem)} по {_emails(base + 1)}"
                g2 = f"{_senders(alive - rem)} {_verb(alive - rem)} по {_emails(base)}"
                text = f"{g1}, а {g2}."
        return {"alive": alive, "total": total, "rows": rows, "text": text,
                "threads": threads, "per_conn": per_conn}

    # ── конфиг кампании (CC/BCC/контроль) ───────────────────────────────
    def set_campaign_config(self, cfg: dict | None = None) -> dict:
        cfg = cfg or {}
        self._cfg = {
            "cc": _split_emails(cfg.get("cc", "")),
            "bcc": _split_emails(cfg.get("bcc", "")),
            "cc_pct": _clamp(_to_int(cfg.get("cc_pct"), 0), 0, 100),
            "bcc_pct": _clamp(_to_int(cfg.get("bcc_pct"), 0), 0, 100),
            "control": _split_emails(cfg.get("control", "")),
            "control_every_n": max(0, _to_int(cfg.get("control_every_n"), 0)),
        }
        return {"ok": True, "cc": len(self._cfg["cc"]), "bcc": len(self._cfg["bcc"]),
                "control": len(self._cfg["control"])}

    # ── отправка ────────────────────────────────────────────────────────
    def send_test(self, email: str) -> dict:
        if not email or "@" not in email:
            return {"ok": False, "info": "Укажите корректный email"}
        ok, info = _send_test(email, self.content_mgr, self.smtp_mgr,
                              self.proxy_mgr, self.logger)
        return {"ok": ok, "info": info}

    def _log_push(self, msg: str) -> None:
        with self._log_lock:
            self._log.append(time.strftime("%H:%M:%S ") + msg)
            if len(self._log) > 500:
                del self._log[:-500]

    def start_campaign(self, params: dict | None = None) -> dict:
        params = params or {}
        if self._sender and self._sender.running:
            return {"error": "Рассылка уже идёт"}
        if not self._recipients:
            return {"error": "Нет получателей — загрузите базу"}
        if self.smtp_mgr.count_alive == 0:
            return {"error": "Нет живых SMTP — проверьте аккаунты"}

        cfg = self._cfg
        queue = build_queue(self._recipients, control_emails=cfg["control"],
                            control_every_n=cfg["control_every_n"])

        with self._log_lock:
            self._log.clear()

        self._sender = CampaignSender(
            queue, self.content_mgr, self.smtp_mgr, self.proxy_mgr,
            self.stats, self.logger,
            cc_addrs=cfg["cc"], bcc_addrs=cfg["bcc"],
            cc_percent=cfg["cc_pct"], bcc_percent=cfg["bcc_pct"],
            on_status=self._log_push,
        )
        # UI оставляет два регулятора: диапазон задержки «от A до B» и потоки (просьба
        # владельца — «и всё»). Мусорный ввод разбираем устойчиво, чтобы не ронять мост.
        #
        # Задержка: движок ждёт uniform[base-jitter, base+jitter] (domain_config.get_delay
        # при base>0), поэтому A..B ⇒ base=(A+B)/2, jitter=(B-A)/2. ПРОГРЕВ движка сохранён:
        # он домножает задержку на warmup ×3→×1 по мере отправки — в начале письма идут
        # медленнее (инбокс), затем сходятся к A..B. Здесь движок не трогаем.
        a = max(0.0, _to_float(params.get("delay_min"), 2.0))
        b = max(0.0, _to_float(params.get("delay_max"), 8.0))
        if b < a:                      # терпим перепутанный порядок полей (от>до)
            a, b = b, a
        base = (a + b) / 2.0
        jit = (b - a) / 2.0
        # Потоки: не больше числа живых SMTP и не больше 50; 0/пусто ⇒ все живые (в пределах).
        alive = self.smtp_mgr.count_alive
        cap = min(alive, 50) if alive else 50
        th_in = _to_int(params.get("threads"), 0)
        max_threads = cap if th_in <= 0 else min(th_in, cap)
        self._sender.start(
            delay=base,
            jitter=jit,
            max_threads=max_threads,
            max_per_conn=0,   # авто-лимит по профилю домена (поле убрано из UI)
            max_per_acc=0,    # без лимита на аккаунт (поле убрано из UI)
        )
        return {"started": True, "queued": len(queue)}

    def pause_campaign(self) -> dict:
        if self._sender:
            self._sender.pause()
        return {"ok": True}

    def resume_campaign(self) -> dict:
        if self._sender:
            self._sender.resume()
        return {"ok": True}

    def stop_campaign(self) -> dict:
        if self._sender:
            self._sender.stop()
            self.stats.mark_stopped()
        return {"ok": True}

    def campaign_state(self) -> dict:
        snap = self.stats.snapshot
        with self._log_lock:
            log = list(self._log[-200:])
        running = bool(self._sender and self._sender.running)
        paused = bool(self._sender and self._sender.paused)
        return {"snapshot": snap, "log": log, "running": running, "paused": paused,
                "recipients": len(self._recipients),
                "alive_smtp": self.smtp_mgr.count_alive,
                "can_start": len(self._recipients) > 0 and self.smtp_mgr.count_alive > 0}

    # ── возобновление прерванной кампании ───────────────────────────────
    def queue_state(self) -> dict:
        data = load_queue_state()
        if not data:
            return {"exists": False}
        return {"exists": True, "remaining": len(data["remaining"]),
                "sent": data.get("sent_count", 0), "total": data.get("total", 0),
                "saved_at": data.get("saved_at", "")}

    def resume_from_state(self, params: dict | None = None) -> dict:
        data = load_queue_state()
        if not data:
            return {"error": "Нет сохранённого состояния"}
        self._recipients = list(data["remaining"])
        return self.start_campaign(params)

    def clear_state(self) -> dict:
        clear_queue_state()
        return {"ok": True}

    # ── UI-мост: выбор файлов через диалог, затем загрузка ───────────────
    def pick_and_load(self, kind: str) -> dict:
        loader = getattr(self, f"load_{kind}", None)
        if loader is None:
            return {"error": f"unknown kind: {kind}"}
        win = webview.active_window()
        if win is None:
            return {"error": "no window"}
        paths = win.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True, file_types=_FILE_TYPES)
        if not paths:
            return {"cancelled": True}
        try:
            return loader(list(paths))
        except Exception as exc:  # понятная ошибка во фронт, без краша
            return {"error": str(exc)}


def main() -> None:
    api = Api()
    webview.create_window(
        "SMTP MAILER",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1400,
        height=880,
        min_size=(1100, 720),
        background_color="#0a0a0a",
    )
    # Окно НЕ передаём в Api (иначе pywebview зациклится при сериализации моста).
    webview.start()


if __name__ == "__main__":
    main()
