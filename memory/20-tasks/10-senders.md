# Задача 10 — Имена отправителей (Sender Names)

## Что реализовано
- `core/content.py` — `load_sender_names()`, `get_random_sender_name()`, `email_only` флаг.
- `gui/tab_content.py` — блок «Sender Names» с чекбоксом, превью, layout 2×2 + sandbox.
- `core/sender.py` — `email.utils.formataddr` для заголовка `From`.

## Почему formataddr (КРИТИЧНО)

### Проблема
Имена могут содержать кириллицу, пробелы и спецсимволы:
```
Иван Петров
O'Brien & Associates
"Компания Рога и Копыта"
```

Наивная конкатенация `f"{name} <{email}>"` создаёт невалидный заголовок по RFC 2822,
что приводит к:
- Отправке в спам (антиспам-фильтры видят невалидный From)
- Крашам SMTP-серверов, которые строго проверяют заголовки
- Неправильному отображению в почтовых клиентах

### Решение
```python
from email.utils import formataddr

msg["From"] = formataddr(("Иван Петров", "smtp@domain.com"))
# → "=?utf-8?q?=D0=98=D0=B2=D0=B0=D0=BD_=D0=9F=D0=B5=D1=82=D1=80=D0=BE=D0=B2?= <smtp@domain.com>"
```

`formataddr` автоматически энкодит non-ASCII по RFC 2047 (Q-encoding / B-encoding).
Почтовые клиенты декодируют это обратно и показывают «Иван Петров».

## Чекбокс «Email only»
- `content_mgr.email_only = True` → `get_random_sender_name()` возвращает `""`.
- `build_message` получает пустое имя → `msg["From"] = from_email` (без обёртки).
- Макрос `{{senderName}}` заменяется на пустоту (удаляется из текста).

## Layout вкладки Content (2×2 + sandbox)
```
┌─ 📝 Subjects ──────┐  ┌─ 📄 Bodies ────────┐
│ [Load][Clear] N     │  │ [Load][Clear] N     │
│ Preview (5 lines)   │  │ Preview (8 lines)   │
├─ 🔗 Links ─────────┤  ├─ 👤 Sender Names ──┤
│ [Load Links][Clear] │  │ [Load][Clear] N     │
│ ☑ Consistent links  │  │ ☑ Email only        │
│ Loaded files list   │  │ Preview (5 names)   │
└─────────────────────┘  └─────────────────────┘
┌─ 🎲 Sandbox ────────────────────────────────┐
│ Email:[___] Name:[___]       [🎲 Generate]  │
│ Sender: Иван Петров                         │
│ Subject: ...                                │
│ Format: HTML                                │
│ ─────────────                               │
│ <html>...</html>                            │
└──────────────────────────────────────────────┘
```
