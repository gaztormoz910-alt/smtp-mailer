import os

def replace_in_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

base_dir = r"c:\Users\Bog_1\OneDrive\Desktop\email smtp sender\gui"

# --- gui/window.py ---
replace_in_file(os.path.join(base_dir, "window.py"), [
    ('tab_names = ["Setup", "Content", "Campaign", "Send", "Stats"]', 'tab_names = ["Настройки", "Контент", "Кампания", "Отправка", "Статистика"]'),
    ('self.tabview.tab("Setup")', 'self.tabview.tab("Настройки")'),
    ('self.tabview.tab("Content")', 'self.tabview.tab("Контент")'),
    ('self.tabview.tab("Campaign")', 'self.tabview.tab("Кампания")'),
    ('self.tabview.tab("Send")', 'self.tabview.tab("Отправка")'),
    ('self.tabview.tab("Stats")', 'self.tabview.tab("Статистика")'),
    ('Proxy file not found:', 'Файл прокси не найден:'),
    ('SMTP file not found:', 'Файл SMTP не найден:'),
    ('Subjects file not found:', 'Файл тем не найден:'),
    ('Bodies file not found:', 'Файл писем не найден:'),
    ('Senders file not found:', 'Файл отправителей не найден:'),
    ('Link file not found:', 'Файл ссылок не найден:'),
])

# --- gui/tab_setup.py ---
replace_in_file(os.path.join(base_dir, "tab_setup.py"), [
    ('text="⚡  Proxy Configuration"', 'text="⚡  Настройки прокси"'),
    ('"📁 Load File"', '"📁 Загрузить файл"'),
    ('text="Auto-refresh"', 'text="Авто-обновление"'),
    ('text="min"', 'text="мин"'),
    ('text="⚡ Check All"', 'text="⚡ Проверить все"'),
    ('"✕ Dead"', '"✕ Мертвые"'),
    ('"Clear"', '"Очистить"'),
    ('text="Total: 0  ·  Alive: 0  ·  Dead: 0"', 'text="Всего: 0  ·  Живых: 0  ·  Мертвых: 0"'),
    ('title="Select proxy list"', 'title="Выберите список прокси"'),
    ('("Text / CSV", "*.txt *.csv")', '("Текст / CSV", "*.txt *.csv")'),
    ('("All", "*.*")', '("Все файлы", "*.*")'),
    ('text="✗  Enter a URL first"', 'text="✗  Сначала введите URL"'),
    ('text=f"✓  Loaded {count} from {source}"', 'text=f"✓  Загружено {count} из {source}"'),
    ('text=f"✓  Done — Alive: {a}  Dead: {d}"', 'text=f"✓  Готово — Живых: {a}  Мертвых: {d}"'),
    ('text=f"✓  Removed {n} dead"', 'text=f"✓  Удалено {n} мертвых"'),
    ('text="✓  Cleared"', 'text="✓  Очищено"'),
    ('text="✗  Enter URL for auto-refresh"', 'text="✗  Введите URL для авто-обновления"'),
    ('text=f"↻  Refreshed: {c} proxies"', 'text=f"↻  Обновлено: {c} прокси"'),
    ('text=f"↻  Auto-refresh ON ({mins} min)"', 'text=f"↻  Авто-обновление ВКЛ ({mins} мин)"'),
    ('text="↻  Auto-refresh OFF"', 'text="↻  Авто-обновление ВЫКЛ"'),
    ('text=f"Total: {t}  ·  Alive: {a}  ·  Dead: {d}"', 'text=f"Всего: {t}  ·  Живых: {a}  ·  Мертвых: {d}"'),
    ('text="📧  SMTP Configuration"', 'text="📧  Настройки SMTP"'),
    ('"📁 Load smtps.txt"', '"📁 Загрузить smtps.txt"'),
    ('title="Select SMTP accounts file"', 'title="Выберите файл SMTP аккаунтов"'),
    ('("Text files", "*.txt")', '("Текстовые файлы", "*.txt")'),
    ('text=f"Sent: {acc.sent_count}"', 'text=f"Отправлено: {acc.sent_count}"'),
    ('"Test"', '"Тест"'),
])

