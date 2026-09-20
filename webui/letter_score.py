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
        # Слова-маркеры ниши. Достаточно БАЗОВОЙ формы/одного синонима — морфология
        # (стеммер ниже) сама сведёт «посмотрел/посмотрела/посмотрю/посмотрят» к одному
        # корню, а перечисленные синонимы покрывают РАЗНЫЕ слова одного смысла. Поэтому
        # тут не нужно перечислять все падежи/времена — только разные корни/синонимы.
        "keywords": [
            # EN — профиль/просмотры/симпатии/пара/сообщения/близость/люди/внешность/активность
            "profile", "account", "page", "photo", "picture", "pic", "album",
            "view", "viewed", "viewer", "seen", "saw", "look", "glance", "peek", "peeked",
            "checked", "spotted", "noticed", "browse",
            "like", "liked", "heart", "fav", "favorite", "favourite", "wink", "winked",
            "match", "matched", "matches", "compatible", "chemistry",
            "message", "msg", "dm", "text", "texted", "note", "chat", "chatted", "reply",
            "inbox", "conversation", "flirt", "flirted",
            "nearby", "near", "close", "local", "area", "around", "neighborhood", "distance",
            "single", "singles", "available", "meet", "meetup", "hookup", "date", "dating",
            "crush", "admirer", "secret", "stranger", "member", "user", "connection", "request",
            "someone", "somebody", "girl", "woman", "lady", "guy", "man", "people",
            "hot", "cute", "sexy", "attractive", "beautiful", "gorgeous", "pretty", "handsome",
            "online", "active", "activity", "notification", "alert", "invite", "invitation",
            # RU
            "профиль", "анкета", "страница", "фото", "фотка", "снимок", "фотография",
            "просмотр", "посмотрел", "смотрел", "глянул", "заглянул", "увидел", "видел",
            "заметил", "лайк", "понравился", "нравишься", "симпатия", "сердечко", "подмигнул",
            "пара", "совпадение", "мэтч", "сообщение", "написал", "ответ", "переписка", "чат",
            "рядом", "поблизости", "недалеко", "близко", "район", "расстояние",
            "одинокий", "одинокая", "свободна", "свободен", "встреча", "свидание", "знакомство",
            "знакомства", "познакомиться", "поклонник", "тайный", "незнакомка", "незнакомец",
            "участник", "пользователь", "кто-то", "девушка", "женщина", "парень", "мужчина",
            "красивая", "красивый", "симпатичная", "милашка", "горячая", "привлекательная",
            "онлайн", "активность", "уведомление", "запрос", "приглашение", "приглашает",
        ],
        # Интрига/конкретика в теме — «есть о чём стало любопытно». Числа считаются отдельно
        # (регуляркой), тут — слова, создающие curiosity gap.
        "intrigue": [
            # EN
            "something", "someone", "somebody", "guess", "believe", "wont", "turns",
            "apparently", "notice", "noticed", "spotted", "wait", "almost", "nearly", "barely",
            "missed", "finally", "again", "twice", "secret", "weird", "strange", "unexpected",
            "surprise", "happened", "remember", "forgot", "mistake", "accident", "honestly",
            "actually", "recently", "lately", "still", "quietly", "somehow",
            # RU
            "раз", "снова", "опять", "кое-что", "что-то", "кто-то", "случилось", "произошло",
            "пропал", "написал", "смотрел", "заходил", "ждёт", "скучает", "видел", "думает",
            "забыл", "нашёл", "ответил", "позвонил", "угадай", "представляешь", "оказывается",
            "заметил", "странно", "неожиданно", "вдруг", "наконец", "тайна", "секрет", "помнишь",
            "недавно", "почему-то",
        ],
        # Эмоциональные триггеры — тёплое/личное чувство (НЕ нейтральные факты).
        "emo": [
            # EN
            "miss", "missing", "missed", "lonely", "alone", "want", "crave", "wish", "dream",
            "thinking", "care", "heart", "waiting", "hope", "crush", "attracted", "nervous",
            "excited", "blush", "need", "feelings", "adore", "love", "kiss", "hug", "cant",
            # RU
            "скучаю", "скучает", "соскучился", "соскучилась", "одиноко", "хочу", "хочет",
            "мечтаю", "мечтает", "жду", "ждёт", "надеюсь", "волнуюсь", "переживаю", "нравишься",
            "нравится", "влюбилась", "влюбился", "сердце", "чувства", "тянет", "обнять",
            "поцеловать", "думаю о тебе", "думаю о", "не могу забыть", "не могу перестать",
        ],
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

