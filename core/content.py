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

_SPINTAX_RE = re.compile(r"\{([^{}]+)\}")
_MACRO_RE   = re.compile(r"\{\{\w+\}\}")
_LINK_RE    = re.compile(r"\[\[LINK(\d*)\]\]")
_HTML_RE    = re.compile(
    r"<(?:html|body|head|div|p|br|table|tr|td|th|a\s+href|img\s|"
    r"h[1-6]|ul|ol|li|span|style|link|meta)[>\s/]",
    re.IGNORECASE,
)


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

    ``pools`` — словарь ``{"": [urls...], "1": [urls...], ...}``.
    ``cache`` — если передан dict, включает режим consistent links
    (одна и та же ссылка для одного макроса внутри одного письма).
    Если пул не найден — ``ValueError``.
    """
    missing: set[str] = set()

    def _repl(m: re.Match) -> str:
        key = m.group(1)              # "" для [[LINK]], "1" для [[LINK1]]
        pool = pools.get(key)
        if not pool:
            missing.add(f"[[LINK{key}]]")
            return m.group(0)         # оставляем как есть для диагностики
        if cache is not None:
            if key not in cache:
                cache[key] = random.choice(pool)
            return cache[key]
        return random.choice(pool)

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


# ── HTML to Plain Text ────────────────────────────────────

def html_to_plain_text(text: str) -> str:
    """Конвертирует HTML в простой текст, сохраняя ссылки и переносы."""
    if not is_html(text):
        return text
    
    # 1. <br> -> \n
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    # 2. Окончания блоков -> \n
    text = re.sub(r'</(p|div|h[1-6]|li|tr)>', '\n', text, flags=re.IGNORECASE)
    
    # 3. Извлечение ссылок: <a href="url">text</a> -> text url
    def link_repl(match):
        url = match.group(1)
        link_text = match.group(2).strip()
        link_text = re.sub(r'<[^>]+>', '', link_text)
        if link_text:
            return f"{link_text} {url}"
        return url
        
    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', link_repl, text, flags=re.IGNORECASE|re.DOTALL)
    
    # 4. Удаление всех остальных тегов
    text = re.sub(r'<[^>]+>', '', text)
    
    # 5. Декодирование HTML-сущностей
    text = html.unescape(text)
    
    # 6. Очистка лишних пустых строк (оставляем максимум двойные)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 7. Убираем пробелы (отступы) в начале каждой строки (остатки от форматирования HTML)
    text = re.sub(r'^[ \t]+', '', text, flags=re.MULTILINE)
    
    return text.strip()


# ── Render pipeline ──────────────────────────────────────

def render(
    template: str,
    variables: dict[str, str] | None = None,
    link_pools: dict[str, list[str]] | None = None,
    link_cache: dict[str, str] | None = None,
) -> str:
    """Полный пайплайн: спинтакс → ссылки → макросы.

    Порядок: spin ▸ [[LINK]] ▸ {{var}}.
    Если в тексте есть ``[[LINK...]]``, а ``link_pools`` пуст — ``ValueError``.
    """
    result = spin(template)
    if _LINK_RE.search(result):
        if not link_pools:
            raise ValueError(
                "Template contains [[LINK]] macros but no link pools loaded"
            )
        result = substitute_links(result, link_pools, cache=link_cache)
    if variables:
        result = substitute(result, variables)
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
        self._subjects = load_lines(filepath)
        return len(self._subjects)

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
        self._bodies = load_blocks(filepath, separator="===END===")
        return len(self._bodies)

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
        rendered = html_to_plain_text(rendered)
        return (rendered, False)

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
        self._link_pools[key] = urls
        # обновляем или добавляем запись
        self._link_files = [
            (fn, k, c) for fn, k, c in self._link_files if k != key
        ]
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
        self._sender_names = load_lines(filepath)
        return len(self._sender_names)

    def clear_sender_names(self) -> None:
        self._sender_names.clear()

    def get_random_sender_name(self) -> str:
        """Случайное имя из списка (или пустая строка)."""
        if not self._sender_names or self.email_only:
            return ""
        return random.choice(self._sender_names)