# --- gui/tab_content.py ---
replace_in_file(os.path.join(base_dir, "tab_content.py"), [
    ('text="📝  Subjects"', 'text="📝  Темы (Subjects)"'),
    ('"📁 Load"', '"📁 Загрузить"'),
    ('"Clear"', '"Очистить"'),
    ('text="0 loaded"', 'text="0 загружено"'),
    ('text="📄  Email Bodies"', 'text="📄  Тексты писем"'),
    ('text="🔗  Links"', 'text="🔗  Ссылки"'),
    ('"📁 Load Links"', '"📁 Загрузить ссылки"'),
    ('text="Consistent links per email"', 'text="Единые ссылки для каждого письма"'),
    ('text="👤  Sender Names"', 'text="👤  Имена отправителей"'),
    ('text="Email only (no sender name)"', 'text="Только email (без имени отправителя)"'),
    ('text="🎲  Test Sandbox — Full Preview"', 'text="🎲  Песочница — Предпросмотр"'),
    ('"Email:"', '"Email:"'),
    ('"Name:"', '"Имя:"'),
    ('text="🎲  Generate"', 'text="🎲  Сгенерировать"'),
    ('title="Select subjects file"', 'title="Выберите файл с темами"'),
    ('text=f"{count} loaded"', 'text=f"{count} загружено"'),
    ('"(empty)"', '"(пусто)"'),
    ('text=f"✓  {count} subjects"', 'text=f"✓  {count} тем"'),
    ('text="✓  Cleared"', 'text="✓  Очищено"'),
    ('title="Select bodies file"', 'title="Выберите файл с текстами писем"'),
    ('text=f"✓  {count} bodies"', 'text=f"✓  {count} писем"'),
    ('title="Select link files"', 'title="Выберите файлы со ссылками"'),
    ('text=f"✓  {len(msgs)} file(s)"', 'text=f"✓  {len(msgs)} файл(ов)"'),
    ('title="Select sender names file"', 'title="Выберите файл имен отправителей"'),
    ('text=f"✓  {count} names"', 'text=f"✓  {count} имен"'),
    ('text="✗  Load subjects / bodies first"', 'text="✗  Сначала загрузите темы / тексты"'),
    ('f"Sender: {sender_name}" if sender_name else "Sender: (email only)"', 'f"Отправитель: {sender_name}" if sender_name else "Отправитель: (только email)"'),
    ('f"Subject:  {subj}"', 'f"Тема:  {subj}"'),
    ('"Subject:  (no subjects loaded)"', '"Тема:  (темы не загружены)"'),
    ('"Plain Text"', '"Обычный текст"'),
    ('f"Format:   {fmt}"', 'f"Формат:   {fmt}"'),
    ('"Format:   —"', '"Формат:   —"'),
    ('"(no bodies loaded)"', '"(тексты не загружены)"'),
    ('text="✓  Preview generated"', 'text="✓  Предпросмотр сгенерирован"'),
])

# --- gui/tab_campaign.py ---
replace_in_file(os.path.join(base_dir, "tab_campaign.py"), [
    ('text="📋  Recipients Database"', 'text="📋  База получателей"'),
    ('text="📁  Load Recipients"', 'text="📁  Загрузить получателей"'),
    ('text="Clear"', 'text="Очистить"'),
    ('text="0 recipients"', 'text="0 получателей"'),
    ('text="Name"', 'text="Имя"'),
    ('text="📬  CC / BCC"', 'text="📬  Копии (CC / BCC)"'),
    ('text="🎯  Control Email Inject"', 'text="🎯  Контрольные адреса (Control Inject)"'),
    ('text="Every:"', 'text="Каждые:"'),
    ('text="emails (0=off)"', 'text="писем (0=выкл)"'),
    ('text="Addrs:"', 'text="Адреса:"'),
    ('text="🔄 Build Queue"', 'text="🔄 Создать очередь"'),
    ('text="⚙  Presets"', 'text="⚙  Пресеты"'),
    ('text="💾  Save Preset"', 'text="💾  Сохранить пресет"'),
    ('text="📂  Load Preset"', 'text="📂  Загрузить пресет"'),
    ('title="Select recipients file"', 'title="Выберите файл получателей"'),
    ('text=f"{len(recs)} recipients"', 'text=f"{len(recs)} получателей"'),
    ('text=f"✓  {len(recs)} from {Path(path).name}"', 'text=f"✓  {len(recs)} из {Path(path).name}"'),
    ('text="✓  Cleared"', 'text="✓  Очищено"'),
    ('text="✗  Load first"', 'text="✗  Сначала загрузите получателей"'),
    ('f"{regular_count} regular"', 'f"{regular_count} обычных"'),
    ('f" + {ctrl_count} ctrl"', 'f" + {ctrl_count} контр."'),
    ('title="Save preset"', 'title="Сохранить пресет"'),
    ('title="Load preset"', 'title="Загрузить пресет"'),
    ('"Preset Warnings"', '"Предупреждения пресета"'),
    ('"Some files were not found:\\n\\n"', '"Некоторые файлы не найдены:\\n\\n"'),
    ('text=f"✓ Saved: {Path(path).name}"', 'text=f"✓ Сохранено: {Path(path).name}"'),
    ('text=f"✓ Loaded: {Path(path).name}"', 'text=f"✓ Загружено: {Path(path).name}"'),
    ('f"  … and {len(self._recipients) - 10} more"', 'f"  … и еще {len(self._recipients) - 10}"'),
])