# Стоп-слова (тема — строго; тело — мягче). Фокус — классические денежные/скам/фарма-
# триггеры фильтров; НЕ добавляем сюда неоднозначные dating-слова, чтобы не штрафовать
# легитимные личные письма. Многословные фразы и символьные («$$$», «100%») ищутся
# подстрокой, одиночные слова — по стему (поэтому «free» больше НЕ ловит «freedom»).
SPAM_SUBJ = ["free", "бесплатно", "freebie", "guaranteed", "guarantee", "гарантировано",
             "гарантия", "winner", "победитель", "congratulations", "поздравляем",
             "поздравляю", "urgent", "срочно", "act now", "click here", "жми сюда",
             "no risk", "без риска", "risk-free", "casino", "казино", "prize", "приз",
             "award", "награда", "selected", "выбран", "выбрана", "100%", "make money",
             "заработай", "earn", "заработок", "$$$", "!!!!", "bonus", "бонус", "jackpot",
             "джекпот", "lottery", "лотерея", "viagra", "cialis", "pharmacy", "аптека",
             "wire transfer", "million", "миллион", "cash", "наличные", "credit card"]
SPAM_BODY = SPAM_SUBJ + ["work from home", "unlimited", "once in a lifetime",
                         "limited time offer", "risk free", "no cost", "free money",
                         "click below", "order now", "buy now", "subscribe", "unsubscribe",
                         "remove from list", "opt out", "dear friend", "this is not spam",
                         "wire transfer", "bank account", "verify your account",
                         "suspended account", "weight loss", "lose weight", "make money fast",
                         "double your", "100% free", "no strings"]

# Призыв к действию (глаголы). Одного-двух синонимов достаточно — стеммер сведёт формы
# («смотри/посмотри/посмотрю/посмотрел», «check/checked/checking»). EN+RU широко.
_CTA_GENERIC = [
    # EN
    "click", "tap", "press", "go", "visit", "open", "see", "view", "look", "watch", "read",
    "check", "find", "get", "grab", "take", "claim", "join", "start", "begin", "discover",
    "explore", "browse", "unlock", "reveal", "learn", "meet", "reply", "answer", "respond",
    "message", "chat", "connect", "swipe", "activate", "register", "download", "follow", "catch",
    # RU
    "нажми", "кликни", "жми", "перейди", "зайди", "открой", "посмотри", "смотри", "глянь",
    "взгляни", "читай", "прочитай", "проверь", "найди", "получи", "забери", "возьми",
    "присоединяйся", "начни", "узнай", "познакомься", "ответь", "напиши", "свяжись", "листай",
    "активируй", "зарегистрируйся", "скачай", "подпишись", "лови", "успей", "открыть",
    "посмотреть", "смотреть", "получить", "узнать", "ответить", "написать", "познакомиться",
]
_CTA_BY_VERT = {
    "dating": ["meet", "message", "view", "profile", "chat", "date", "wink", "flirt",
               "reply", "swipe"],
    "crypto": ["invest", "buy", "trade", "claim", "check", "инвестировать", "купить",
               "трейд", "вложить"],
    "finance": ["apply", "check", "get", "save", "claim", "подать", "оформить", "сэкономить"],
}
# Слишком «общие» анкоры — их скорер штрафует (нужен глагол+объект). Держим коротко и точно,
# чтобы не штрафовать нормальные анкоры.
_ANCHOR_GENERIC = ["click here", "here", "link", "this", "that", "it", "more", "details",
                   "read more", "learn more", "tap here", "go here", "this link",
                   "жми", "тут", "здесь", "ссылка", "подробнее", "далее", "сюда", "туда",
                   "вот", "узнать больше", "читать далее"]
