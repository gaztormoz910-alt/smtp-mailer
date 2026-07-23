"""content.py — рандомизация контента и спинтакс.

Обработка шаблонов тем, тел писем, ссылок, имён отправителей.
Подстановка переменных, раскрутка спинтакса {вариант1|вариант2}.
Макросы ссылок [[LINK]], [[LINK1]], [[LINK2]] с кешем консистентности.
Авто-определение HTML vs Plain Text.
"""

from __future__ import annotations

import html
import random
import re
from pathlib import Path

from core.storage import load_blocks, load_lines

# Module-level cryptographic RNG (reused across all calls for performance)
_rnd = random.SystemRandom()

# ── Regex ─────────────────────────────────────────────────

_SPINTAX_RE = re.compile(r"\{([^{}]+)\}")
_MACRO_RE   = re.compile(r"\{\{\w+\}\}")
_LINK_RE    = re.compile(r"\[\[LINK(\d*)\]\]")
_HTML_RE    = re.compile(
    r"<(?:html|body|head|div|p|br|table|tr|td|th|a\s+href|img\s|"
    r"h[1-6]|ul|ol|li|span|style|link|meta)[>\s/]",
    re.IGNORECASE,
)

# ── Омоглифы (Анти-фильтр букв) ───────────────────────────
# Только визуально идентичные пары символов.
# Направление замены определяется автоматически по доминирующему алфавиту текста.

# Кириллица → Латиница (для русскоязычных писем)
_HOMOGLYPHS_CYR_TO_LAT = {
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'х': 'x', 'у': 'y',
    'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 'О': 'O',
    'Р': 'P', 'С': 'C', 'Т': 'T', 'Х': 'X',
    'і': 'i', 'І': 'I', 'ѕ': 's', 'Ѕ': 'S'
}

# Латиница → Кириллица (для англоязычных писем)
_HOMOGLYPHS_LAT_TO_CYR = {v: k for k, v in _HOMOGLYPHS_CYR_TO_LAT.items()}

def _detect_dominant_script(text: str) -> str:
    """Определяет доминирующий алфавит текста: 'cyrillic' или 'latin'.
    Считает количество кириллических и латинских букв и возвращает тот,
    которого больше.
    """
    cyr_count = 0
    lat_count = 0
    for ch in text:
        code = ord(ch)
        if 0x0400 <= code <= 0x04FF:    # Кириллица (Unicode block)
            cyr_count += 1
        elif (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):  # A-Z, a-z
            lat_count += 1
    return 'cyrillic' if cyr_count >= lat_count else 'latin'

# Списке случайных слов для генерации белого шума (текста)
_NOISE_WORDS = [
    "clarity", "density", "factor", "random", "profile", "element", "system",
    "network", "channel", "message", "status", "context", "index", "vector",
    "domain", "server", "proxy", "config", "header", "subject", "content",
    "delivery", "account", "volume", "sender", "route", "filter", "security",
    "process", "thread", "queue", "client", "request", "response", "source"
]

def _generate_noise_text(word_count: int = 15) -> str:
    """Генерирует случайную фразу для белого шума."""
    rnd = random.SystemRandom()
    words = [rnd.choice(_NOISE_WORDS) for _ in range(word_count)]
    return " ".join(words)

def _generate_random_id(length: int = 8) -> str:
    """Генерирует случайный ID (буквы + цифры)."""
    rnd = random.SystemRandom()
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(rnd.choice(chars) for _ in range(length))



# ── Спинтакс ──────────────────────────────────────────────

def spin(text: str) -> str:
    """Рекурсивно раскрывает спинтакс ``{opt1|opt2|opt3}``.

    Обрабатывает вложенные конструкции **любой глубины**.
    Защищает переменные {{var}} от случайного раскрытия.
    """
    # 1. Прячем переменные типа {{name}}, чтобы они не сломались
    hidden_vars = []
    def _hide(m: re.Match) -> str:
        hidden_vars.append(m.group(0))
        return f"__VAR_{len(hidden_vars)-1}__"
    
    text = _MACRO_RE.sub(_hide, text)

    # 2. Раскрываем спинтакс изнутри наружу
    while _SPINTAX_RE.search(text):
        text = _SPINTAX_RE.sub(
            lambda m: _rnd.choice(m.group(1).split("|")),
            text,
        )
        
    # 3. Восстанавливаем переменные
    for i, var_val in enumerate(hidden_vars):
        text = text.replace(f"__VAR_{i}__", var_val)

    return text


