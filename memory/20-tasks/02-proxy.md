# Задача 2 — Прокси

## Что реализовано
Модуль `core/proxy_manager.py` + визуальный фрейм «Proxy Configuration» на вкладке Setup.

## Загрузка прокси
- **Из файла** — `ProxyManager.load_from_file()` → `storage.load_lines()` → парсинг каждой строки.
- **По URL** — `ProxyManager.load_from_url()` → `storage.load_lines_from_url()` (HTTP GET + тот же парсинг).
- **Авто-обновление** — фоновый daemon-поток, перезагрузка по URL каждые N минут (`start_auto_refresh`).

## Парсинг форматов
Regex `_PROXY_RE` поддерживает:
1. `protocol://host:port`
2. `protocol://user:pass@host:port`
3. `host:port:user:pass`
4. `host:port`

Если протокол не указан → `http`.

## Многопоточная проверка
- `ProxyManager.check_all()` запускает **отдельный поток**, внутри которого `ThreadPoolExecutor` (до 30 воркеров) проверяет прокси параллельно.
- Каждый воркер делает GET на `api.ipify.org` через прокси с таймаутом 7 сек.
- Коллбэк `on_progress(checked, total, proxy)` вызывается после каждой проверки — GUI обновляет конкретную строку и счётчик без пересоздания списка.
- GUI-поток **не блокируется** — все обновления через `widget.after(0, ...)`.

## Ротация
`get_next()` — round-robin по живым прокси (статус `Alive`).

## GUI (tab_setup.py)
- Фрейм с тёмным фоном `#141414`, скруглённые углы, бордер.
- Кнопки: Load File, Load URL, Check All (акцент `#fbbf24`), Remove Dead, Clear All.
- Чекбокс авто-обновления + поле минут.
- `CTkScrollableFrame` со строками прокси: `[PROTO] host:port  Status`.
- Цвета статусов: Untested → серый, Alive → `#4ade80`, Dead → `#ef4444`.
- Строка статистики: Total | Alive | Dead | Untested.
- Строка последнего действия (success/error).
- Все кнопки блокируются на время проверки/загрузки.

## Файлы затронутые в задаче 2
| Файл | Действие |
|---|---|
| `gui/theme.py` | создан (палитра) |
| `gui/window.py` | обновлён (импорт из theme) |
| `gui/tab_setup.py` | переписан (proxy UI) |
| `core/storage.py` | реализован |
| `core/proxy_manager.py` | реализован |
| `core/logger.py` | реализован |