# Глаголы действия в анкоре (= призыв). По сути объединение CTA-глаголов + пары синонимов.
_ANCHOR_VERBS = _CTA_GENERIC + ["open", "start", "play", "meet", "date", "chat", "view", "see",
                                "look", "peek", "reveal", "unlock", "discover", "скачать",
                                "войти", "зарегистрироваться", "перейти", "забрать",
                                "активировать", "смотреть", "открыть"]

_URGENCY = [
    # EN
    "today", "tonight", "now", "soon", "hurry", "quick", "fast", "expires", "expire",
    "expiring", "ends", "ending", "deadline", "last", "final", "only", "before", "midnight",
    "hours", "minutes", "moments", "limited", "closing", "gone", "leaving", "still",
    # RU
    "сегодня", "сейчас", "скоро", "быстрее", "поторопись", "успей", "срочно", "истекает",
    "истечёт", "заканчивается", "кончается", "последний", "последняя", "финал", "только",
    "осталось", "полночь", "до полуночи", "до конца дня", "пока не поздно", "пока можешь",
    "вот-вот", "сгорит", "сгорят", "уходит", "пропадёт", "ещё онлайн", "ещё тут", "час",
]
_PERSONAL = [
    # EN — 2-е лицо + обращения
    "you", "your", "yours", "youre", "youve", "youll", "youd", "yourself", "u", "ur",
    "dear", "honey", "babe", "baby", "sweetie", "sweetheart", "darling", "cutie", "hun",
    # RU
    "ты", "тебя", "тебе", "тобой", "тобою", "твой", "твоя", "твоё", "твои", "твоих",
    "твоего", "твоей", "твоём", "твою", "твоим", "твоими", "вы", "ваш", "ваша", "ваше",
    "ваши", "вас", "вам", "вами", "милый", "милая", "дорогой", "дорогая", "красавчик",
    "красотка", "солнышко", "зайка", "любимый", "любимая",
]


def _has_emoji(s: str) -> bool:
    # Аналог \p{Emoji_Presentation}: только пиктограммы, НЕ текстовые стрелки (→).
    for ch in s:
        o = ord(ch)
        if 0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF:
            return True
    return False


def _clamp(v: float) -> int:
    return max(0, min(100, int(round(v))))


# ══ МОРФОЛОГИЯ: лёгкий двуязычный стеммер + сопоставление по смыслу ══════════════
# ЗАЧЕМ: без него скорер «знал» бы только точные слова из списков и штрафовал письмо за
# синоним или другую форму слова («посмотрел» знает, «посмотрела/посмотрю/заглянул» — нет),
# из-за чего оценка получалась ложной. Стеммер сводит ВСЕ формы одного слова к общему корню
# (и в тексте, и в словаре — тогда они совпадают), а списки-синонимы выше покрывают РАЗНЫЕ
# слова одного смысла. Стем не обязан быть лингвистически идеальным — важно лишь, чтобы формы
# ОДНОГО слова давали ОДИН стем. Без внешних зависимостей (модуль гоняет headless-гейт).

_VOWELS_RU = set("аеёиоуыэюя")
_CYR_RE = re.compile(r"[а-яё]")
_TOKEN_RE = re.compile(r"[a-zа-яё']+", re.IGNORECASE)