# ── Ссылки [[LINK]], [[LINK1]] ────────────────────────────

def substitute_links(
    text: str,
    pools: dict[str, list[str]],
    cache: dict[str, str] | None = None,
) -> str:
    """Заменяет ``[[LINK]]``, ``[[LINK1]]`` и т.д. на URL из пулов.
    Каждая ссылка получает уникальный GET-параметр для обхода фильтров.
    """
    missing: set[str] = set()

    def _randomize_url(url: str) -> str:
        """Добавляет случайный GET-хвост к URL для полной уникальности.
        Корректно обрабатывает хэши/якоря (#) в конце ссылок.
        """
        if not url:
            return url
            
        # Отделяем хэш (#anchor), если он есть
        hash_part = ""
        if "#" in url:
            url, hash_part = url.split("#", 1)
            hash_part = "#" + hash_part

        param_name = _rnd.choice([
            "id", "sid", "tid", "hash", "token", "uid", "utm_id",
            "ref", "src", "tag", "v", "click", "cid", "pid", "rid",
            "mid", "sub", "track", "r", "s", "t", "key", "code",
            "session", "view", "page", "via", "c", "u", "q", "x",
            "nonce", "sig", "ts", "seq", "idx", "ver", "rev", "chk",
            "data", "p", "f", "m", "w", "h", "d", "e", "n", "o",
        ])
        param_val = _generate_random_id(8)
        
        # Если в URL уже есть параметры
        if "?" in url:
            randomized = f"{url}&{param_name}={param_val}"
        else:
            randomized = f"{url}?{param_name}={param_val}"
            
        # Склеиваем обратно с хэшем
        return randomized + hash_part

    def _repl(m: re.Match) -> str:
        key = m.group(1)              # "" для [[LINK]], "1" для [[LINK1]]
        pool = pools.get(key)
        if not pool:
            missing.add(f"[[LINK{key}]]")
            return m.group(0)
            
        if cache is not None:
            if key not in cache:
                raw_url = _rnd.choice(pool)
                cache[key] = _randomize_url(raw_url)
            return cache[key]
            
        return _randomize_url(_rnd.choice(pool))

    result = _LINK_RE.sub(_repl, text)

    if missing:
        raise ValueError(f"No links loaded for: {', '.join(sorted(missing))}")
    return result


# ── Макросы {{name}}, {{email}} ───────────────────────────

def substitute(text: str, variables: dict[str, str]) -> str:
    """Заменяет ``{{key}}`` значениями.  Нераспознанные макросы удаляются."""
    for key, val in variables.items():
        text = text.replace("{{" + key + "}}", val)
    text = _MACRO_RE.sub("", text)
    return text.strip()


# ── HTML-детект ───────────────────────────────────────────

def is_html(text: str) -> bool:
    return bool(_HTML_RE.search(text))


_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_BLOCK_END_RE = re.compile(r'</(p|div|h[1-6]|li|tr)>', re.IGNORECASE)
_A_TAG_RE = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_ANY_TAG_RE = re.compile(r'<[^>]+>')
_MULTI_NL_RE = re.compile(r'\n{3,}')
_LEADING_SPACE_RE = re.compile(r'^[ \t]+', re.MULTILINE)

# ── HTML to Plain Text ────────────────────────────────────

def html_to_plain_text(text: str) -> str:
    """Конвертирует HTML в простой текст, сохраняя ссылки и переносы."""
    if not is_html(text):
        return text
    
    # 1. <br> -> \n
    text = _BR_RE.sub('\n', text)
    
    # 2. Окончания блоков -> \n
    text = _BLOCK_END_RE.sub('\n', text)
    
    # 3. Извлечение ссылок: <a href="url">text</a> -> text url
    def link_repl(match):
        url = match.group(1)
        link_text = match.group(2).strip()
        link_text = _ANY_TAG_RE.sub('', link_text)
        if link_text:
            return f"{link_text} {url}"
        return url
        
    text = _A_TAG_RE.sub(link_repl, text)
    
    # 4. Удаление всех остальных тегов
    text = _ANY_TAG_RE.sub('', text)
    
    # 5. Декодирование HTML-сущностей
    text = html.unescape(text)
    
    # 6. Очистка лишних пустых строк (оставляем максимум двойные)
    text = _MULTI_NL_RE.sub('\n\n', text)
    
    # 7. Убираем пробелы (отступы) в начале каждой строки (остатки от форматирования HTML)
    text = _LEADING_SPACE_RE.sub('', text)
    
    return text.strip()


