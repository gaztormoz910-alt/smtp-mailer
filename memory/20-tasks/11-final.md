# Задача 11 — CC/BCC, Пресеты, Лаунчеры (ФИНАЛ)

## CC / BCC

### Логика
- На каждое письмо бросается `random.randint(1, 100) <= percent`.
- Если выпало — CC/BCC адреса добавляются.
- CC → в заголовок `msg["Cc"]` + в `envelope_to`.
- **BCC → ТОЛЬКО в `envelope_to`**, никогда в заголовки.

### Почему BCC нельзя в заголовки (КРИТИЧНО)
```python
# НЕПРАВИЛЬНО — основной получатель видит скрытые адреса:
msg["Bcc"] = "hidden@secret.com"

# ПРАВИЛЬНО — только в конверт:
envelope_to = [to_email] + cc_addrs + bcc_addrs
conn.sendmail(from_email, envelope_to, msg.as_string())
```

SMTP протокол разделяет «конверт» (кому реально доставить) и «содержимое» (что видит получатель).
BCC работает именно за счёт этого разделения: адрес есть в конверте, но отсутствует в headers.

### JSON-лог
```json
{"recipient": "user@mail.com", "status": "sent", "had_cc": true, "had_bcc": false}
```

## Пресеты

### Формат (data/presets/*.json)
```json
{
  "proxy_file": "C:/path/to/proxies.txt",
  "smtp_file": "C:/path/to/smtps.txt",
  "subjects_file": "C:/path/to/subjects.txt",
  "bodies_file": "C:/path/to/bodies.txt",
  "senders_file": "C:/path/to/senders.txt",
  "link_files": ["C:/path/to/links.txt", "C:/path/to/links1.txt"],
  "recipients_file": "C:/path/to/recipients.csv",
  "consistent_links": true,
  "email_only": false,
  "control_every_n": 100,
  "control_emails": "ctrl@gmail.com",
  "cc_addrs": "cc@mail.com",
  "cc_percent": 10,
  "bcc_addrs": "bcc@hidden.com",
  "bcc_percent": 5,
  "delay": 5,
  "jitter": 2
}
```

### Сохранение
`App.gather_full_preset()` собирает из всех вкладок (Setup, Content, Campaign, Send).

### Загрузка
`App.apply_full_preset(data)` применяет все настройки и перечитывает файлы.
Если файл не найден — предупреждение (messagebox), без краша.

## Лаунчеры
- `start.bat` — Windows: проверяет Python, `pip install -r`, запускает main.py
- `start.command` — macOS/Linux: `cd` в папку скрипта, `pip3 install -r`, `python3 main.py`

## Директории при старте
`main.py` создаёт `data/`, `data/presets/`, `logs/` автоматически.

## Build .exe
```bash
pyinstaller --onefile --windowed --name CharlyMailer main.py
```

## Файлы задачи 11
| Файл | Действие |
|---|---|
| `core/sender.py` | CC/BCC в build_message + CampaignSender |
| `core/logger.py` | had_cc/had_bcc в log_send |
| `core/presets.py` | новый — save/load JSON |
| `gui/tab_campaign.py` | CC/BCC поля + пресеты |
| `gui/tab_send.py` | campaign_tab wiring CC/BCC |
| `gui/window.py` | gather/apply_full_preset |
| `gui/tab_setup.py` | path tracking |
| `gui/tab_content.py` | path tracking |
| `main.py` | создание директорий |
| `start.bat` | Windows launcher |
| `start.command` | macOS launcher |
| `README.md` | полная документация |