# Русские окончания (глагол/причастие/прилагательное/существительное/местоимение),
# отсортируем по длине убыв. — снимаем самый длинный подходящий, храня корень ≥3 букв.
# ВАЖНО: прошедшее время снимаем коротким «л/ла/ло/ли», а «хвостовую» гласную убирает
# пост-нормализация ниже (написал→написа→напис, посмотрел→посмотре→посмотр). Так мы НЕ
# используем агрессивные «ала/ила/или/…», которые съедали существительные (профили→«проф»).
_RU_SUFFIXES = sorted(set([
    # возвратные и длинные
    "ешься", "ишься", "ается", "уется", "уются", "аются", "яются",
    "ется", "ится", "емся", "имся", "етесь", "итесь", "ются", "ятся",
    "лся", "лась", "лись", "вшись", "вшийся",
    # причастия/прилагательные-длинные
    "ающий", "ующий", "ящий", "ащий", "авший", "ивший", "ывший", "ущий", "ющий",
    "анн", "янн", "енн", "ённ", "ированн",
    # настоящее/будущее
    "аешь", "аёшь", "уешь", "уёшь", "ываешь", "иваешь", "аете", "уете",
    "ешь", "ишь", "ете", "ите", "ает", "ают", "еет", "еют", "ует", "уют",
    "ит", "ят", "ют", "им", "ем",
    # инфинитив
    "овать", "евать", "ывать", "ивать", "ать", "ять", "еть", "ить", "ыть", "уть",
    "ть", "ти", "чь",
    # прошедшее (коротко) + гласную уберёт пост-нормализация
    "л", "ла", "ло", "ли",
    # прилагательные/местоимения
    "ыми", "ими", "ого", "его", "ому", "ему",
    "ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ым", "ых", "их", "ую", "юю",
    # существительные
    "ами", "ями", "ах", "ях", "ов", "ев", "ам", "ям", "ом", "ья", "ье", "ью",
    # одиночные
    "а", "я", "ы", "и", "у", "ю", "о", "е", "ь", "й",
]), key=len, reverse=True)


def _stem_ru(w: str) -> str:
    # снимаем одно самое длинное окончание, потом нормализуем «хвост» (мягкий знак + одна
    # гласная) — так «сообщение/сообщения» и «посмотре/посмотр» сходятся к одному стему.
    if len(w) > 4:
        for suf in _RU_SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
    if len(w) > 3 and w[-1] in "ьъй":
        w = w[:-1]
    if len(w) > 3 and w[-1] in _VOWELS_RU:
        w = w[:-1]
    return w


def _stem_en(w: str) -> str:
    for suf in ("'s", "'ve", "'re", "'ll", "'d", "'m", "n't"):
        if w.endswith(suf):
            w = w[: -len(suf)]
            break
    if len(w) > 4:
        if w.endswith("ies"):
            w = w[:-3] + "y"
        elif w.endswith("sses"):
            w = w[:-2]
        elif w.endswith(("ches", "shes", "xes", "zes", "ses", "oes")):
            w = w[:-2]
        elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
            w = w[:-1]
    if len(w) > 4:
        if w.endswith("ing"):
            w = w[:-3]
        elif w.endswith("edly"):
            w = w[:-4]
        elif w.endswith("ed"):
            w = w[:-2]
        elif w.endswith("ly"):
            w = w[:-2]
    if len(w) > 3 and w.endswith("e"):  # «silent e»: like/liked→lik, profile→profil
        w = w[:-1]
    return w


_STEM_CACHE: dict[str, str] = {}


def _stem(w: str) -> str:
    w = w.lower()
    s = _STEM_CACHE.get(w)
    if s is None:
        s = _stem_ru(w) if _CYR_RE.search(w) else _stem_en(w)
        _STEM_CACHE[w] = s
    return s


def _text_stems(text: str) -> set[str]:
    return {_stem(t) for t in _TOKEN_RE.findall(text.lower())}


def _is_phrase(w: str) -> bool:
    # многословное, с дефисом или чисто символьное («$$$», «100%», «!!!!») — ищем подстрокой,
    # одиночное слово — по стему.
    return (" " in w) or ("-" in w) or not any(ch.isalpha() for ch in w)


class _Concept:
    __slots__ = ("stems", "phrases")

    def __init__(self, stems: set[str], phrases: tuple[str, ...]):
        self.stems = stems
        self.phrases = phrases


def _concept(*words: str) -> _Concept:
    stems: set[str] = set()
    phrases: list[str] = []
    for w in words:
        wl = w.strip().lower()
        if not wl:
            continue
        if _is_phrase(wl):
            phrases.append(wl)
        else:
            stems.add(_stem(wl))
    return _Concept(stems, tuple(phrases))