# ── Render pipeline ──────────────────────────────────────

# Регулярные выражения для новых макросов AMS стиля
_RND_STRING_RE = re.compile(r"\[%%RndString\((\d+)\)%%\]")
_RND_NUMBER_RE = re.compile(r"\[%%RndNumber\((\d+),(\d+)\)%%\]")

def _substitute_ams_macros(text: str) -> str:
    """Обрабатывает макросы [%%RndString(8)%%] и [%%RndNumber(100,200)%%]."""
    # 1. RndString
    def rnd_str_repl(m):
        length = int(m.group(1))
        return _generate_random_id(length)
    text = _RND_STRING_RE.sub(rnd_str_repl, text)

    # 2. RndNumber
    def rnd_num_repl(m):
        lo, hi = int(m.group(1)), int(m.group(2))
        return str(random.SystemRandom().randint(lo, hi))
    text = _RND_NUMBER_RE.sub(rnd_num_repl, text)
    
    return text

def _replace_homoglyphs(text: str, rate: float = 0.0) -> str:
    """Двусторонняя замена визуально идентичных букв между алфавитами.

    Автоматически определяет доминирующий алфавит текста:
    - Русский текст → часть кириллических букв заменяется на латинские
    - Английский текст → часть латинских букв заменяется на кириллические
    НЕ затрагивает HTML-теги, ссылки, CSS-стили и текст внутри <a> тегов.
    Rate рандомизируется per-email (3-12%) если не задан явно.
    """
    rnd = random.SystemRandom()
    # Рандомизация rate per-email если не задан
    if rate <= 0:
        rate = rnd.uniform(0.03, 0.12)

    # Разбиваем на: HTML-теги, <a>...</a> блоки целиком, и обычный текст
    _a_block_re = re.compile(r'(<a\s[^>]*>.*?</a>)', re.IGNORECASE | re.DOTALL)
    # Сначала защищаем <a> блоки
    a_blocks = []
    def _hide_a(m):
        a_blocks.append(m.group(0))
        return f'__ABLOCK_{len(a_blocks)-1}__'
    text = _a_block_re.sub(_hide_a, text)

    # Собираем только текстовые части (без HTML-тегов) для определения языка
    parts = re.split(r'(<[^>]+>)', text)
    text_only = ''.join(parts[i] for i in range(0, len(parts), 2))

    # Определяем направление замены
    script = _detect_dominant_script(text_only)
    if script == 'cyrillic':
        homoglyph_map = _HOMOGLYPHS_CYR_TO_LAT
    else:
        homoglyph_map = _HOMOGLYPHS_LAT_TO_CYR

    for i in range(len(parts)):
        # Четные индексы — обычный текст вне тегов
        if i % 2 == 0:
            chars = list(parts[i])
            for j, char in enumerate(chars):
                if char in homoglyph_map and rnd.random() < rate:
                    chars[j] = homoglyph_map[char]
            parts[i] = ''.join(chars)
    result = ''.join(parts)

    # Восстанавливаем <a> блоки
    for i, block in enumerate(a_blocks):
        result = result.replace(f'__ABLOCK_{i}__', block)
    return result


# ── Безопасная уникализация HTML (без spam-триггеров) ─────

_CSS_NOISE_PROPS = [
    "mso-line-height-rule:exactly;",
    "-webkit-text-size-adjust:100%;",
    "-ms-text-size-adjust:100%;",
    "mso-table-lspace:0pt;",
    "mso-table-rspace:0pt;",
    "word-break:break-word;",
    "border-spacing:0;",
    "-webkit-font-smoothing:antialiased;",
    "text-rendering:optimizeLegibility;",
    "mso-style-priority:100;",
    "font-variant-ligatures:normal;",
    "text-decoration-skip-ink:auto;",
    "-moz-osx-font-smoothing:grayscale;",
    "orphans:2;",
    "widows:2;",
]


