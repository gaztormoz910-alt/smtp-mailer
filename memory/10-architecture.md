# 🏗️ Архитектура SMTP MAILER

> Актуальная карта всех модулей `core/` и `gui/`, потоки данных, многопоточность,
> пресеты и логирование. Обновлено по факту кода на 2026-09-12 (финальный аудит,
> см. [[daily/2026-09-12]]). Ранее заметка описывала более старое состояние —
> теперь синхронизирована с кодом.

---

## Карта модулей

### `core/` — ядро (без GUI)

| Модуль | Назначение |
|---|---|
| `storage.py` | Загрузка данных: `load_lines` (строки, игнор пустых и `#`), `load_lines_from_url` (HTTP GET), `load_blocks` (тела, разделитель `===END===`, срезает markdown-ограждения), `load_csv_rows` |
| `proxy_manager.py` | `ProxyEntry` + `ProxyManager`: парсинг 4 форматов, проверка живости **реальным TCP-тестом SMTP-серверов** через прокси, DNSBL, гео (ip-api/ipinfo), скоринг, round-robin, авто-обновление из URL |
| `smtp_manager.py` | `SmtpAccount` + `SmtpManager` + `connect_smtp`: формат `host:port:email:password`, туннель через PySocks, поддельный EHLO по домену, SSL/STARTTLS по порту, классификация ошибок, round-robin по живым. Поле `bound_proxy` — опц. привязка прокси к аккаунту |
| `content.py` | `ContentManager` + движок: `spin` (рекурсивный спинтакс), `substitute` (плейсхолдеры), `substitute_links` (`[[LINK]]`), `render`, `is_html`, `html_to_plain_text`; анти-спам трансформации (омоглифы, HTML-entities, CSS-шум, комментарии, zero-width); `subjects_preview_text`, `format_email_preview` |
| `queue_manager.py` | `Recipient` + загрузка базы CSV/TXT (email обязателен) + `build_queue` (control-инжект) + `preview_recipients` |
| `domain_config.py` | Профили отправки по группам доменов (Gmail/Outlook/Yahoo/AOL/iCloud/Zoho/GMX + дефолт): задержки, лимиты на коннект/час, порог прогрева. `get_delay`, `get_warmup_factor`, `get_max_per_conn`, `get_domain_group` |
| `sender.py` | `CampaignSender` (многопоточный движок), `build_message` (MIME, анти-фингерпринт заголовков), `send_test`, `generate_preview`, `resolve_delay`, сохранение/загрузка `queue-state.json` |
| `stats.py` | `SendStats` — потокобезопасные счётчики, per-SMTP (+ `last_activity`) и per-proxy метрики, `snapshot` (скорость, ETA, `started_at`, статусы RU, флаг `mark_stopped`) |
| `logger.py` | `JsonLogger` (singleton, асинхронный писатель): боевой лог `logs/YYYY-MM-DD.json` (JSON-lines, timestamp с `Z`), тест-лог `logs/test-log.json`, общий лог `.jsonl`, экспорт JSON/CSV |
| `presets.py` | `save_preset`/`load_preset` — пресеты кампании в `data/presets/*.json` |
| `countries.py` | `COUNTRIES_RU`: ISO-код → русское название (гео прокси) |

Пустые `core/__init__.py`, `gui/__init__.py` — маркеры пакетов.

### `gui/` — интерфейс (CustomTkinter, тёмная тема)

| Модуль | Назначение |
|---|---|
| `window.py` | Главное окно `App`: общие менеджеры, инжект во вкладки, колбэки, полный пресет, блокировка UI, пересчёт доступности СТАРТ при смене вкладки |
| `theme.py` | Палитра/шрифты (фон `#0a0a0a`, акцент `#4ade80`) |
| `validation.py` | Валидаторы Entry (float, int, percent 0–100, email, список email, URL) |
| `tab_setup.py` | «Настройки»: прокси + SMTP (загрузка, «Проверить все», карточки, пагинация, авто-проверка прокси перед стартом через `ensure_proxies_checked`) |
| `tab_content.py` | «Контент»: темы, тела, ссылки, имена (превью первых 5), превью развёрнутого тела, песочница |
| `tab_campaign.py` | «Кампания»: база (превью первых 5), CC/BCC + проценты, control-инжект, пресеты |
| `tab_plan.py` | «План»: `PlanTab` — распределение писем между живыми SMTP, авто-проставление потоков/лимита |
| `tab_send.py` | «Отправка»: тест, задержка/разброс/писем-в-минуту, СТАРТ (неактивна без базы+SMTP)/СТОП/ПАУЗА, предпросмотр, диалог возобновления |
| `tab_stats.py` | «Статистика»: прогресс-бар, плитки (Speed/ETA/Sent/Errors/В очереди + время), таблицы SMTP (с «Актив.») и прокси, экспорт |

### Скрипты в корне
`main.py` — точка входа (создаёт `data/`, `data/presets/`, `logs/`, патчит скроллбар, запускает `App`). `start.bat`/`start.command` — лаунчеры. `translate.py`, `scrape.py`, `test_ablock_fix.py` — утилиты/тест, не часть рантайма.

---

## Поток данных

1. `App` создаёт единые `ProxyManager`, `SmtpManager`, `ContentManager`, `SendStats` и раздаёт их вкладкам.
2. «Кампания» строит очередь `list[Recipient]` (+ control-инжект) → колбэк `on_queue_ready` → `SendTab.set_recipients`.
3. «Отправка» создаёт `CampaignSender`, запускает в daemon-потоке.
4. GUI — главный поток Tk; обновления из воркеров через `parent.after(0, …)`; тяжёлые проверки — `ThreadPoolExecutor`.
5. Остановка/пауза — `threading.Event`; задержки через `stop_event.wait(delay)` (отменяемый сон).

---

## Многопоточность

> GUI — в главном потоке. Вся тяжёлая работа — в daemon-потоках.

- `CampaignSender._worker_dispatcher` поднимает по одному воркеру на живой SMTP-аккаунт (лимит `max_threads`), все тянут из общей `queue.Queue`, перемешанной по доменам (`interleave_by_domain`).
- Разделяемое состояние под `threading.Lock`/`RLock`; `SendStats` атомарен; `JsonLogger` пишет из отдельного потока через очередь.
- Ошибки: `5xx` → аккаунт `DEAD`; прочее → коннект сброшен, получатель в очередь (до 3 ретраев).

---

## Логирование

- **Боевой лог**: `logs/YYYY-MM-DD.json` — JSON-lines, запись `{timestamp(Z), recipient, smtp_used, proxy_used, subject, status, error_text?, control?, had_cc?, had_bcc?}`.
- **Тест-лог**: `logs/test-log.json` — тестовые отправки отдельно (не в статистику/боевой лог).
- **Экспорт**: JSON (валидный массив) и CSV.

---

## Связанные документы
- [[00-overview]] — обзор и статус
- [[30-decisions]] — ключевые решения
- [[40-errors]] — журнал ошибок
- [[daily/2026-09-12]] — финал проекта