def _has(low: str, ts: set[str], concept: _Concept) -> bool:
    # low — текст в нижнем регистре, ts — множество стемов его токенов (считаем один раз).
    if concept.stems & ts:
        return True
    return any(p in low for p in concept.phrases)


def _count(low: str, ts: set[str], concept: _Concept) -> int:
    return len(concept.stems & ts) + sum(1 for p in concept.phrases if p in low)


def _matched(low: str, ts: set[str], words: list[str]) -> list[str]:
    # какие ИСХОДНЫЕ слова из списка нашлись (для показа в чек-листе стоп-слов).
    out = []
    for w in words:
        wl = w.lower()
        if (wl in low) if _is_phrase(wl) else (_stem(wl) in ts):
            out.append(w)
    return out


# Предсобранные «концепты» из расширенных списков (стемы считаются один раз на импорте).
_KW = {v: _concept(*cfg.get("keywords", [])) for v, cfg in VERTICALS.items()}
_INTR = {v: _concept(*cfg.get("intrigue", [])) for v, cfg in VERTICALS.items()}
_EMO = {v: _concept(*cfg.get("emo", [])) for v, cfg in VERTICALS.items()}
_URG_C = _concept(*_URGENCY)
_PERS_C = _concept(*_PERSONAL)
_ANCHOR_VB_C = _concept(*_ANCHOR_VERBS)
_ANCHOR_GEN_SET = {a.strip().lower() for a in _ANCHOR_GENERIC}  # анкор целиком == «общий»
_CTA_C = {v: _concept(*(_CTA_BY_VERT.get(v, []) + _CTA_GENERIC)) for v in VERTICALS}
_CTA_C_GENERIC = _concept(*_CTA_GENERIC)


def _cta_concept(vertical: str) -> _Concept:
    return _CTA_C.get(vertical, _CTA_C_GENERIC)


def _kw_concept(vertical: str) -> _Concept:
    return _KW.get(vertical, _KW.get("dating"))


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

    sts = _text_stems(subj)
    subj_spam = _matched(lo, sts, SPAM_SUBJ)
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
    bts = _text_stems(body)
    body_spam = _matched(blo, bts, SPAM_BODY)
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
    lo, blo = subj.lower(), body.lower()
    sts, bts = _text_stems(subj), _text_stems(body)
    kw = _kw_concept(vertical)
    intr = _INTR.get(vertical)

    if vertical == "dating":
        if re.search(r"\d", subj) or (intr and _has(lo, sts, intr)):
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

    if _has(lo, sts, kw):
        score += 14; checks.append({"ok": True, "text": "Ключевые слова вертикали: есть в теме"})
    else:
        checks.append({"ok": False, "text": "Ключевые слова вертикали: нет в теме"})

    if _has(lo, sts, _URG_C):
        score += 18; checks.append({"ok": True, "text": "Срочность в теме: есть"})
    elif _has(blo, bts, _URG_C):
        score += 10; checks.append({"ok": False, "text": "Срочность в теме: нет (но есть в теле)"})
        tips.append("Срочность есть в теле, но не в теме - перенеси в тему")
    else:
        tips.append('Срочность повышает open rate: "сегодня", "истекает", "last chance"')
        checks.append({"ok": False, "text": "Срочность в теме: нет"})

    if _has(lo, sts, _PERS_C):
        score += 14; checks.append({"ok": True, "text": "Личное обращение в теме: есть"})
    elif vertical in ("dating", "sweepstakes"):
        tips.append('Личное обращение ("ты", "твой") в теме повышает открываемость')
        checks.append({"ok": False, "text": "Личное обращение в теме: нет"})
    else:
        checks.append({"ok": False, "text": "Личное обращение в теме: нет (не обязательно)"})

    if _has(blo, bts, kw):
        score += 10  # тихий бонус

    return {"score": _clamp(score), "issues": issues, "tips": tips, "checks": checks}