def _generate_realistic_comment() -> str:
    """Генерирует реалистичный HTML-комментарий.
    БЕЗ Outlook conditional comments (они ломают вёрстку если не парные).
    Только безопасные build/version/section/campaign markers.
    """
    _rid = lambda n: ''.join(_rnd.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(n))
    _word = lambda: _rnd.choice([
        'header', 'footer', 'content', 'main', 'wrapper', 'layout',
        'body', 'container', 'section', 'module', 'block', 'row',
        'column', 'card', 'text', 'image', 'button', 'spacer',
        'divider', 'banner', 'nav', 'hero', 'cta', 'sidebar',
    ])
    templates = [
        # Build / version markers
        f"<!-- v{_rnd.randint(1,9)}.{_rnd.randint(0,99)}.{_rnd.randint(0,999)} -->",
        f"<!-- build:{_rid(8)} -->",
        f"<!-- {_rid(6)}-{_rid(4)}-{_rid(4)} -->",
        f"<!-- rev:{_rid(6)} {_rnd.randint(2023,2026)}-{_rnd.randint(1,12):02d}-{_rnd.randint(1,28):02d} -->",
        # Template system / CMS markers
        f"<!-- section:{_word()} -->",
        f"<!-- /section:{_word()} -->",
        f"<!-- block:{_word()}_{_rnd.randint(1,99)} -->",
        f"<!-- /block -->",
        f"<!-- region:{_word()} -->",
        f"<!-- template:{_word()}_{_rid(4)} -->",
        # Marketing platform markers (Mailchimp, SendGrid, etc.)
        f"<!-- mc:variant=\"{_word()}\" -->",
        f"<!-- sg:{_rid(8)} -->",
        f"<!-- campaign:{_rid(12)} -->",
        f"<!-- email-id:{_rid(8)}-{_rid(4)}-{_rid(4)}-{_rid(12)} -->",
        f"<!-- batch:{_rnd.randint(1000,9999)} -->",
        # Misc common patterns
        f"<!-- {_rnd.randint(2023,2026)}-{_rnd.randint(1,12):02d}-{_rnd.randint(1,28):02d}T{_rnd.randint(0,23):02d}:{_rnd.randint(0,59):02d} -->",
        f"<!-- auto-generated -->",
        f"<!-- do not edit below this line -->",
        f"<!-- E{_rnd.randint(100,999)} -->",
        f"<!-- ID:{_rid(16)} -->",
        f"<!-- editable:{_word()} -->",
        f"<!-- /editable -->",
        f"<!-- {_word()} start -->",
        f"<!-- {_word()} end -->",
    ]
    return _rnd.choice(templates)


def _randomize_html_entities(text: str, rate: float = 0.03) -> str:
    """Заменяет ~3% букв в тексте на HTML-entity эквиваленты.
    Визуально ничего не меняется, но исходный код письма уникален.
    Обрабатывает ТОЛЬКО текстовые ноды (не трогает HTML-теги и атрибуты).
    """
    parts = re.split(r'(<[^>]+>)', text)
    for i in range(0, len(parts), 2):
        if parts[i]:
            chars = list(parts[i])
            for j, char in enumerate(chars):
                if char.isalpha() and _rnd.random() < rate:
                    code = ord(char)
                    fmt = _rnd.choice(['dec', 'hex', 'hex_upper'])
                    if fmt == 'dec':
                        chars[j] = f"&#{code};"
                    elif fmt == 'hex':
                        chars[j] = f"&#x{code:x};"
                    else:
                        chars[j] = f"&#x{code:X};"
            parts[i] = ''.join(chars)
    return ''.join(parts)


def _inject_css_noise(text: str) -> str:
    """Добавляет безвредные CSS-свойства в существующие inline-стили.
    Это стандартные MSO/Webkit свойства, которые используются во всех
    легитимных маркетинговых рассылках (Mailchimp, SendGrid, etc.).
    Вероятность рандомизируется per-email (20-50%).
    """
    css_rate = _rnd.uniform(0.20, 0.50)
    def _add_noise(m: re.Match) -> str:
        style = m.group(0)
        if _rnd.random() < css_rate:
            prop = _rnd.choice(_CSS_NOISE_PROPS)
            # Вставляем перед закрывающей кавычкой, с гарантированным ;
            if style.endswith('"'):
                inner = style[7:-1]  # style="..." → ...
                if inner and not inner.rstrip().endswith(';'):
                    inner += ';'
                return f'style="{inner}{prop}"'
            elif style.endswith("'"):
                inner = style[7:-1]
                if inner and not inner.rstrip().endswith(';'):
                    inner += ';'
                return f"style='{inner}{prop}'"
        return style
    return re.sub(r'style="[^"]*"', _add_noise, text, flags=re.IGNORECASE)


