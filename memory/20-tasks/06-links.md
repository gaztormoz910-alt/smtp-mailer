# Задача 6 — Ссылки (Links)

## Что реализовано
- `core/content.py` — пулы ссылок, макросы `[[LINK]]`/`[[LINK1]]`, consistent links.
- `gui/tab_content.py` — блок Links с мульти-файл загрузкой и чекбоксом.

## Макросы ссылок
| Макрос | Файл | Пример |
|---|---|---|
| `[[LINK]]` | `links.txt` | Основной оффер |
| `[[LINK1]]` | `links1.txt` | Лендинг 1 |
| `[[LINK2]]` | `links2.txt` | Партнёрка |

### Определение пула из имени файла
Regex `(\d+)$` применяется к stem файла:
- `links.txt` → stem `links` → нет цифр → ключ `""` → `[[LINK]]`
- `links1.txt` → stem `links1` → `"1"` → `[[LINK1]]`
- `links42.txt` → stem `links42` → `"42"` → `[[LINK42]]`

## Pipeline обработки
```
spin(template)  →  substitute_links(text, pools, cache)  →  substitute(text, vars)
```
Спинтакс раскрывается **перед** заменой ссылок — это гарантирует,
что `[[LINK]]` внутри `{opt_a [[LINK1]]|opt_b [[LINK2]]}` обработается корректно.

## Consistent Links
Чекбокс «Consistent links per email» (по умолчанию OFF).

- **OFF:** каждое вхождение `[[LINK]]` → **разная** случайная ссылка.
- **ON:** первое `[[LINK]]` → кешируется; все последующие `[[LINK]]`
  в том же письме (тема + тело) → **та же** ссылка.

Механизм: `link_cache = {}` создаётся перед генерацией одного письма
и передаётся в `render()` для темы и для тела.

## Защита от сбоев
Если в тексте найден макрос `[[LINK2]]`, а пул `"2"` пуст →
`ValueError("No links loaded for: [[LINK2]]")`.
Песочница ловит это и показывает ошибку красным.

## Файлы задачи 6
| Файл | Действие |
|---|---|
| `core/content.py` | расширен (link_pools, substitute_links, render, pool_key_from_filename) |
| `gui/tab_content.py` | переписан (добавлен блок Links, layout 3+1) |
