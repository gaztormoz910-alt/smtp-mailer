# Задача 5 — Тела писем (Bodies)

## Что реализовано
- `core/storage.py` — добавлен `load_blocks(filepath, separator="===END===")`.
- `core/content.py` — `ContentManager.load_bodies()`, `get_random_body()`, `is_html()`.
- `gui/tab_content.py` — переструктурирован: Subjects (верх-лево), Bodies (верх-право), Sandbox (низ).

## Формат файла bodies.txt
Каждое тело отделяется строкой `===END===` на отдельной строке:
```
{Привет|Здравствуйте}, {{name}}!
Это первое тело.
===END===
<html><body>
<p>{Hello|Hi} {{name}},</p>
<p>Second body (HTML).</p>
</body></html>
===END===
```

## Рекурсивный спинтакс (любая глубина)
Regex `\{([^{}]+)\}` — ищет самый **внутренний** блок (без вложенных `{}`).
Цикл `while` повторяет до полного раскрытия.

Пример с тройной вложенностью:
```
{a {b {c|d}|e}|f}
→ итерация 1: {c|d} → d → "{a {b d|e}|f}"
→ итерация 2: {b d|e} → b d → "{a b d|f}"
→ итерация 3: {a b d|f} → a b d
```

## Авто-определение HTML
Regex ищет теги: `<html>`, `<body>`, `<p>`, `<br>`, `<a href=`, `<div>`, `<table>` и др.
Если найден хотя бы один → `is_html = True`.
Используется для будущего формирования `MIMEText(text, "html")` vs `MIMEText(text, "plain")`.

## GUI layout вкладки Content
```
┌─── Subjects ──────────┐  ┌─── Bodies ────────────┐
│ [Load] [Clear] N      │  │ [Load] [Clear] N      │
│ Preview (raw 5 lines) │  │ Preview (first body)  │
└───────────────────────┘  └───────────────────────┘

┌─── 🎲 Test Sandbox (full width) ────────────────────┐
│ Email: [___] Name: [___] Sender: [___] [Generate]   │
│ ┌─ Combined preview ───────────────────────────────┐│
│ │ Subject: Hello John!                              ││
│ │ Format: HTML                                      ││
│ │ ──────────────────────────────────────────        ││
│ │ <html><body><p>Hi John...</p></body></html>       ││
│ └───────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

## Файлы задачи 5
| Файл | Действие |
|---|---|
| `core/storage.py` | добавлен `load_blocks()` |
| `core/content.py` | добавлены bodies, is_html() |
| `gui/tab_content.py` | переписан (3 секции) |