def render(
    template: str,
    variables: dict[str, str] | None = None,
    link_pools: dict[str, list[str]] | None = None,
    link_cache: dict[str, str] | None = None,
    is_subject: bool = False,
) -> str:
    """Полный пайплайн рандомизации.

    is_subject=True:  облегчённый режим для тем (без омоглифов, без HTML-шума).
    is_subject=False: полный режим для тела письма (максимальная уникализация).
    """
    # Определяем формат шаблона ДО модификаций
    original_is_html = is_html(template)

    # 1. Спинтакс
    result = spin(template)

    # 2. Ссылки [[LINK]] с уникальными GET-хвостами
    if _LINK_RE.search(result):
        if not link_pools:
            raise ValueError(
                "Template contains [[LINK]] macros but no link pools loaded"
            )
        result = substitute_links(result, link_pools, cache=link_cache)

    # 3. Переменные получателя {{name}}, {{email}}
    if variables:
        result = substitute(result, variables)

    # 4. AMS макросы [%%RndString%%], [%%RndNumber%%]
    result = _substitute_ams_macros(result)

    # ── Для Subject: на этом всё (без омоглифов, без шума) ──
    if is_subject:
        return result

    # ── Ниже — только для тела письма (Body) ──

    # 5. Омоглифы (визуально идентичная подмена букв, rate рандомизируется 3-12%)
    result = _replace_homoglyphs(result)  # rate=0 → авторандом 3-12%

    # 6. Уникализация HTML (безопасные методы без spam-триггеров)
    if original_is_html:
        # 6a. HTML entity randomization (rate рандомизируется 1-5%)
        entity_rate = _rnd.uniform(0.01, 0.05)
        result = _randomize_html_entities(result, rate=entity_rate)

        # 6b. CSS noise (безвредные MSO/Webkit свойства)
        result = _inject_css_noise(result)

        # 6c. Реалистичные HTML-комментарии (безопасные, без Outlook conditional)
        block_tags = ["</div>", "</p>", "</td>", "</tr>", "</th>", "</ul>", "</ol>", "</li>"]
        for _ in range(_rnd.randint(2, 5)):
            comment = _generate_realistic_comment()
            found_positions = []
            for tag in block_tags:
                for match_pos in re.finditer(re.escape(tag), result, re.IGNORECASE):
                    found_positions.append(match_pos.end())
            if found_positions:
                idx = _rnd.choice(found_positions)
                result = result[:idx] + comment + result[idx:]

        # 6d. Zero-Width символы для байтовой уникальности
        _ZW_CHARS = ['\u200B', '\u200C', '\u200D', '\u2060', '\uFEFF']
        zw_count = _rnd.randint(2, 6)
        # Вставляем только в текстовые ноды (не в теги)
        text_parts = re.split(r'(<[^>]+>)', result)
        text_indices = [i for i in range(0, len(text_parts), 2) if text_parts[i].strip()]
        if text_indices:
            for _ in range(zw_count):
                idx = _rnd.choice(text_indices)
                s = text_parts[idx]
                if len(s) > 1:
                    pos = _rnd.randint(1, len(s) - 1)
                    text_parts[idx] = s[:pos] + _rnd.choice(_ZW_CHARS) + s[pos:]
            result = ''.join(text_parts)

        # 6e. Рандомизация пробелов HTML (уникальный исходный код)
        def _randomize_whitespace(m):
            tag = m.group(0)
            # Случайный пробел перед >
            if _rnd.random() < 0.15 and not tag.endswith('/>'):
                tag = tag[:-1] + ' >'
            return tag
        result = re.sub(r'<[^>]+>', _randomize_whitespace, result)

    return result


# ── Утилита: ключ пула из имени файла ────────────────────

_POOL_KEY_RE = re.compile(r"(\d+)$")


def pool_key_from_filename(filename: str) -> str:
    """``links.txt`` → ``""``,  ``links1.txt`` → ``"1"``,  ``links2.txt`` → ``"2"``."""
    stem = Path(filename).stem           # "links1"
    m = _POOL_KEY_RE.search(stem)
    return m.group(1) if m else ""


# ── Менеджер контента ─────────────────────────────────────