# --- gui/tab_send.py ---
replace_in_file(os.path.join(base_dir, "tab_send.py"), [
    ('text="🧪  Test Send"', 'text="🧪  Тестовая отправка"'),
    ('text="To:"', 'text="Кому:"'),
    ('text="📨  SEND TEST"', 'text="📨  ОТПРАВИТЬ ТЕСТ"'),
    ('text="📨  Campaign Controls"', 'text="📨  Управление кампанией"'),
    ('text="Delay:"', 'text="Задержка:"'),
    ('text="sec"', 'text="сек"'),
    ('text="±Jitter:"', 'text="±Разброс:"'),
    ('text="👁  Preview"', 'text="👁  Предпросмотр"'),
    ('text="▶  START"', 'text="▶  СТАРТ"'),
    ('text="■  STOP"', 'text="■  СТОП"'),
    ('text="⏸  PAUSE"', 'text="⏸  ПАУЗА"'),
    ('text="Ready  ·  Load recipients & SMTP to start"', 'text="Готов  ·  Загрузите получателей и SMTP для старта"'),
    ('text="📋  Message Preview / Log"', 'text="📋  Предпросмотр письма / Лог"'),
    ('text="✗  Enter a valid email"', 'text="✗  Введите корректный email"'),
    ('text="Sending…"', 'text="Отправка…"'),
    ('text="✗  No recipients loaded — go to Campaign tab"', 'text="✗  Получатели не загружены — перейдите во вкладку Кампания"'),
    ('text="✗  No alive SMTP — go to Setup tab"', 'text="✗  Нет живых SMTP — перейдите во вкладку Настройки"'),
    ('f"▶  Sending to {len(self._recipients)} recipients…{cc_info}{bcc_info}"', 'f"▶  Отправка {len(self._recipients)} получателям…{cc_info}{bcc_info}"'),
    ('f"Campaign started: {len(self._recipients)} recipients\\n"', 'f"Кампания начата: {len(self._recipients)} получателей\\n"'),
    ('text="■  Stopped"', 'text="■  Остановлено"'),
    ('text="▶  Resumed"', 'text="▶  Возобновлено"'),
    ('text="▶  RESUME"', 'text="▶  ПРОДОЛЖИТЬ"'),
    ('text="⏸  Paused"', 'text="⏸  На паузе"'),
    ('f"✓  Finished — Sent: {snap[\'sent\']}  Errors: {snap[\'errors\']}"', 'f"✓  Завершено — Отправлено: {snap[\'sent\']}  Ошибок: {snap[\'errors\']}"'),
    ('title="Resume Campaign"', 'title="Возобновление кампании"'),
    ('text="⚡ Interrupted campaign found"', 'text="⚡ Обнаружена прерванная кампания"'),
    ('f"Sent: {sent} / {total}  ·  Remaining: {len(remaining)}"', 'f"Отправлено: {sent} / {total}  ·  Осталось: {len(remaining)}"'),
    ('text="▶  Resume"', 'text="▶  Возобновить"'),
    ('text="✕  Discard"', 'text="✕  Сбросить"'),
    ('f"↻  Resumed queue: {len(remaining)} recipients"', 'f"↻  Очередь возобновлена: {len(remaining)} получателей"'),
    ('text=f"Ready  ·  {count} recipients loaded"', 'text=f"Готов  ·  Загружено {count} получателей"'),
    ('text="Ready  ·  Load recipients to start"', 'text="Готов  ·  Загрузите получателей для старта"'),
])

# --- gui/tab_stats.py ---
replace_in_file(os.path.join(base_dir, "tab_stats.py"), [
    ('text="Idle"', 'text="Ожидание"'),
    ('title="⚡ Speed"', 'title="⚡ Скорость"'),
    ('"0 /min"', '"0 /мин"'),
    ('title="⏱  ETA"', 'title="⏱  Осталось"'),
    ('title="✓  Sent"', 'title="✓  Отправлено"'),
    ('title="✗  Errors"', 'title="✗  Ошибки"'),
    ('text="📧  SMTP Accounts"', 'text="📧  Аккаунты SMTP"'),
    ('("Email", 180), ("Sent", 50), ("Err", 45), ("Status", 60)', '("Email", 180), ("Отпр", 50), ("Ошиб", 45), ("Статус", 60)'),
    ('text="🌐  Proxies"', 'text="🌐  Прокси"'),
    ('("Address", 180), ("Used", 50), ("Err", 45), ("Status", 60)', '("Адрес", 180), ("Исп", 50), ("Ошиб", 45), ("Статус", 60)'),
    ('text="📥  Export JSON"', 'text="📥  Экспорт JSON"'),
    ('text="📥  Export CSV"', 'text="📥  Экспорт CSV"'),
    ('f"{snap[\'speed_per_min\']} /min"', 'f"{snap[\'speed_per_min\']} /мин"'),
    ('text="idle"', 'text="ожидание"'),
    ('text="✗  No send logs found"', 'text="✗  Логи отправки не найдены"'),
    ('title="Export CSV"', 'title="Экспорт CSV"'),
    ('title="Export JSON"', 'title="Экспорт JSON"'),
    ('text=f"✓  Exported {count} records → {Path(dst).name}"', 'text=f"✓  Экспортировано {count} записей → {Path(dst).name}"'),
])

print("Translation applied.")
