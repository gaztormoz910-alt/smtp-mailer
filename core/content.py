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

# ── Regex ─────────────────────────────────────────────────

_SPINTAX_RE = re.compile(r"(?<!\{)\{([^{}]+)\}(?!\})")
_MACRO_RE   = re.compile(r"\{\{\w+\}\}")
_LINK_RE    = re.compile(r"\[\[LINK(\d*)\]\]")
_HTML_RE    = re.compile(
    r"<(?:html|body|head|div|p|br|table|tr|td|th|a\s+href|img\s|"
    r"h[1-6]|ul|ol|li|span|style|link|meta)[>\s/]",
    re.IGNORECASE,
)

# ── Омоглифы (Анти-фильтр букв) ───────────────────────────
_HOMOGLYPHS = {
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'х': 'x', 'у': 'y',
    'А': 'A', 'Е': 'E', 'О': 'O', 'Р': 'P', 'С': 'C', 'Х': 'X', 'У': 'Y',
    'і': 'i', 'І': 'I', 'ѕ': 's', 'Ѕ': 'S', 'м': 'm', 'М': 'M', 'т': 't',
    'Т': 'T', 'н': 'h', 'Н': 'H', 'к': 'k', 'К': 'K', 'в': 'b', 'В': 'B'
}

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

def _replace_homoglyphs(text: str, rate: float = 0.08) -> str:
    """Случайно заменяет схожие русские буквы на латинские (по умолчанию ~8% букв)."""
    rnd = random.SystemRandom()
    chars = list(text)
    for i, char in enumerate(chars):
        if char in _HOMOGLYPHS and rnd.random() < rate:
            chars[i] = _HOMOGLYPHS[char]
    return "".join(chars)


# ── Спинтакс ──────────────────────────────────────────────

def spin(text: str) -> str:
    """Рекурсивно раскрывает спинтакс ``{opt1|opt2|opt3}``.

    Обрабатывает вложенные конструкции **любой глубины**:
    сначала самые внутренние, затем наружу (цикл while).
    """
    while _SPINTAX_RE.search(text):
        text = _SPINTAX_RE.sub(
            lambda m: random.choice(m.group(1).split("|")),
            text,
        )
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
        """Добавляет случайный GET-хвост к URL для полной уникальности."""
        if not url:
            return url
        # Генерируем случайный ключ и значение (например: ?utm_id=a8f2k3s9)
        param_name = random.choice(["id", "sid", "tid", "hash", "token", "uid", "utm_id"])
        param_val = _generate_random_id(8)
        
        # Если в URL уже есть параметры
        if "?" in url:
            return f"{url}&{param_name}={param_val}"
        return f"{url}?{param_name}={param_val}"

    def _repl(m: re.Match) -> str:
        key = m.group(1)              # "" для [[LINK]], "1" для [[LINK1]]
        pool = pools.get(key)
        if not pool:
            missing.add(f"[[LINK{key}]]")
            return m.group(0)
            
        if cache is not None:
            if key not in cache:
                raw_url = random.choice(pool)
                cache[key] = _randomize_url(raw_url)
            return cache[key]
            
        return _randomize_url(random.choice(pool))

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

def _replace_homoglyphs(text: str, rate: float = 0.08) -> str:
    """Случайно заменяет схожие русские буквы на латинские только в тексте.
    НЕ затрагивает HTML-теги, ссылки и CSS-стили, чтобы ничего не сломать.
    """
    rnd = random.SystemRandom()
    # Разделяем текст по HTML-тегам
    parts = re.split(r'(<[^>]+>)', text)
    for i in range(len(parts)):
        # Четные индексы (0, 2, 4...) — это обычный текст вне тегов
        if i % 2 == 0:
            chars = list(parts[i])
            for j, char in enumerate(chars):
                if char in _HOMOGLYPHS and rnd.random() < rate:
                    chars[j] = _HOMOGLYPHS[char]
            parts[i] = "".join(chars)
    return "".join(parts)

def render(
    template: str,
    variables: dict[str, str] | None = None,
    link_pools: dict[str, list[str]] | None = None,
    link_cache: dict[str, str] | None = None,
) -> str:
    """Полный пайплайн 101% рандомизации:
    Спинтакс -> Ссылки -> Макросы -> AMS макросы -> Омоглифы -> Уникализация (HTML/Text).
    """
    # Определяем формат оригинального шаблона ДО каких-либо модификаций
    original_is_html = is_html(template)

    # 1. Спинтакс
    result = spin(template)
    
    # 2. Ссылки [[LINK]] с автоматическими GET-хвостами
    if _LINK_RE.search(result):
        if not link_pools:
            raise ValueError(
                "Template contains [[LINK]] macros but no link pools loaded"
            )
        result = substitute_links(result, link_pools, cache=link_cache)
        
    # 3. Базовые переменные получателя {{name}}, {{email}}
    if variables:
        result = substitute(result, variables)
        
    # 4. Обработка AMS макросов [%%RndString%%] и [%%RndNumber%%]
    result = _substitute_ams_macros(result)
    
    # 5. Анти-фильтр: Замена схожих кириллических букв на латиницу в тексте
    result = _replace_homoglyphs(result, rate=0.08)

    # 6. Уникализация контента
    if original_is_html:
        # 6a. Добавляем невидимый белый шум в конец body (12-22 случайных слов)
        noise_word_count = random.SystemRandom().randint(12, 22)
        noise_text = _generate_noise_text(noise_word_count)
        noise_html = (
            f'<div style="display:none !important; font-size:1px; color:#ffffff; '
            f'line-height:1px; opacity:0; filter:alpha(opacity=0);">'
            f'{noise_text}</div>'
        )
        
        if "</body>" in result:
            result = result.replace("</body>", f"{noise_html}</body>")
        elif "</html>" in result:
            result = result.replace("</html>", f"{noise_html}</html>")
        else:
            result = f"{result}{noise_html}"
            
        # 6b. Вставляем HTML-комментарии строго ПОСЛЕ закрывающих тегов разметки
        # Это гарантирует, что мы не сломаем синтаксис внутри тегов (например, <a <!-- --> href="...">)
        block_tags = ["</div>", "</p>", "</td>", "</tr>", "</th>", "</ul>", "</ol>", "</li>", "<br>", "<br/>"]
        for _ in range(3):
            comment = f"<!-- {_generate_random_id(12)} -->"
            found_positions = []
            for tag in block_tags:
                for m in re.finditer(re.escape(tag), result, re.IGNORECASE):
                    found_positions.append(m.end())
            if found_positions:
                idx = random.SystemRandom().choice(found_positions)
                result = result[:idx] + comment + result[idx:]
    else:
        # Для Plain Text писем добавляем текстовый шум в самом низу через отступы
        noise_text = _generate_noise_text(6)
        result = f"{result}\n\n\n\n\n[ {noise_text} ]"

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
        template = random.choice(self._subjects)
        pools = self._link_pools if self._link_pools else None
        return render(template, variables, pools, link_cache)

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
        template = random.choice(self._bodies)
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
        """Загружает ссылки из файла.  Пул определяется по имени файла.

        Возвращает ``(pool_key, count)``.
        """
        filename = Path(filepath).name
        key = pool_key_from_filename(filename)
        urls = load_lines(filepath)
        
        if key in self._link_pools:
            self._link_pools[key].extend(urls)
        else:
            self._link_pools[key] = urls
            
        # Обновляем список загруженных файлов (просто добавляем)
        self._link_files.append((filename, key, len(urls)))
        self._link_files.sort(key=lambda x: x[1])
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
        return random.choice(self._sender_names)