class ContentManager:
    """Хранит и генерирует темы, тела, ссылки, имена отправителей."""

    def __init__(self) -> None:
        self._subjects: list[str] = []
        self._bodies: list[str] = []
        self._link_pools: dict[str, list[str]] = {}       # key → urls
        self._link_files: list[tuple[str, str, int]] = []  # (filename, key, count)
        self._sender_names: list[str] = []                 # задача 10
        self.consistent_links: bool = False
        self.email_only: bool = False

    # ══════════════════════════════════════════════════════
    #  SUBJECTS
    # ══════════════════════════════════════════════════════

    @property
    def subjects(self) -> list[str]:
        return list(self._subjects)

    @property
    def subject_count(self) -> int:
        return len(self._subjects)

    def load_subjects(self, filepath: str) -> int:
        lines = load_lines(filepath)
        self._subjects.extend(lines)
        return len(lines)

    def clear_subjects(self) -> None:
        self._subjects.clear()

    def get_random_subject(
        self,
        variables: dict[str, str] | None = None,
        link_cache: dict[str, str] | None = None,
    ) -> str:
        if not self._subjects:
            return ""
        template = _rnd.choice(self._subjects)
        pools = self._link_pools if self._link_pools else None
        return render(template, variables, pools, link_cache, is_subject=True)

    # ══════════════════════════════════════════════════════
    #  BODIES
    # ══════════════════════════════════════════════════════

    @property
    def bodies(self) -> list[str]:
        return list(self._bodies)

    @property
    def body_count(self) -> int:
        return len(self._bodies)

    def load_bodies(self, filepath: str) -> int:
        blocks = load_blocks(filepath, separator="===END===")
        self._bodies.extend(blocks)
        return len(blocks)

    def clear_bodies(self) -> None:
        self._bodies.clear()

    def get_random_body(
        self,
        variables: dict[str, str] | None = None,
        link_cache: dict[str, str] | None = None,
    ) -> tuple[str, bool]:
        if not self._bodies:
            return ("", False)
        template = _rnd.choice(self._bodies)
        pools = self._link_pools if self._link_pools else None
        rendered = render(template, variables, pools, link_cache)
        is_html_body = is_html(rendered)
        return (rendered, is_html_body)

    # ══════════════════════════════════════════════════════
    #  LINKS
    # ══════════════════════════════════════════════════════

    @property
    def link_pools(self) -> dict[str, list[str]]:
        return dict(self._link_pools)

    @property
    def link_files(self) -> list[tuple[str, str, int]]:
        """Список ``(filename, pool_key, count)``."""
        return list(self._link_files)

    @property
    def link_pool_count(self) -> int:
        return len(self._link_pools)

    def load_links_file(self, filepath: str) -> tuple[str, int]:
        """Загружает ссылки из файла. Пул определяется порядком загрузки 
        (1-й файл -> "", 2-й -> "1", и т.д.).
        
        Возвращает ``(pool_key, count)``.
        """
        filename = Path(filepath).name
        urls = load_lines(filepath)
        
        # Ищем, загружался ли уже этот файл, чтобы добавить в тот же пул
        existing_keys = [k for fname, k, _ in self._link_files if fname == filename]
        if existing_keys:
            key = existing_keys[0]
        else:
            num_pools = len(self._link_pools)
            key = "" if num_pools == 0 else str(num_pools)
        
        if key in self._link_pools:
            self._link_pools[key].extend(urls)
        else:
            self._link_pools[key] = urls
            
        # Обновляем список загруженных файлов
        self._link_files.append((filename, key, len(urls)))
        # Сортируем для красоты (пустые ключи первые, потом по числу)
        self._link_files.sort(key=lambda x: int(x[1]) if x[1].isdigit() else 0)
        return key, len(urls)

    def clear_links(self) -> None:
        self._link_pools.clear()
        self._link_files.clear()

    # ══════════════════════════════════════════════════════
    #  SENDER NAMES
    # ══════════════════════════════════════════════════════

    @property
    def sender_names(self) -> list[str]:
        return list(self._sender_names)

    @property
    def sender_name_count(self) -> int:
        return len(self._sender_names)

    def load_sender_names(self, filepath: str) -> int:
        """Загружает имена отправителей из файла (одно имя на строку)."""
        lines = load_lines(filepath)
        self._sender_names.extend(lines)
        return len(lines)

    def clear_sender_names(self) -> None:
        self._sender_names.clear()

    def get_random_sender_name(self) -> str:
        """Случайное имя из списка (или пустая строка)."""
        if not self._sender_names or self.email_only:
            return ""
        return _rnd.choice(self._sender_names)

