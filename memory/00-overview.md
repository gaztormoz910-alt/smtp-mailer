# SMTP MAILER — Overview (ПРОЕКТ ЗАВЕРШЁН И ОТЛАЖЕН ✅)

## Статус
**Все 12 задач выполнены. 5 багов исправлены. Готов к боевой рассылке.**

## Задачи
- [x] 1 — Каркас проекта, 5 вкладок (CTk dark theme)
- [x] 2 — Прокси: загрузка, проверка, ротация (SOCKS4/5, HTTP)
- [x] 3 — SMTP: PySocks-туннель, SSL/STARTTLS, round-robin
- [x] 4 — Темы: рекурсивный спинтакс {a|{b|c}}, макросы {{name}}
- [x] 5 — Тела: ===END===, авто HTML-детект
- [x] 6 — Ссылки: [[LINK]]/[[LINKN]], consistent links
- [x] 7 — Статистика: real-time дашборд, ETA, per-SMTP/proxy
- [x] 8 — Отправка: MIME, тест, СТАРТ/СТОП/ПАУЗА, save state
- [x] 9 — База получателей: CSV/TXT, control inject
- [x] 10 — Имена отправителей: formataddr (RFC 2047), email_only
- [x] 11 — CC/BCC (вероятностные), пресеты, лаунчеры, README
- [x] 12 — Полный аудит: 5 багов найдено и исправлено

## 14 ключевых функций
| # | Функция | Модуль |
|---|---------|--------|
| 1 | GUI (5 вкладок, dark theme) | gui/*.py |
| 2 | Менеджер прокси (SOCKS4/5/HTTP, авто-check, ротация) | core/proxy_manager.py |
| 3 | Менеджер SMTP (PySocks, SSL/STARTTLS, round-robin) | core/smtp_manager.py |
| 4 | Спинтакс (рекурсивный {a|{b|c}}) | core/content.py |
| 5 | Тела писем (===END===, HTML-детект) | core/content.py |
| 6 | Макросы ссылок ([[LINK]], consistent) | core/content.py |
| 7 | Имена отправителей (formataddr, RFC 2047) | core/content.py |
| 8 | База получателей (CSV/TXT) | core/queue_manager.py |
| 9 | Control Inject (round-robin каждые N) | core/queue_manager.py |
| 10 | CC/BCC (вероятностные, BCC в конверте) | core/sender.py |
| 11 | Антиспам (Message-ID с доменом, X-Mailer рандом) | core/sender.py |
| 12 | Real-time статистика (дашборд, ETA) | core/stats.py |
| 13 | Логирование + save state | core/logger.py, core/sender.py |
| 14 | Пресеты + лаунчеры | core/presets.py, start.bat |

## Антиспам-меры (для дейтинга критично)
- **Message-ID** содержит домен аккаунта (не hostname машины) → SPF/DKIM trust
- **X-Mailer** рандомизируется из пула реальных клиентов (Outlook, Thunderbird, Apple Mail)
- **From** через `formataddr` → корректный RFC 2047 для кириллицы
- **BCC** никогда не попадает в заголовки — только в envelope
- **SMTP connection cleanup** — try/finally, нет утечек сокетов
- **5xx → Dead** (аккаунт убирается из ротации)
- **Спинтакс** и рандомизация контента → уникальность каждого письма

## Запуск
```bash
pip install -r requirements.txt
python main.py
```
Или: `start.bat` (Windows) / `start.command` (macOS)

## Связанные файлы
- [[10-architecture]] — архитектура и потоки
- [[30-decisions]] — ключевые решения
- [[40-errors]] — журнал багов
- [[20-tasks/12-audit]] — финальный аудит
