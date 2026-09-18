# -*- coding: utf-8 -*-
"""Скорер письма для превью: честная оценка открываемости / кликабельности /
доставляемости + проверка контраста (не «пустое» ли письмо).

ПОЧЕМУ так: пользователь тестировал письма во внешнем оценщике и получал РАЗНЫЙ балл
у одного шаблона (часть раскрытий спинтакса слабые). Чтобы не гонять контент во
внешний сервис, тот же разбор считается локально прямо в софте — по тем же
стандартным email-критериям (длина темы 20-70, вопрос/эмодзи/конкретика в теме,
ключи ниши, срочность, личное обращение; тело 50-600, призыв к действию,
персонализация, эмоц-триггеры, анкор глагол+объект). Веса подобраны так, чтобы
совпадать с общепринятым разбором dating-рассылок (сверено на реальном письме:
доставляемость 100, открываемость 24, кликабельность 50 → итог 55/«C»).

Итоговый балл = round(0.30·доставляемость + 0.40·открываемость + 0.30·кликабельность).
Оценки: A≥82, B≥66, C≥50, D≥35, F<35.

Модуль без внешних зависимостей и без побочных эффектов — его гоняет headless-гейт.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# ── профили ниш ──────────────────────────────────────────────────────────────
# Ниша проекта — Dating (см. CLAUDE.md), она реализована точно. Crypto/Finance —
# для полноты. Остальные ниши уходят в общий путь (числа вместо интриги/эмоции).
VERTICALS = {
    "dating": {
        "name": "Dating",
        "avg_ctr": "0.8-1.5%",
        "ctr_ranges": [
            (78, "1.3-1.5%", "↑ выше нормы", True),
            (62, "1.0-1.3%", "↑ в норме", True),
            (46, "0.6-1.0%", "↓ чуть ниже нормы", False),
            (30, "0.3-0.6%", "↓ ниже нормы", False),
            (0,  "< 0.3%",   "↓ значительно ниже нормы", False),
        ],
        "keywords": ["meet", "match", "single", "love", "date", "attractive", "profile",
                     "view", "like", "message", "знакомства", "встреча", "одинокие",
                     "красивые", "свидание", "профиль", "написала", "написал", "посмотрела",
                     "посмотрел", "понравилось", "познакомиться", "пропал", "заходила",
                     "заходил", "ждёт", "скучает", "скучала", "скучал", "смотрел"],
        "intrigue": ["раз", "снова", "кое-что", "кое что", "случилось", "пропал", "написала",
                     "смотрела", "заходила", "ждёт", "скучает", "видела", "думает", "забыла",
                     "нашла", "нашёл", "ответил", "позвонила", "написал"],
        "emo": ["скучаю", "пропал", "ждёт", "написала", "понравился", "нравишься", "давно",
                "хочу", "мечтаю", "нравится", "красивая", "красивый", "позвони", "ответь",
                "скучает", "волнуюсь", "соскучилась", "соскучился", "думаю о тебе", "думаю о"],
    },
    "crypto": {
        "name": "Crypto", "avg_ctr": "0.6-1.2%",
        "ctr_ranges": [(78, "1.0-1.2%", "↑ выше нормы", True), (62, "0.8-1.0%", "↑ в норме", True),
                       (46, "0.5-0.8%", "↓ чуть ниже нормы", False), (30, "0.2-0.5%", "↓ ниже нормы", False),
                       (0, "< 0.2%", "↓ значительно ниже нормы", False)],
        "keywords": ["bitcoin", "btc", "ethereum", "eth", "profit", "invest", "roi", "crypto",
                     "blockchain", "token", "инвестиции", "прибыль", "доход", "криптовалюта",
                     "биткоин", "трейдинг", "trading", "signal", "сигнал", "депозит", "кошелёк"],
        "intrigue": [], "emo": [],
    },
    "finance": {
        "name": "Finance", "avg_ctr": "0.5-1.0%",
        "ctr_ranges": [(78, "0.9-1.0%", "↑ выше нормы", True), (62, "0.7-0.9%", "↑ в норме", True),
                       (46, "0.4-0.7%", "↓ чуть ниже нормы", False), (30, "0.2-0.4%", "↓ ниже нормы", False),
                       (0, "< 0.2%", "↓ значительно ниже нормы", False)],
        "keywords": ["loan", "credit", "save", "money", "financial", "bank", "interest", "rate",
                     "approve", "кредит", "займ", "финансы", "деньги", "одобрен", "ставка",
                     "сэкономить", "платёж", "заявка", "рефинансирование", "ипотека"],
        "intrigue": [], "emo": [],
    },
}
_GENERIC_CTR = [(78, "выше нормы", "↑ выше нормы", True), (62, "в норме", "↑ в норме", True),
                (46, "чуть ниже", "↓ чуть ниже нормы", False), (30, "ниже", "↓ ниже нормы", False),
                (0, "низкий", "↓ значительно ниже нормы", False)]

# Стоп-слова (тема — строго; тело — мягче). Совпадает с базовым набором фильтров.
SPAM_SUBJ = ["free", "бесплатно", "guaranteed", "гарантировано", "winner", "победитель",
             "congratulations", "поздравляем", "urgent", "срочно", "act now", "click here",
             "жми сюда", "no risk", "без риска", "casino", "казино", "prize", "приз", "award",
             "selected", "выбран", "выбрана", "100%", "make money", "заработай", "earn",
             "заработок", "$$$", "!!!!"]
SPAM_BODY = SPAM_SUBJ + ["work from home", "unlimited", "once in a lifetime",
                         "limited time offer", "risk free", "no cost", "free money",
                         "click below", "order now", "buy now", "subscribe", "unsubscribe",
                         "remove from list", "opt out"]

# Призыв к действию и «общие» (слабые) анкоры.
_CTA_GENERIC = ["click", "нажми", "перейди", "жми", "смотреть", "посмотри", "смотри",
                "получить", "получи", "открыть", "открой", "узнать", "узнай",
                "зарегистрируйся", "забрать", "забери", "активировать", "активируй",
                "войди", "зайди", "прочитай", "ответь", "проверь"]
_CTA_BY_VERT = {
    "dating": ["meet", "message", "view", "profile", "chat", "date", "познакомиться",
               "написать", "посмотреть", "смотреть", "ответить", "открыть"],
    "crypto": ["invest", "buy", "trade", "claim", "check", "инвестировать", "купить",
               "получить", "посмотреть", "проверить", "войти", "смотреть"],
    "finance": ["apply", "check", "get", "save", "claim", "подать", "проверить",
                "получить", "сэкономить", "узнать", "смотреть"],
}
_ANCHOR_GENERIC = ["click here", "here", "link", "жми", "тут", "здесь", "подробнее",
                   "click", "more", "read more", "далее", "узнать больше"]
_ANCHOR_VERBS = ["получить", "открыть", "смотреть", "скачать", "войти", "зарегистрироваться",
                 "узнать", "проверить", "забрать", "активировать", "посмотреть", "перейти",
                 "claim", "get", "open", "view", "start", "join", "register", "check",
                 "activate", "play"]

_URGENCY = ["today", "tonight", "сегодня", "сейчас", "now", "hours", "час", "expires",
            "истекает", "last chance", "последний", "limited", "осталось", "только",
            "ending", "midnight", "полночь", "пропал", "сгорит", "сгорят", "сгорают",
            "истечёт", "до полуночи", "до конца дня"]
_PERSONAL = ["you", "your", "ты", "тебе", "тебя", "тобой", "твой", "твоя", "твои", "твоих",
             "твоего", "твоей", "твоём", "твою", "you've", "вы", "ваш", "вас", "вам",
             "милый", "красавчик", "дорогой", "дорогая"]


def _has_emoji(s: str) -> bool:
    # Аналог \p{Emoji_Presentation}: только пиктограммы, НЕ текстовые стрелки (→).
    for ch in s:
        o = ord(ch)
        if 0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF:
            return True
    return False


def _clamp(v: float) -> int:
    return max(0, min(100, int(round(v))))


def _cta_words(vertical: str) -> list[str]:
    return _CTA_BY_VERT.get(vertical, []) + _CTA_GENERIC


# ── три составляющие ──────────────────────────────────────────────────────────
def _score_deliverability(subj: str, body: str, vertical: str) -> dict:
    score, issues, checks = 100, [], []
    sl = len(subj)
    lo = subj.lower()

    if 20 <= sl <= 70:
        checks.append({"ok": True, "text": f"Длина темы: {sl} симв. (норма 20-70)"})
    elif sl < 10:
        score -= 30; issues.append({"sev": "critical", "text": f"Тема слишком короткая ({sl})"})
        checks.append({"ok": False, "text": f"Длина темы: {sl} симв. - слишком коротко"})
    elif sl < 20:
        score -= 10; checks.append({"ok": False, "text": f"Длина темы: {sl} симв. - коротко"})
    elif sl > 70:
        score -= 15; checks.append({"ok": False, "text": f"Длина темы: {sl} симв. - обрежется"})

    caps = re.findall(r"\b[A-ZА-ЯЁ]{3,}\b", subj)
    if not caps:
        checks.append({"ok": True, "text": "Caps lock: не обнаружен"})
    elif len(caps) >= 2:
        score -= 20; checks.append({"ok": False, "text": "Caps lock: " + ", ".join(caps[:2])})
        issues.append({"sev": "critical", "text": "Слова заглавными в теме - красный флаг"})
    else:
        score -= 8; checks.append({"ok": False, "text": "Caps lock: " + caps[0]})

    subj_spam = [w for w in SPAM_SUBJ if w in lo]
    if not subj_spam:
        checks.append({"ok": True, "text": "Стоп-слова в теме: не найдены"})
    else:
        score -= len(subj_spam) * 18
        checks.append({"ok": False, "text": "Стоп-слова в теме: " + ", ".join(subj_spam)})
        issues.append({"sev": "critical", "text": "Спам-слова в теме: " + ", ".join(subj_spam)})

    excl = subj.count("!")
    if excl <= 1:
        checks.append({"ok": True, "text": "Восклицательные знаки: в норме"})
    else:
        score -= excl * 8
        checks.append({"ok": False, "text": f"Восклицательных знаков: {excl} (много)"})

    blo = body.lower()
    body_spam = [w for w in SPAM_BODY if w in blo]
    if not body_spam:
        checks.append({"ok": True, "text": "Стоп-слова в теле: не найдены"})
    else:
        score -= len(body_spam) * 5
        checks.append({"ok": False, "text": "Стоп-слова в теле: " + ", ".join(body_spam[:3])})
        if len(body_spam) >= 3:
            issues.append({"sev": "warning", "text": "Спам-слова в теле: " + ", ".join(body_spam[:4])})

    if len(body.strip()) < 30:
        score -= 15; issues.append({"sev": "warning", "text": "Тело письма слишком короткое"})

    return {"score": _clamp(score), "issues": issues, "checks": checks}


def _score_openrate(subj: str, body: str, vertical: str) -> dict:
    score, issues, tips, checks = 10, [], [], []
    cfg = VERTICALS.get(vertical, {})
    lo, blo = subj.lower(), body.lower()
    vkeys = cfg.get("keywords", [])

    if vertical == "dating":
        intr = cfg.get("intrigue", [])
        if re.search(r"\d", subj) or any(w in lo for w in intr):
            score += 14; checks.append({"ok": True, "text": "Конкретика / интрига в теме: есть"})
        else:
            tips.append('Добавь интригу/конкретику: "3 раза заходила", "кое-что случилось", "ждёт ответа"')
            checks.append({"ok": False, "text": "Конкретика / интрига в теме: нет"})
    else:
        if re.search(r"\d", subj):
            score += 14; checks.append({"ok": True, "text": "Числа в теме: есть"})
        else:
            tips.append("Добавь число в тему: %, $, количество")
            checks.append({"ok": False, "text": "Числа в теме: нет"})

    q = subj.count("?")
    if q == 1:
        score += 10; checks.append({"ok": True, "text": "Вопрос в теме: есть"})
    elif q > 1:
        score -= 5; checks.append({"ok": False, "text": f"Вопросов в теме: {q} (много)"})
    else:
        checks.append({"ok": False, "text": "Вопрос в теме: нет"})

    if _has_emoji(subj):
        score += 10; checks.append({"ok": True, "text": "Эмодзи в теме: есть"})
    else:
        tips.append("Эмодзи выделяет письмо в ящике - попробуй одно")
        checks.append({"ok": False, "text": "Эмодзи в теме: нет"})

    if any(w in lo for w in vkeys):
        score += 14; checks.append({"ok": True, "text": "Ключевые слова вертикали: есть в теме"})
    else:
        checks.append({"ok": False, "text": "Ключевые слова вертикали: нет в теме"})

    if any(w in lo for w in _URGENCY):
        score += 18; checks.append({"ok": True, "text": "Срочность в теме: есть"})
    elif any(w in blo for w in _URGENCY):
        score += 10; checks.append({"ok": False, "text": "Срочность в теме: нет (но есть в теле)"})
        tips.append("Срочность есть в теле, но не в теме - перенеси в тему")
    else:
        tips.append('Срочность повышает open rate: "сегодня", "истекает", "last chance"')
        checks.append({"ok": False, "text": "Срочность в теме: нет"})

    if any(w in lo for w in _PERSONAL):
        score += 14; checks.append({"ok": True, "text": "Личное обращение в теме: есть"})
    elif vertical in ("dating", "sweepstakes"):
        tips.append('Личное обращение ("ты", "твой") в теме повышает открываемость')
        checks.append({"ok": False, "text": "Личное обращение в теме: нет"})
    else:
        checks.append({"ok": False, "text": "Личное обращение в теме: нет (не обязательно)"})

    if any(w in blo for w in vkeys):
        score += 10  # тихий бонус

    return {"score": _clamp(score), "issues": issues, "tips": tips, "checks": checks}


def _score_clickability(subj: str, body: str, anchor: str, vertical: str) -> dict:
    score, issues, tips, checks = 20, [], [], []
    cfg = VERTICALS.get(vertical, {})
    blo = body.lower()

    bl = len(body.strip())
    if bl < 50:
        score -= 20; issues.append({"sev": "critical", "text": "Тело слишком короткое - нет контекста"})
        checks.append({"ok": False, "text": f"Длина тела: {bl} симв. - слишком мало"})
    elif bl <= 600:
        score += 20; checks.append({"ok": True, "text": f"Длина тела: {bl} симв. (норма 50-600)"})
    elif bl <= 1200:
        score += 8; checks.append({"ok": False, "text": f"Длина тела: {bl} симв. - многовато"})
    else:
        score -= 10; checks.append({"ok": False, "text": f"Длина тела: {bl} симв. - слишком много"})

    if any(w in blo for w in _cta_words(vertical)):
        score += 18; checks.append({"ok": True, "text": "Призыв к действию: найден"})
    else:
        issues.append({"sev": "critical", "text": "Нет призыва к действию - читатель не знает что делать"})
        checks.append({"ok": False, "text": "Призыв к действию: нет"})

    if any(w in blo for w in _PERSONAL):
        score += 10; checks.append({"ok": True, "text": "Персонализация (ты/you): есть"})
    else:
        tips.append('Добавь личное обращение ("ты", "you")')
        checks.append({"ok": False, "text": "Персонализация (ты/you): нет"})

    vhits = sum(1 for w in cfg.get("keywords", []) if w in blo)
    if vhits >= 2:
        score += 15; checks.append({"ok": True, "text": f"Ключевые слова вертикали: {vhits} найдено"})
    elif vhits == 1:
        score += 8; checks.append({"ok": False, "text": "Ключевые слова вертикали: 1 (добавь ещё)"})
    else:
        tips.append("В теле нет ключевых слов вертикали - оффер не ощущается")
        checks.append({"ok": False, "text": "Ключевые слова вертикали: не найдены"})

    if vertical == "dating":
        if any(w in blo for w in cfg.get("emo", [])):
            score += 8; checks.append({"ok": True, "text": "Эмоциональные триггеры: найдены"})
        else:
            tips.append('Добавь эмоц-триггер - "скучает", "написала", "нравишься"')
            checks.append({"ok": False, "text": "Эмоциональные триггеры: нет"})
    else:
        if re.search(r"\$|%|\d{2,}", body):
            score += 8; checks.append({"ok": True, "text": "Цифры / % / $: есть"})
        else:
            tips.append("Добавь конкретную цифру - сумму, процент, количество")
            checks.append({"ok": False, "text": "Цифры / % / $: нет"})

    has_link = bool(re.search(r"https?://|www\.", body, re.I))
    anchor = (anchor or "").strip()
    if has_link:
        score += 5; checks.append({"ok": True, "text": "Ссылка в теле: есть"})
    elif anchor:
        al = anchor.lower()
        if al in _ANCHOR_GENERIC:
            score -= 8; checks.append({"ok": False, "text": f'Анкор: слишком общий ("{anchor}")'})
            issues.append({"sev": "warning", "text": "Анкор слишком общий - нужен глагол+объект"})
        elif any(v in al for v in _ANCHOR_VERBS):
            score += 10; checks.append({"ok": True, "text": f'Анкор с глаголом: "{anchor}"'})
        else:
            tips.append('Анкор с глаголом повышает CTR: "Смотреть профиль", "Открыть сообщение"')
            checks.append({"ok": False, "text": f'Анкор без глагола: "{anchor}"'})
    else:
        checks.append({"ok": False, "text": "Ссылка и анкор: не указаны"})
        tips.append("Укажи текст кнопки/ссылки - без него нет кликов")

    return {"score": _clamp(score), "issues": issues, "tips": tips, "checks": checks}


# ── контраст (HTML): не «пустое» ли письмо ────────────────────────────────────
_NAMED = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0),
          "green": (0, 128, 0), "blue": (0, 0, 255), "gray": (128, 128, 128),
          "grey": (128, 128, 128), "silver": (192, 192, 192)}


def _parse_color(v: str):
    if not v:
        return None
    v = v.strip().lower()
    if v in _NAMED:
        return _NAMED[v]
    m = re.match(r"#([0-9a-f]{3})$", v)
    if m:
        h = m.group(1)
        return tuple(int(c * 2, 16) for c in h)
    m = re.match(r"#([0-9a-f]{6})$", v)
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", v)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _lum(rgb) -> float:
    def ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _ratio(a, b) -> float:
    l1, l2 = _lum(a), _lum(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _css(style: str, prop: str):
    # Граница перед именем свойства обязательна: иначе "color" ловится внутри
    # "background-color", и контейнер выглядит как «текст цвета фона» (контраст 1:1).
    m = re.search(r"(?<![-\w])" + re.escape(prop) + r"\s*:\s*([^;]+)", style, re.I)
    return _parse_color(m.group(1)) if m else None


# Void-теги (без закрывающего) — не создают контекст наследования.
_VOID = {"br", "img", "hr", "meta", "link", "input", "area", "base",
         "col", "embed", "source", "track", "wbr"}
_CONTRAST_MIN = 2.5  # ниже — текст практически невидим («пустое» письмо)


class _ContrastScan(HTMLParser):
    """Идём по дереву со стеком (тег, цвет, фон). Цвет/фон НАСЛЕДУЮТСЯ от родителя,
    если у элемента не заданы свои — как в реальном рендере. У КАЖДОГО текстового узла
    считаем контраст его эффективного цвета к эффективному фону. Так ловится и текст без
    своего color, унаследовавший светлый цвет от родителя на светлом фоне (его старая
    версия чекера пропускала, а серый футер «маскировал» проблему как минимум)."""

    def __init__(self, page_bg):
        super().__init__(convert_charrefs=True)
        self.stack = [("", None, page_bg)]  # (tag, color|None, bg)
        self.results = []  # список (kind, ratio) по каждому видимому текст-узлу

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _VOID:
            return
        style = dict(attrs).get("style") or ""
        _, pcol, pbg = self.stack[-1]
        col = _css(style, "color") or pcol
        bg = _css(style, "background-color") or _css(style, "background") or pbg
        self.stack.append((tag, col, bg))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _VOID or len(self.stack) == 1:
            return
        # Закрываем до ближайшего совпадающего открытого тега (терпим кривую вёрстку).
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not data or not data.strip():
            return
        _, col, bg = self.stack[-1]
        if col is None:  # цвет нигде не задан — клиент нарисует контрастно, не наша забота
            return
        is_link = any(f[0] == "a" for f in self.stack)
        self.results.append(("кнопка/ссылка" if is_link else "текст", _ratio(col, bg)))


def check_contrast(html: str) -> dict:
    """Проверяет КАЖДЫЙ текстовый блок письма (с учётом наследования цвета/фона) на
    невидимость: цвет ≈ фон. Флагует, если ХОТЯ БЫ один блок ниже порога 2.5:1 — низкий
    серый футер один по себе письмо не «зачищает», но реально невидимый текст ловится."""
    # Фон-«по умолчанию» для корня: первый явный background среди контейнеров, иначе белый.
    page_bg = None
    for m in re.finditer(r'style\s*=\s*"([^"]*)"', html, re.I):
        c = _css(m.group(1), "background-color") or _css(m.group(1), "background")
        if c:
            page_bg = c
            break
    if page_bg is None:
        page_bg = (255, 255, 255)

    scan = _ContrastScan(page_bg)
    try:
        scan.feed(html)
    except Exception:
        pass
    res = scan.results
    if not res:
        return {"ok": True, "ratio": None,
                "text": "Контраст не проверить (нет явных цветов) — клиент нарисует по умолчанию"}

    worst = round(min(r for _, r in res), 2)
    invisible = [(k, r) for k, r in res if r < _CONTRAST_MIN]
    total = len(res)
    if not invisible:
        return {"ok": True, "ratio": worst, "count": 0,
                "text": f"Контраст в норме (все {total} текст. блоков ≥{_CONTRAST_MIN}:1, минимум {worst}:1)"}
    kinds = sorted({k for k, _ in invisible})
    plural = "ы" if len(invisible) > 1 else ""
    return {"ok": False, "ratio": worst, "count": len(invisible),
            "text": f"⚠ {len(invisible)} из {total} текст. блоков почти невидим{plural} "
                    f"({', '.join(kinds)}): контраст до {worst}:1 — у получателя это будет "
                    f"«пустым». Смени цвет (светлый фон → тёмный текст, тёмный фон → светлый)."}


# ── структура (как рендер-тестеры: DOCTYPE/charset/unsub/размер/ссылки/JS) ────
_SHORT = ["bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "rebrand.ly", "is.gd", "cutt.ly"]


def check_structure(raw_html: str, is_html: bool, text: str) -> dict:
    issues, score = [], 100
    if not is_html:
        return {"score": 100, "status": "plain text — структурных рисков нет", "issues": []}
    low = raw_html.lower()
    links = re.findall(r"<a\b[^>]*>", raw_html, re.I)
    imgs = re.findall(r"<img\b[^>]*>", raw_html, re.I)
    size = len(raw_html.encode("utf-8"))

    if size > 102400:
        score -= 10; issues.append({"t": "bad", "text": f"HTML > 100 KB ({size} б) — Gmail обрежет письмо"})
    elif size > 51200:
        score -= 4; issues.append({"t": "warn", "text": f"HTML > 50 KB ({size} б) — близко к лимиту Gmail"})

    if len(links) == 0:
        score -= 3; issues.append({"t": "warn", "text": "Ни одной ссылки — письму нужен CTA"})
    elif len(links) > 30:
        score -= 8; issues.append({"t": "bad", "text": f"{len(links)} ссылок — слишком много"})

    has_unsub = bool(re.search(r"unsubscribe|отписат|opt[-\s]?out", low))
    if links and not has_unsub:
        # Мягко: у нас unsubscribe кладётся в ЗАГОЛОВОК (List-Unsubscribe), не в тело —
        # фейковый блок в теле сам по себе спам-триггер. Показываем как инфо, не приговор.
        issues.append({"t": "warn", "text": "Нет ссылки «отписаться» в теле — тестеры это отмечают "
                       "(в рассылке отписка идёт заголовком List-Unsubscribe, не в теле)"})
        score -= 4

    if any(d in low for d in _SHORT):
        score -= 10; issues.append({"t": "bad", "text": "Сокращённые ссылки (bit.ly, t.co…) — фильтры их не любят"})
    if not re.search(r"<!doctype", low):
        score -= 2; issues.append({"t": "warn", "text": "Нет <!DOCTYPE html> — Outlook может рендерить в quirks mode"})
    if not re.search(r"<meta[^>]+charset", low):
        issues.append({"t": "info", "text": "Нет <meta charset> в теле — не страшно: софт задаёт кодировку "
                       "заголовком MIME (utf-8), это лишь замечание тестеров"})
    if re.search(r"<link[^>]+rel=[\"']?stylesheet", low):
        score -= 6; issues.append({"t": "bad", "text": "External <link stylesheet> — не работает в почте"})
    if re.search(r"<script", low) or re.search(r"\son\w+\s*=", low) or "javascript:" in low:
        score -= 10; issues.append({"t": "bad", "text": "В письме есть JS — все клиенты его режут"})
    imgs_noalt = sum(1 for i in imgs if not re.search(r"\balt\s*=", i, re.I))
    if imgs and imgs_noalt:
        score -= min(6, imgs_noalt * 2)
        issues.append({"t": "warn", "text": f"{imgs_noalt} из {len(imgs)} картинок без alt"})

    score = _clamp(score)
    status = ("отлично — структура чистая" if score >= 80 else
              "есть мелкие риски" if score >= 60 else
              "много структурных проблем" if score >= 40 else "критично")
    return {"score": score, "status": status, "issues": issues}


# ── публичная функция ─────────────────────────────────────────────────────────
def _grade(s: int) -> tuple[str, str]:
    if s >= 82:
        return "A", "#4ade80"
    if s >= 66:
        return "B", "#86efac"
    if s >= 50:
        return "C", "#fbbf24"
    if s >= 35:
        return "D", "#fb923c"
    return "F", "#f87171"


def _verdict(score: int, dl: int, orr: int, ctr: int, vert: str) -> str:
    vn = VERTICALS.get(vert, {}).get("name", "вертикали")
    if score >= 82:
        return f"Письмо готово к отправке. Хорошая доставляемость и чёткий оффер для {vn}."
    if score >= 66:
        return "Письмо рабочее, но есть точки роста. Доработай по советам ниже."
    if dl >= 70 and orr < 45:
        return "Письмо дойдёт до ящика — но его не откроют. Слабая тема, исправь в первую очередь."
    if dl >= 70 and ctr < 40:
        return "Письмо дойдёт и его откроют — но не кликнут. Переработай тело и призыв к действию."
    if score >= 50:
        return "Средний результат. Исправь приоритетные пункты и пересчитай."
    if score >= 35:
        return "Слабое письмо. Высокий риск не получить клик. Нужна серьёзная правка."
    return "Письмо не готово к отправке. Критические ошибки — начни с них."


def _ctr_estimate(ctr_score: int, vert: str) -> dict:
    cfg = VERTICALS.get(vert, {})
    ranges = cfg.get("ctr_ranges", _GENERIC_CTR)
    for mn, val, tag, up in ranges:
        if ctr_score >= mn:
            return {"val": val, "tag": tag, "up": up, "norm": cfg.get("avg_ctr", "")}
    return {"val": "?", "tag": "", "up": False, "norm": cfg.get("avg_ctr", "")}


def extract_anchor(html: str) -> str:
    """Текст последней <a>…</a> — это и есть анкор (что видит и жмёт получатель)."""
    matches = re.findall(r"<a\b[^>]*>(.*?)</a>", html, re.I | re.S)
    for raw in reversed(matches):
        txt = re.sub(r"<[^>]+>", "", raw)
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            return txt
    return ""


def score_letter(subject: str, body_text: str, html: str = "",
                 is_html: bool = False, anchor: str | None = None,
                 vertical: str = "dating") -> dict:
    """Главная функция: полный разбор письма. body_text — ВИДИМЫЙ текст (как в ящике),
    html — исходный HTML (для контраста/структуры), anchor — текст кнопки/ссылки
    (если None и есть HTML — вытащим из <a>)."""
    subject = subject or ""
    body_text = body_text or ""
    if anchor is None:
        anchor = extract_anchor(html) if is_html else ""

    dl = _score_deliverability(subject, body_text, vertical)
    orr = _score_openrate(subject, body_text, vertical)
    ctr = _score_clickability(subject, body_text, anchor, vertical)
    overall = _clamp(dl["score"] * 0.30 + orr["score"] * 0.40 + ctr["score"] * 0.30)
    letter, color = _grade(overall)

    contrast = check_contrast(html) if is_html else {"ok": True, "ratio": None,
                                                     "text": "plain text — контраст не важен"}
    structure = check_structure(html, is_html, body_text)

    return {
        "overall": overall, "grade": letter, "grade_color": color,
        "deliverability": dl["score"], "openrate": orr["score"], "clickability": ctr["score"],
        "verdict": _verdict(overall, dl["score"], orr["score"], ctr["score"], vertical),
        "ctr_estimate": _ctr_estimate(ctr["score"], vertical),
        "checks": {"deliverability": dl["checks"], "openrate": orr["checks"],
                   "clickability": ctr["checks"]},
        "tips": (orr["tips"] + ctr["tips"])[:5],
        "issues": dl["issues"] + orr["issues"] + ctr["issues"],
        "contrast": contrast,
        "structure": structure,
        "vertical": vertical,
        "anchor": anchor,
    }