def _score_clickability(subj: str, body: str, anchor: str, vertical: str) -> dict:
    score, issues, tips, checks = 20, [], [], []
    blo = body.lower()
    bts = _text_stems(body)
    kw = _kw_concept(vertical)

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

    if _has(blo, bts, _cta_concept(vertical)):
        score += 18; checks.append({"ok": True, "text": "Призыв к действию: найден"})
    else:
        issues.append({"sev": "critical", "text": "Нет призыва к действию - читатель не знает что делать"})
        checks.append({"ok": False, "text": "Призыв к действию: нет"})

    if _has(blo, bts, _PERS_C):
        score += 10; checks.append({"ok": True, "text": "Персонализация (ты/you): есть"})
    else:
        tips.append('Добавь личное обращение ("ты", "you")')
        checks.append({"ok": False, "text": "Персонализация (ты/you): нет"})

    vhits = _count(blo, bts, kw)
    if vhits >= 2:
        score += 15; checks.append({"ok": True, "text": f"Ключевые слова вертикали: {vhits} найдено"})
    elif vhits == 1:
        score += 8; checks.append({"ok": False, "text": "Ключевые слова вертикали: 1 (добавь ещё)"})
    else:
        tips.append("В теле нет ключевых слов вертикали - оффер не ощущается")
        checks.append({"ok": False, "text": "Ключевые слова вертикали: не найдены"})

    if vertical == "dating":
        emo = _EMO.get(vertical)
        if emo and _has(blo, bts, emo):
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
        ats = _text_stems(anchor)
        if al in _ANCHOR_GEN_SET:
            score -= 8; checks.append({"ok": False, "text": f'Анкор: слишком общий ("{anchor}")'})
            issues.append({"sev": "warning", "text": "Анкор слишком общий - нужен глагол+объект"})
        elif _has(al, ats, _ANCHOR_VB_C):
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
        # НЕ штрафуем и НЕ пугаем: письмо этого проекта маскируется под личное сообщение
        # живого человека (см. CLAUDE.md), а у личного письма НЕТ блока «отписаться» — более
        # того, фейковый unsubscribe в теле сам по себе спам-триггер (он в списке SPAM_BODY).
        # Поэтому отсутствие отписки в теле — это ПРАВИЛЬНО, а не дефект. Показываем как
        # спокойную инфо-строку (без штрафа к баллу), чтобы владелец понимал, почему её нет.
        issues.append({"t": "info", "text": "Ссылки «отписаться» в теле нет — для письма-«личного» "
                       "это правильно (фейковый блок отписки сам по себе спам-триггер). Не дефект."})

    if any(d in low for d in _SHORT):
        score -= 10; issues.append({"t": "bad", "text": "Сокращённые ссылки (bit.ly, t.co…) — фильтры их не любят"})
    if not re.search(r"<!doctype", low):
        score -= 2; issues.append({"t": "warn", "text": "Нет <!DOCTYPE html> — Outlook может рендерить в quirks mode"})
    if not re.search(r"<meta[^>]+charset", low):
        # Тоже НЕ дефект: кодировку письма задаёт заголовок MIME (Content-Type charset=utf-8,
        # см. sender.build_message), а <meta charset> внутри тела почтовые клиенты игнорируют.
        # Инфо без штрафа — чтобы строка не выглядела «проблемой», которую надо чинить.
        issues.append({"t": "info", "text": "<meta charset> в теле нет — и не нужен: кодировку "
                       "задаёт заголовок письма (MIME, utf-8). Не дефект."})
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


# ── ПОЛНОТА ПИСЬМА: есть ли РЕАЛЬНАЯ ссылка и РЕАЛЬНОЕ тело ────────────────────
# ПОЧЕМУ отдельная проверка: скорер charly (и мой 3-осевой расчёт, что его повторяет)
# даёт баллы за СЛОВА-CTA, но НЕ проверяет, что в письме есть настоящая кликабельная
# ссылка с видимым текстом и настоящее тело. Из-за этого письма из скриншотов владельца
# (тело без видимой ссылки; «1 ссылка», но её текст пустой; или вообще один заголовок)
# получали B/78 и уходили в рассылку — а клика по ним быть не может. Эта проверка ловит
# ровно тот брак и делает вердикт честным: неполное письмо нельзя отправлять.
_LINK_TOKEN_RE = re.compile(r"\[\[LINK\d*\]\]")
_URL_RE = re.compile(r"https?://|www\.", re.I)


