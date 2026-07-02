# Задача 7 — Статистика и логирование

## Что реализовано
- `core/stats.py` — потокобезопасный `SendStats` (глобальные метрики + per-SMTP/per-proxy).
- `core/logger.py` — расширен: `log_send()`, `export_json()`, `export_csv()`.
- `gui/tab_stats.py` — дашборд с прогресс-баром, карточками метрик, таблицами, экспортом.

## Потокобезопасность (КРИТИЧНО)

### Проблема
CustomTkinter (Tk) — однопоточный. Вызов `widget.configure()` из рабочего потока → crash.

### Решение: Polling через `.after()`
```python
def _update_ui(self):
    snap = self.stats.snapshot       # атомарный dict, lock внутри
    self.status_label.configure(...)  # безопасно, мы в main thread
    self.parent.after(1000, self._update_ui)  # повтор через 1 сек
```

1. `SendStats.snapshot` — берёт `threading.Lock`, копирует все данные в dict, отдаёт.
2. GUI вызывает `_update_ui()` каждую секунду через `widget.after(1000, ...)`.
3. `_update_ui()` выполняется **в main-thread** Tk → безопасно обновляет виджеты.
4. Фоновые потоки (sender) вызывают только `stats.record_sent()` / `stats.record_error()`.

### Скорость и ETA
```
elapsed_min = (time.time() - start_time) / 60
speed = sent / elapsed_min                      # писем/мин
remaining = total - sent - errors
eta_min = remaining / speed                     # минут до конца
```

## Send-лог (JSON-lines)
Файл: `logs/YYYY-MM-DD_send.jsonl`. Одна строка = одно письмо:
```json
{"timestamp":"...","recipient":"...","smtp_used":"...","proxy_used":"...","subject":"...","status":"sent"}
```
При ошибке добавляется `"error_text":"..."`.

## Экспорт
- **JSON**: копирует `_send.jsonl` → `.json` (as-is).
- **CSV**: парсит каждую JSON-строку → `csv.DictWriter` с заголовками.
- Оба выполняются в фоновом потоке (`threading.Thread`) чтобы не вешать GUI.

## GUI дашборд
```
┌─ Status ─────────────────────────────────────────────┐
│  Idle                                                │
│  ▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0.0 %   │
├─ Metrics ────────────────────────────────────────────┤
│  ⚡ Speed   │  ⏱ ETA   │  ✓ Sent   │  ✗ Errors     │
│  0 /min    │  —       │  0        │  0             │
├─ Detail ─────────────────────────────────────────────┤
│ SMTP Accounts          │  Proxies                    │
│ Email|Sent|Err|Status  │  Address|Used|Err|Status    │
│ (scrollable)           │  (scrollable)               │
├─ Export ─────────────────────────────────────────────┤
│ [📥 Export JSON] [📥 Export CSV]                     │
└──────────────────────────────────────────────────────┘
```

## Файлы задачи 7
| Файл | Действие |
|---|---|
| `core/stats.py` | создан |
| `core/logger.py` | расширен (log_send, export_json, export_csv, warning) |
| `gui/tab_stats.py` | создан |
