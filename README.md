# Pinion

**Pinion** — десктопное Windows-приложение для массовых email-рассылок через пул
SMTP-аккаунтов и SOCKS-прокси. Интерфейс по умолчанию — веб (pywebview, тёмная
тема); сохранён и старый на CustomTkinter. Ниша контента — Dating / знакомства:
каждое письмо должно выглядеть как личное сообщение живого человека и довести
получателя до клика, не попав в спам.

---

## Установка (готовый .exe)

Скачать последнюю версию установщика (постоянная ссылка, всегда указывает на свежий релиз):

**[⬇ Pinion-setup.exe](releases/latest/download/Pinion-setup.exe)**

1. Скачайте `Pinion-setup.exe` и запустите двойным кликом.
2. При первом запуске Windows покажет синий экран **«Windows защитила ваш
   компьютер»** — это ожидаемо для любого установщика без платной цифровой
   подписи. Нажмите **Подробнее → Выполнить в любом случае**.
3. Программа ставится в профиль пользователя
   (`%LOCALAPPDATA%\Programs\Pinion`), **права администратора не нужны**.
   Python и все библиотеки уже внутри — ставить отдельно ничего не требуется.

Требования: **Windows 10/11, 64-bit**.

---

## Запуск из исходников

```bash
pip install -r requirements.txt
python main.py            # веб-интерфейс (pywebview) — по умолчанию
python main.py ctk        # старый интерфейс на CustomTkinter
```

Зависимости: `pywebview`, `pythonnet` (Windows-бэкенд pywebview), `customtkinter`,
`PySocks`, `requests`. Python 3.13.

Служебные режимы (headless-прогон ядра для CI/самопроверки, без окна):

```bash
python main.py --selftest selftest.log        # ядро + GUI-бэкенд (best-effort)
python main.py --selftest-core selftest.log   # только ядро, без GUI-импортов
```

При старте рядом с `.exe` (в сборке) или в корне исходников создаются каталоги
`data/`, `data/presets/`, `logs/` — путь считает `core/appenv.py`.

---

## Возможности

| Возможность | Описание |
|---|---|
| **Прокси** | SOCKS5 (HTTP/HTTPS принудительно → socks5), загрузка из файла/URL, авто-обновление; проверка живости = реальный TCP-тест SMTP-серверов через прокси + DNSBL + гео + скоринг |
| **SMTP-аккаунты** | `host:port:email:password` (гибкие разделители), туннелирование через PySocks, SSL (465) / STARTTLS (587) / PLAIN, поддельный EHLO, ротация round-robin |
| **Спинтакс** | Рекурсивный `{a|{b|c}}` любой вложенности в темах и телах |
| **Переменные** | `{{name}}`, `{{email}}`, `{{senderName}}` |
| **Ссылки** | Пулы `[[LINK]]`, `[[LINK1]]`…, режим единых ссылок, уникальный GET-параметр на каждую ссылку |
| **Макросы** | `[%%RndString(n)%%]`, `[%%RndNumber(lo,hi)%%]` |
| **Уникализация HTML** | Софт сам добавляет CSS-шум, реалистичные комментарии, вариацию пробелов в тегах. Омоглифы / entities / zero-width **убраны** (2026 — детектятся фильтрами как фишинг) |
| **Анти-фингерпринтинг** | Имитация реального клиента по домену: boundary, Message-ID, порядок заголовков, charset/кодировка, Date со сдвигом, вариация имени отправителя, Reply-To ~35% |
| **Многопоточная отправка** | Один воркер на живой аккаунт, общая очередь, перемешанная по доменам, профили задержек/лимитов по провайдеру + прогрев |
| **CC / BCC** | Вероятностные CC/BCC с настраиваемым процентом (BCC — только в envelope) |
| **Контрольные адреса** | Инъекция контрольных писем каждые N сообщений |
| **Статистика** | Дашборд в реальном времени, метрики per-SMTP / per-proxy, экспорт JSON/CSV |
| **Логи** | Структурные JSON-lines (общий + лог отправки), асинхронная запись |
| **Возобновление** | Продолжение прерванной кампании из `data/queue-state.json` |
| **Пресеты** | Сохранение/загрузка всех настроек кампании в JSON |

---

## Вкладки

1. **Настройки** — загрузка прокси и SMTP-аккаунтов, «Проверить все».
2. **Контент** — темы, тела, ссылки, имена отправителей + песочница-предпросмотр.
3. **Кампания** — база получателей, CC/BCC, control inject, пресеты, «Создать очередь».
4. **Отправка** — тестовое письмо, параметры скорости, СТАРТ/СТОП/ПАУЗА, возобновление.
5. **Статистика** — прогресс, карточки, таблицы SMTP/прокси, экспорт.

---

## Форматы входных файлов