def _visible_anchor_texts(html: str) -> list[str]:
    """Видимый текст каждой <a>…</a> — то, что реально видит и жмёт получатель.
    `</a\\s*>` — терпим пробел перед «>» (валидный HTML: «</a >»)."""
    out = []
    for raw in re.findall(r"<a\b[^>]*>(.*?)</a\s*>", html, re.I | re.S):
        txt = re.sub(r"<[^>]+>", "", raw)          # убрать вложенные теги
        txt = _LINK_TOKEN_RE.sub("", txt)          # [[LINK]] — это href, не видимый текст
        txt = re.sub(r"\s+", " ", txt).strip()
        out.append(txt)
    return out


def check_completeness(subject: str, body_text: str, html: str,
                       is_html: bool, anchor: str) -> dict:
    """Флагует ровно те браки, что видны в скриншотах владельца:
       (1) нет рабочей ссылки/кнопки; (2) ссылка есть, но её видимый текст пустой
       (<a></a> — «1 ссылка», но кликать визуально не по чему); (3) нет тела —
       один заголовок/ссылка без сообщения. Любой из трёх → письмо НЕПОЛНОЕ."""
    issues, checks = [], []
    complete = True

    # 1) РЕАЛЬНАЯ ссылка + НЕПУСТОЙ видимый якорь
    if is_html:
        a_tags = re.findall(r"<a\b[^>]*>.*?</a\s*>", html, re.I | re.S)
        hrefs = re.findall(r'<a\b[^>]*\bhref\s*=\s*["\']?([^"\'>\s]+)', html, re.I)
        real_href = any(h.strip() and h.strip() != "#" for h in hrefs)
        anchors = [a for a in _visible_anchor_texts(html) if a]
        if not a_tags or not real_href:
            complete = False
            issues.append({"sev": "critical",
                           "text": "❌ В письме НЕТ рабочей ссылки/кнопки (<a href>) — кликать не по чему"})
            checks.append({"ok": False, "text": "Рабочая ссылка/кнопка: НЕТ"})
        elif not anchors:
            complete = False
            issues.append({"sev": "critical",
                           "text": "❌ Ссылка есть, но её видимый текст ПУСТОЙ (<a></a>) — "
                                   "у получателя ссылки не видно (частый брак: якорь попал в пустую ветку спинтакса)"})
            checks.append({"ok": False, "text": "Видимый текст ссылки: ПУСТОЙ"})
        else:
            checks.append({"ok": True, "text": "Рабочая видимая ссылка/кнопка: есть"})
    else:
        has_url = bool(_URL_RE.search(body_text)) or bool(_LINK_TOKEN_RE.search(body_text))
        has_anchor = bool((anchor or "").strip())
        if not (has_url or has_anchor):
            complete = False
            issues.append({"sev": "critical",
                           "text": "❌ В теле нет ссылки ([[LINK]] / URL) — кликать не по чему"})
            checks.append({"ok": False, "text": "Ссылка в теле: НЕТ"})
        else:
            checks.append({"ok": True, "text": "Ссылка в теле: есть"})

    # 2) РЕАЛЬНОЕ тело (не только ссылка/якорь). Считаем «живой» текст без URL, без
    #    [[LINK]] и без видимого текста якоря — чтобы «письмо = одна кнопка» не прошло.
    core = _URL_RE.sub(" ", body_text)
    core = _LINK_TOKEN_RE.sub(" ", core)
    for a in ([anchor] if anchor else []) + (_visible_anchor_texts(html) if is_html else []):
        if a:
            core = core.replace(a, " ")
    core = re.sub(r"\s+", " ", core).strip()
    words = [w for w in core.split() if any(c.isalpha() for c in w)]
    if len(core) < 25 or len(words) < 4:
        complete = False
        issues.append({"sev": "critical",
                       "text": "❌ У письма нет тела — один заголовок/ссылка без сообщения"})
        checks.append({"ok": False, "text": "Тело письма: ПУСТОЕ / только ссылка"})
    else:
        checks.append({"ok": True, "text": f"Тело письма: есть ({len(words)} слов)"})

    return {"complete": complete, "issues": issues, "checks": checks}


