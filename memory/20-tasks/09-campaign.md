# Задача 9 — База получателей и Control Inject

## Что реализовано
- `core/queue_manager.py` — `Recipient`, загрузка CSV/TXT, `build_queue` с control inject.
- `gui/tab_campaign.py` — загрузка базы, превью, control inject настройки, build queue.
- `core/sender.py` — обновлён под `Recipient` (email/name/is_control).
- `gui/tab_send.py` — `set_recipients` принимает `list[Recipient]`.
- `gui/window.py` — `tab_campaign.on_queue_ready = tab_send.set_recipients`.

## Формат файлов
- **CSV:** обязательна колонка `email`, опционально `name`. Регистронезависимый поиск.
- **TXT:** одна строка — один email. Автоопределение по расширению `.csv` / `.txt`.

## Алгоритм Control Inject
```
Вход:  recipients = [r1..r500], control_emails = [c1, c2], N = 100
Выход: r1..r100, CTRL(c1), r101..r200, CTRL(c2), r201..r300, CTRL(c1), r301..r400, CTRL(c2), r401..r500
       ───────── ──────── ─────────── ──────── ───────────── ──────── ─────────── ──────── ──────────
       100 regular  1 ctrl   100 regular  1 ctrl   100 regular   1 ctrl  100 regular  1 ctrl  100 regular

Итого: 500 regular + 5 control = 505 total (при N=100 и 500 получателях)
```

Round-robin: `control_emails[ctrl_idx % len(control_emails)]`, `ctrl_idx` инкрементируется.

## Очистка save state при новой базе
При загрузке новой базы `clear_queue_state()` удаляет `data/queue-state.json`.

## Recipient dataclass
```python
@dataclass
class Recipient:
    email: str
    name: str = ""
    is_control: bool = False
```
- `to_dict()` / `from_dict()` — для сериализации в queue-state.json
- В send-логе: `control=True` если `is_control`
- В статусах: `[CONTROL] ✓ → email` для визуальной пометки

## Файлы задачи 9
| Файл | Действие |
|---|---|
| `core/queue_manager.py` | создан |
| `gui/tab_campaign.py` | переписан |
| `core/sender.py` | обновлён (Recipient) |
| `gui/tab_send.py` | обновлён (Recipient) |
| `gui/window.py` | обновлён (callback wiring) |
