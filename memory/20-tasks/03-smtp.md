# Задача 3 — SMTP-аккаунты

## Что реализовано
Модуль `core/smtp_manager.py` + блок «SMTP Configuration» на вкладке Setup (правая колонка).

## Формат файла
Одна строка = один аккаунт: `host:port:email:password`.
Пароль может содержать двоеточия (split с limit=3).

## Подключение через PySocks (КРИТИЧНАЯ ЛОГИКА)
`smtplib` не поддерживает прокси из коробки. Решение:

1. Создаём `socks.socksocket()` через PySocks.
2. Подключаем сокет к SMTP-серверу **через прокси**.
3. Подставляем сокет в `smtplib.SMTP` / `SMTP_SSL`:
   - `smtp.sock = proxy_socket`
   - `smtp.file = smtp.sock.makefile('rb')`
   - `smtp._host = host`
   - Читаем greeting: `smtp.getreply()`, проверяем код 220.
4. Дальше работаем как обычно: `ehlo()`, `starttls()`, `login()`.

## Шифрование по порту
| Порт | Метод |
|---|---|
| 465 | SSL — сокет оборачиваем в `ssl.create_default_context().wrap_socket()` ДО передачи в SMTP_SSL |
| 587 | STARTTLS — подключаемся plain, затем `smtp.starttls()` |
| 25 и др. | Plain, пробуем STARTTLS (если сервер поддерживает) |

## Ротация
- `get_next()` — round-robin по живым (status == ALIVE).
- **5xx ошибки** (auth fail, перма-бан) → `Dead`, исключён из ротации.
- **4xx / сетевые** (таймаут, обрыв) → остаётся в ротации, `last_error` записывается.

## Карточки в GUI
Каждый аккаунт отображается карточкой (`CTkFrame`) с:
- Email (жирный), host:port [SSL/STARTTLS], статус (●), счётчик Sent.
- Кнопка «Test» — индивидуальный тест-логин в фоне.
- Строка ошибки — показывается под кнопкой если логин не прошёл.

## Проверка через прокси
При «Check All» и «Test» — если есть живые прокси в `proxy_mgr`, подключение идёт через `proxy_mgr.get_next()`.

## Файлы задачи 3
| Файл | Действие |
|---|---|
| `core/smtp_manager.py` | реализован полностью |
| `gui/tab_setup.py` | переписан (две колонки: Proxy + SMTP) |