# ── ГИББЕРИШ: письмо ли это вообще (порт логики charly ocenka-pisma) ───────────
_MASH = ["ыва", "фыв", "йцу", "ывп", "ыап", "асд", "asd", "qwe", "zxc", "qwer", "asdf", "йфя"]


def _word_looks_random(word: str) -> bool:
    # Настоящее слово имеет высокую долю уникальных букв; клавиатурный набор — низкую.
    w = re.sub(r"[^а-яёa-z]", "", word.lower())
    if len(w) < 5:
        return False
    return len(set(w)) / len(w) < 0.55


def check_gibberish(subject: str, body_text: str) -> bool:
    """True, если тема+тело похожи на случайный набор символов (кот прошёл по клаве
    или спинтакс схлопнулся в мусор). Как у charly: ≥2 клавиатурных последовательности,
    ЛИБО каждое значимое слово выглядит случайным."""
    combined = (subject + " " + body_text).lower()
    if sum(1 for p in _MASH if p in combined) >= 2:
        return True
    tokens = (subject + " " + body_text).split()
    meaningful = [w for w in tokens if len(re.sub(r"[^а-яёa-z]", "", w, flags=re.I)) >= 5]
    if not meaningful:
        return False
    return all(_word_looks_random(w) for w in meaningful)


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
    matches = re.findall(r"<a\b[^>]*>(.*?)</a\s*>", html, re.I | re.S)
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

    # 3-осевой расчёт — ТОЧНАЯ копия charly (числа не трогаем, чтобы совпадать с их
    # оценщиком). Полнота и гиббериш — отдельный слой поверх, он НЕ меняет эти числа,
    # но делает вердикт честным: неполное/мусорное письмо нельзя отправлять.
    dl = _score_deliverability(subject, body_text, vertical)
    orr = _score_openrate(subject, body_text, vertical)
    ctr = _score_clickability(subject, body_text, anchor, vertical)
    overall = _clamp(dl["score"] * 0.30 + orr["score"] * 0.40 + ctr["score"] * 0.30)
    letter, color = _grade(overall)

    contrast = check_contrast(html) if is_html else {"ok": True, "ratio": None,
                                                     "text": "plain text — контраст не важен"}
    structure = check_structure(html, is_html, body_text)
    completeness = check_completeness(subject, body_text, html, is_html, anchor)
    gibberish = check_gibberish(subject, body_text)

    # Вердикт: сначала «стоп-факторы» (мусор / неполное письмо), потом обычный разбор.
    if gibberish:
        verdict = ("⛔ Это не похоже на письмо — набор случайных символов. "
                   "Введи нормальную тему и тело.")
    elif not completeness["complete"]:
        verdict = ("⛔ ПИСЬМО НЕПОЛНОЕ — не отправляй: " +
                   "; ".join(i["text"].lstrip("❌ ").strip() for i in completeness["issues"]))
    else:
        verdict = _verdict(overall, dl["score"], orr["score"], ctr["score"], vertical)

    # Критические браки полноты — В НАЧАЛО списка проблем (их видят первыми).
    issues = completeness["issues"] + dl["issues"] + orr["issues"] + ctr["issues"]

    return {
        "overall": overall, "grade": letter, "grade_color": color,
        "deliverability": dl["score"], "openrate": orr["score"], "clickability": ctr["score"],
        "verdict": verdict,
        "complete": completeness["complete"],   # False → письмо нельзя слать (нет ссылки/тела)
        "gibberish": gibberish,
        "ctr_estimate": _ctr_estimate(ctr["score"], vertical),
        "checks": {"deliverability": dl["checks"], "openrate": orr["checks"],
                   "clickability": ctr["checks"], "completeness": completeness["checks"]},
        "tips": (orr["tips"] + ctr["tips"])[:5],
        "issues": issues,
        "contrast": contrast,
        "structure": structure,
        "vertical": vertical,
        "anchor": anchor,
    }
