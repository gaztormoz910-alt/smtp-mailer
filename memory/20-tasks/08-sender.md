# Задача 8 — Отправка писем (Sender)

## Что реализовано
- `core/sender.py` — build_message, send_test, generate_preview, CampaignSender, save/load state.
- `gui/tab_send.py` — тестовая отправка, campaign controls, resume dialog.
- `gui/window.py` — общие менеджеры для всех вкладок.

## MIME-сообщение
```python
msg = MIMEMultipart("alternative")
msg["From"] = "Sender Name <email@domain.com>"
msg["To"] = recipient
msg["Subject"] = rendered_subject
msg["Date"] = formatdate(localtime=True)      # антиспам
msg["Message-ID"] = make_msgid()               # уникальный ID
msg["MIME-Version"] = "1.0"
msg["X-Mailer"] = "SmtpMailer/1.0"
msg.attach(MIMEText(body, "html"|"plain", "utf-8"))
```

## Паузa / Стоп через threading.Event

### Два Event-а
```python
self.stop_event = threading.Event()    # set() = остановить
self.pause_event = threading.Event()   # set() = работать, clear() = пауза
self.pause_event.set()                 # изначально не на паузе
```

### Рабочий цикл
```python
while idx < total:
    if stop_event.is_set():
        break

    pause_event.wait()          # блокирует если clear() (пауза)
    if stop_event.is_set():     # проверить после разблокировки
        break

    # ... send email ...

    # прерываемая задержка (stop_event.wait вместо time.sleep)
    if stop_event.wait(actual_delay):
        break
```

**Почему `stop_event.wait(delay)` а не `time.sleep(delay)`:**
`time.sleep()` блокирует на всё время задержки — СТОП не сработает пока sleep не кончится.
`stop_event.wait(delay)` немедленно прерывается при `stop_event.set()`.

## Save State (возобновление после краша)

### Когда сохраняется
- Каждые 15 писем (`_save_counter >= 15`)
- При нажатии ПАУЗА
- При нажатии СТОП
- По завершению кампании

### Формат `data/queue-state.json`
```json
{
  "remaining": ["addr1@x.com", "addr2@x.com"],
  "sent_count": 142,
  "total": 500,
  "saved_at": "2026-06-30T14:23:15"
}
```

### Восстановление при запуске
`SendTab._check_resume_state()` проверяет файл через 500ms после старта.
Если найден → показывает `CTkToplevel` диалог:
- **Resume** → загружает `remaining` в `_recipients`
- **Discard** → удаляет файл

### Очистка
При успешном завершении кампании (`_on_campaign_done`) → `clear_queue_state()`.

## Общие менеджеры (window.py)
```python
class App(ctk.CTk):
    def __init__(self):
        self.proxy_mgr = ProxyManager()
        self.smtp_mgr = SmtpManager()
        self.content_mgr = ContentManager()
        self.stats = SendStats()

        # все вкладки получают одни и те же экземпляры
        self.tab_setup = SetupTab(..., proxy_mgr=self.proxy_mgr, smtp_mgr=self.smtp_mgr)
        self.tab_content = ContentTab(..., content_mgr=self.content_mgr)
        self.tab_send = SendTab(..., content_mgr=..., smtp_mgr=..., proxy_mgr=..., stats=...)
        self.tab_stats = StatsTab(..., stats=self.stats)
```

## Файлы задачи 8
| Файл | Действие |
|---|---|
| `core/sender.py` | создан |
| `gui/tab_send.py` | переписан |
| `gui/window.py` | переписан (shared managers) |
| `gui/tab_setup.py` | обновлён конструктор |
| `gui/tab_content.py` | обновлён конструктор |