### Прокси (`.txt`)
```
socks5://user:pass@host:port
socks5://host:port
host:port:user:pass
host:port
```
`#` — комментарий. HTTP/HTTPS автоматически переводятся в socks5 (для туннелирования SMTP нужен SOCKS).

### SMTP (`.txt`)
Формат `host:port:email:password` (пароль может содержать `:`; парсер также пробует
разделители `| ; ,` и таб). Шифрование по порту: 465 → SSL, 587 → STARTTLS, иначе PLAIN/STARTTLS.
```
smtp.gmail.com:587:user@gmail.com:password
mail.example.com:465:sender@example.com:secret
```

### Темы (`subjects.txt`)
Один спинтакс-шаблон на строку:
```
{Привет|Здравствуй} {{name}}, {это ты|тебя искал}?
```

### Тела (`bodies.txt` / `.html`)
Блоки, разделённые строкой `===END===`; HTML/plain определяется автоматически;
markdown-ограждения ``` срезаются.
```html
<html><body><p>Привет, {{name}}! Загляни: [[LINK]]</p></body></html>
===END===
Привет, {{name}}. Открой: [[LINK1]]
```

### Ссылки (`links.txt`, `links1.txt`, …)
Один URL (или спинтакс-шаблон) на строку; имя файла задаёт макрос
`[[LINK]]` / `[[LINK1]]` / …

### Имена отправителей (`senders.txt`)
Одно имя на строку.

### База получателей
`.txt` (email по строке, опционально `email,name`) или `.csv` (колонка `email`
обязательна, `name`/`имя` — опционально; разделитель `,` или `;` — автоопределение).

---

## Сборка и релиз

Версия хранится в **едином источнике** — файле `VERSION`.

### Выпуск новой версии (через GitHub Actions)

Один тег запускает сборку и публикацию:

```bash
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions (`.github/workflows/release.yml`) на `windows-latest`:
собирает `.exe` (PyInstaller, `Pinion.spec`, onedir: pywebview + pythonnet +
customtkinter), гоняет смоук `Pinion.exe --selftest-core` (реальный путь ядра),
проверяет версию в ресурсе `.exe`, собирает установщик (Inno Setup, `Pinion.iss`)
и публикует `Pinion-setup.exe` в GitHub Releases на постоянную ссылку
`releases/latest/download/Pinion-setup.exe`.

### Локальная сборка

```bash
python tools/set_version.py 1.0.1     # записать версию в VERSION + version_info.txt
python -m PyInstaller --noconfirm --clean Pinion.spec
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "/DAppVersion=1.0.1" Pinion.iss
```

Неочевидности локальной сборки:
- Собирать **вне OneDrive** (`--distpath`/`--workpath` в temp), иначе OneDrive лочит файлы.
- Inno Setup стоит в **user-scope**: `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.
- В заморозке данные пишутся рядом с `.exe` через `core/appenv.writable_base()`,
  ресурсы читаются из `_MEIPASS` через `resource_path`.

### Проверочные скрипты

```bash
python tools/verify_release_setup.py   # целостность пайплайна релиза (токен RELEASE_SETUP_OK)
python test_ablock_fix.py              # регресс контента: нет обфускации, ссылки целы
```

---

## Структура проекта

```
├── main.py               # точка входа: веб / ctk / --selftest
├── run_web.py            # прямой запуск веб-интерфейса
├── VERSION               # единый источник версии
├── Pinion.spec           # сборка PyInstaller (onedir)
├── Pinion.iss            # установщик Inno Setup
├── core/                 # ядро (логика, без GUI)
│   ├── appenv.py         # пути и версия (resource_path / writable_base / app_version)
│   ├── storage.py        # загрузка файлов/URL
│   ├── proxy_manager.py  # прокси: парсинг, проверка, ротация
│   ├── smtp_manager.py   # SMTP: парсинг, подключение через прокси, проверка
│   ├── content.py        # спинтакс, переменные, ссылки, уникализация
│   ├── queue_manager.py  # получатели, control inject, сборка очереди
│   ├── domain_config.py  # профили отправки по группам доменов
│   ├── sender.py         # движок рассылки, сборка MIME
│   ├── stats.py          # потокобезопасная статистика
│   ├── logger.py         # JSON-lines логгер, экспорт
│   ├── presets.py        # сохранение/загрузка пресетов
│   ├── blacklist.py      # общий модуль DNSBL
│   └── countries.py      # ISO-код → русское название страны
├── webui/                # веб-интерфейс (по умолчанию)
│   ├── host.py           # pywebview-хост, мост js_api
│   ├── letter_score.py   # локальный скорер письма в превью
│   └── web/              # index.html, app.js, style.css
├── gui/                  # старый интерфейс CustomTkinter
├── tools/                # make_icon / check_icon / set_version / verify_release_setup
├── data/                 # рантайм: состояние очереди, пресеты
└── logs/                 # ежедневные JSON-логи
```

---

## Лицензия

Только для приватного использования.
