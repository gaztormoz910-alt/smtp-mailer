

from __future__ import annotations

import html
import random
import re
from pathlib import Path

from core.storage import load_blocks, load_lines

_rnd = random.SystemRandom()


_SPINTAX_RE = re.compile(r"\{([^{}]+)\}")
_MACRO_RE   = re.compile(r"\{\{\w+\}\}")
_LINK_RE    = re.compile(r"\[\[LINK(\d*)\]\]")
_HTML_RE    = re.compile(
    r"<(?:html|body|head|div|p|br|table|tr|td|th|a\s+href|img\s|"
    r"h[1-6]|ul|ol|li|span|style|link|meta)[>\s/]",
    re.IGNORECASE,
)


# Омоглифы (кир↔лат) удалены в 2026: почтовые ML-фильтры нормализуют confusable-символы
# ДО анализа и флагуют их наличие как спуфинг/фишинг — польза нулевая, риск реальный.

_NOISE_WORDS = [
    "clarity", "density", "factor", "random", "profile", "element", "system",
    "network", "channel", "message", "status", "context", "index", "vector",
    "domain", "server", "proxy", "config", "header", "subject", "content",
    "delivery", "account", "volume", "sender", "route", "filter", "security",
    "process", "thread", "queue", "client", "request", "response", "source"
]

def _generate_noise_text(word_count: int = 15) -> str:
    rnd = random.SystemRandom()
    words = [rnd.choice(_NOISE_WORDS) for _ in range(word_count)]
    return " ".join(words)

def _generate_random_id(length: int = 8) -> str:
    rnd = random.SystemRandom()
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(rnd.choice(chars) for _ in range(length))


def spin(text: str) -> str:

    hidden_vars = []
    def _hide(m: re.Match) -> str:
        hidden_vars.append(m.group(0))
        return f"__VAR_{len(hidden_vars)-1}__"
    
    text = _MACRO_RE.sub(_hide, text)

    while _SPINTAX_RE.search(text):
        text = _SPINTAX_RE.sub(
            lambda m: _rnd.choice(m.group(1).split("|")),
            text,
        )
        
    for i, var_val in enumerate(hidden_vars):
        text = text.replace(f"__VAR_{i}__", var_val)

    return text


def substitute_links(
    text: str,
    pools: dict[str, list[str]],
    cache: dict[str, str] | None = None,
    mode: str = "urls",
) -> str:

    missing: set[str] = set()

    def _randomize_url(url: str) -> str:
        if not url:
            return url
            
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
        
        if "?" in url:
            randomized = f"{url}&{param_name}={param_val}"
        else:
            randomized = f"{url}?{param_name}={param_val}"
            
        return randomized + hash_part

    def _repl(m: re.Match) -> str:
        key = m.group(1)
        pool = pools.get(key)
        if not pool:
            missing.add(f"[[LINK{key}]]")
            return m.group(0)

        if mode == "spintax":
            return spin(_rnd.choice(pool))

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


def substitute(text: str, variables: dict[str, str]) -> str:
    for key, val in variables.items():
        text = text.replace("{{" + key + "}}", val)
    text = _MACRO_RE.sub("", text)
    return text.strip()


def is_html(text: str) -> bool:
    return bool(_HTML_RE.search(text))


_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)


def validate_template(template: str, is_subject: bool = False) -> list[str]:
    """Ловит дефекты спинтакса, которые уйдут ПОЛУЧАТЕЛЮ сырыми: непарные фигурные
    скобки и «|» вне спинтакс-блока. Возвращает список кратких проблем (пусто = чисто).

    Почему это нужно: движок spin() разворачивает только СБАЛАНСИРОВАННЫЕ {a|b}. Непарную
    скобку он закрыть не может — и она вместе с «|» утекает в письмо. Раньше это происходило
    молча (владелец видел {…|…} уже в превью/у получателя); теперь ловим ДО отправки.

    Что НЕ считаем скобками спинтакса: {{name}} и пр. переменные, [[LINK]] и CSS-блоки
    <style>{…}</style> (в этих письмах их нет, но подстраховываемся)."""
    t = _STYLE_BLOCK_RE.sub("", template)
    t = _MACRO_RE.sub("", t)   # {{переменные}}
    t = _LINK_RE.sub("", t)    # [[LINK]]
    depth = 0
    extra_close = 0
    top_pipe = 0
    for ch in t:
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                extra_close += 1
            else:
                depth -= 1
        elif ch == "|" and depth == 0:
            top_pipe += 1
    issues: list[str] = []
    if depth:
        issues.append(f"незакрытая {{ ×{depth}")
    if extra_close:
        issues.append(f"лишняя }} ×{extra_close}")
    if top_pipe:
        issues.append(f"«|» вне блока ×{top_pipe}")
    return issues


def find_content_issues(items: list[str], is_subject: bool = False) -> list[dict]:
    """Прогоняет validate_template по списку шаблонов. Возвращает [{n, why}] только для
    битых (n — номер с 1, why — краткая причина). Чистые не включаются."""
    out: list[dict] = []
    for i, tpl in enumerate(items):
        probs = validate_template(tpl, is_subject)
        if probs:
            out.append({"n": i + 1, "why": ", ".join(probs)})
    return out


# \s* перед закрывающим «>» — терпим «</p >», «</a >» (пробел в закрывающем теге —
# валидный HTML; движок его больше не создаёт, но шаблон автора может содержать).
_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_BLOCK_END_RE = re.compile(r'</(p|div|h[1-6]|li|tr)\s*>', re.IGNORECASE)
_A_TAG_RE = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a\s*>', re.IGNORECASE | re.DOTALL)
_ANY_TAG_RE = re.compile(r'<[^>]+>')
_MULTI_NL_RE = re.compile(r'\n{3,}')
_LEADING_SPACE_RE = re.compile(r'^[ \t]+', re.MULTILINE)


def html_to_plain_text(text: str) -> str:
    if not is_html(text):
        return text
    
    text = _BR_RE.sub('\n', text)
    
    text = _BLOCK_END_RE.sub('\n', text)
    
    def link_repl(match):
        url = match.group(1)
        link_text = match.group(2).strip()
        link_text = _ANY_TAG_RE.sub('', link_text)
        if link_text:
            return f"{link_text} {url}"
        return url
        
    text = _A_TAG_RE.sub(link_repl, text)
    
    text = _ANY_TAG_RE.sub('', text)
    
    text = html.unescape(text)
    
    text = _MULTI_NL_RE.sub('\n\n', text)
    
    text = _LEADING_SPACE_RE.sub('', text)
    
    return text.strip()


_RND_STRING_RE = re.compile(r"\[%%RndString\((\d+)\)%%\]")
_RND_NUMBER_RE = re.compile(r"\[%%RndNumber\((\d+),(\d+)\)%%\]")

def _substitute_ams_macros(text: str) -> str:
    def rnd_str_repl(m):
        length = int(m.group(1))
        return _generate_random_id(length)
    text = _RND_STRING_RE.sub(rnd_str_repl, text)

    def rnd_num_repl(m):
        lo, hi = int(m.group(1)), int(m.group(2))
        return str(random.SystemRandom().randint(lo, hi))
    text = _RND_NUMBER_RE.sub(rnd_num_repl, text)
    
    return text

# _replace_homoglyphs удалён (2026): см. комментарий выше про детект confusables.


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
    _rid = lambda n: ''.join(_rnd.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(n))
    _word = lambda: _rnd.choice([
        'header', 'footer', 'content', 'main', 'wrapper', 'layout',
        'body', 'container', 'section', 'module', 'block', 'row',
        'column', 'card', 'text', 'image', 'button', 'spacer',
        'divider', 'banner', 'nav', 'hero', 'cta', 'sidebar',
    ])
    templates = [
        f"<!-- v{_rnd.randint(1,9)}.{_rnd.randint(0,99)}.{_rnd.randint(0,999)} -->",
        f"<!-- build:{_rid(8)} -->",
        f"<!-- {_rid(6)}-{_rid(4)}-{_rid(4)} -->",
        f"<!-- rev:{_rid(6)} {_rnd.randint(2023,2026)}-{_rnd.randint(1,12):02d}-{_rnd.randint(1,28):02d} -->",
        f"<!-- section:{_word()} -->",
        f"<!-- /section:{_word()} -->",
        f"<!-- block:{_word()}_{_rnd.randint(1,99)} -->",
        f"<!-- /block -->",
        f"<!-- region:{_word()} -->",
        f"<!-- template:{_word()}_{_rid(4)} -->",
        f"<!-- mc:variant=\"{_word()}\" -->",
        f"<!-- sg:{_rid(8)} -->",
        f"<!-- campaign:{_rid(12)} -->",
        f"<!-- email-id:{_rid(8)}-{_rid(4)}-{_rid(4)}-{_rid(12)} -->",
        f"<!-- batch:{_rnd.randint(1000,9999)} -->",
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


# _randomize_html_entities удалён (2026): подмена букв на &#NN; — классический маркер
# обфускации, который фильтры распознают; в HTML-письме давал минус к репутации.


def _inject_css_noise(text: str) -> str:
    css_rate = _rnd.uniform(0.20, 0.50)
    def _add_noise(m: re.Match) -> str:
        style = m.group(0)
        if _rnd.random() < css_rate:
            prop = _rnd.choice(_CSS_NOISE_PROPS)
            if style.endswith('"'):
                inner = style[7:-1]
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


# ── Косметическая чистка пробелов после раскрытия спинтакса ────────────────────
# ПОЧЕМУ: пустая ветка «{…|}» рядом с пробелом/знаком препинания оставляет получателю
# видимый брак — «status .», «disappears ?», двойной пробел. Раньше движок это НЕ чистил
# (перекладывал на автора шаблона), и в реальных письмах владельца брак был виден. Теперь
# чистим на выходе — безопасно: только пробел ПЕРЕД знаком препинания и схлопывание
# двойных пробелов. В HTML трогаем ТОЛЬКО текст между тегами (атрибуты, URL, inline-CSS
# защищены), чтобы не сломать вёрстку/ссылку.
_PUNCT_SPACE_RE = re.compile(r"[ \t]+([.,!?:;])")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+(\n|$)")
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")


def _tidy_text_run(s: str) -> str:
    s = _PUNCT_SPACE_RE.sub(r"\1", s)
    s = _MULTISPACE_RE.sub(" ", s)
    return s


def _tidy_spaces(text: str, html_mode: bool) -> str:
    if not html_mode:
        text = _PUNCT_SPACE_RE.sub(r"\1", text)
        text = _MULTISPACE_RE.sub(" ", text)
        text = _TRAILING_WS_RE.sub(r"\1", text)
        return text
    # HTML: чистим только НЕ-теговые сегменты (чётные индексы после split по тегам).
    parts = _TAG_SPLIT_RE.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = _tidy_text_run(parts[i])
    return "".join(parts)


def render(
    template: str,
    variables: dict[str, str] | None = None,
    link_pools: dict[str, list[str]] | None = None,
    link_cache: dict[str, str] | None = None,
    is_subject: bool = False,
    link_mode: str = "urls",
) -> str:

    original_is_html = is_html(template)

    result = spin(template)

    if _LINK_RE.search(result):
        if not link_pools:
            raise ValueError(
                "Template contains [[LINK]] macros but no link pools loaded"
            )
        result = substitute_links(result, link_pools, cache=link_cache, mode=link_mode)

    if variables:
        result = substitute(result, variables)

    result = _substitute_ams_macros(result)

    # Косметическая чистка пробелов из пустых веток спинтакса (« ?», «  » и т. п.).
    # Делаем ДО HTML-уникализации: она пробел перед знаком препинания не создаёт,
    # а теги к этому моменту нормальные (уникализация добавит « >» уже после).
    result = _tidy_spaces(result, original_is_html)

    if is_subject:
        return result

    # 2026: \u043E\u043C\u043E\u0433\u043B\u0438\u0444\u044B, zero-width \u0441\u0438\u043C\u0432\u043E\u043B\u044B \u0438 entity-\u043F\u043E\u0434\u043C\u0435\u043D\u0430 \u0431\u0443\u043A\u0432 \u0423\u0411\u0420\u0410\u041D\u042B \u043D\u0430\u043C\u0435\u0440\u0435\u043D\u043D\u043E. \u0424\u0438\u043B\u044C\u0442\u0440\u044B
    # (Gmail/Yahoo/Microsoft) \u043D\u043E\u0440\u043C\u0430\u043B\u0438\u0437\u0443\u044E\u0442 \u043D\u0435\u0432\u0438\u0434\u0438\u043C\u044B\u0435 \u0441\u0438\u043C\u0432\u043E\u043B\u044B \u0438 confusables \u0414\u041E \u0430\u043D\u0430\u043B\u0438\u0437\u0430 \u0438
    # \u0444\u043B\u0430\u0433\u0443\u044E\u0442 \u0441\u0430\u043C\u043E \u0438\u0445 \u043D\u0430\u043B\u0438\u0447\u0438\u0435 \u043A\u0430\u043A \u0444\u0438\u0448\u0438\u043D\u0433 \u2014 \u043F\u043E\u043B\u044C\u0437\u044B \u043D\u043E\u043B\u044C, \u0440\u0438\u0441\u043A \u0435\u0441\u0442\u044C. \u0423\u043D\u0438\u043A\u0430\u043B\u044C\u043D\u043E\u0441\u0442\u044C \u043F\u0438\u0441\u044C\u043C\u0430
    # \u0434\u0430\u0451\u0442 \u0441\u043F\u0438\u043D\u0442\u0430\u043A\u0441; \u043D\u0438\u0436\u0435 \u2014 \u0442\u043E\u043B\u044C\u043A\u043E \u0431\u0435\u0437\u043E\u043F\u0430\u0441\u043D\u0430\u044F \u00AB\u043A\u043B\u0438\u0435\u043D\u0442\u043E\u043F\u043E\u0434\u043E\u0431\u043D\u0430\u044F\u00BB \u0432\u0430\u0440\u0438\u0430\u0442\u0438\u0432\u043D\u043E\u0441\u0442\u044C HTML
    # (\u0440\u0435\u0430\u043B\u044C\u043D\u044B\u0435 \u043F\u043E\u0447\u0442\u043E\u0432\u044B\u0435 \u043A\u043B\u0438\u0435\u043D\u0442\u044B \u0438 \u0441\u0430\u043C\u0438 \u043A\u043B\u0430\u0434\u0443\u0442 MSO/webkit-\u0441\u0442\u0438\u043B\u0438 \u0438 HTML-\u043A\u043E\u043C\u043C\u0435\u043D\u0442\u0430\u0440\u0438\u0438).
    if original_is_html:
        result = _inject_css_noise(result)

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

        def _randomize_whitespace(m):
            tag = m.group(0)
            # Пробел перед «>» добавляем ТОЛЬКО в открывающие теги С АТРИБУТАМИ.
            # ПОЧЕМУ не в закрывающие («</a>»→«</a >»): это валидный HTML, но ломает
            # ВСЕХ regex-потребителей, ищущих «</a>»/«</p>» — конвертацию в plain-text
            # (text/plain-часть письма теряла URL ссылки и переносы строк), локальный
            # скорер (ложное «НЕТ ссылки») и внешние анти-спам-тесты. Уникальности от
            # пробела в закрывающем теге ноль (там нет атрибутов) — риск без пользы.
            # DOCTYPE/комментарии (<!…>) и теги без атрибутов тоже пропускаем.
            if tag.startswith('</') or tag.startswith('<!'):
                return tag
            if _rnd.random() < 0.15 and not tag.endswith('/>') and ' ' in tag:
                tag = tag[:-1] + ' >'
            return tag
        result = re.sub(r'<[^>]+>', _randomize_whitespace, result)

    return result


_POOL_KEY_RE = re.compile(r"(\d+)$")


def pool_key_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    m = _POOL_KEY_RE.search(stem)
    return m.group(1) if m else ""


def subjects_preview_text(subjects: list[str], limit: int = 5) -> str:
    # ТЗ задачи 3: превью показывает первые N тем (по умолчанию 5), а не весь
    # список — иначе при большой базе тем окошко превью забивается целиком.
    # Если тем больше лимита, дописываем строку-счётчик остатка (сами темы сверх
    # лимита НЕ показываем).
    if not subjects:
        return "(пусто)"
    shown = subjects[:limit]
    text = "\n".join(shown)
    extra = len(subjects) - len(shown)
    if extra > 0:
        text += f"\n… ещё {extra}"
    return text


def format_email_preview(subject: str, body: str, is_html_flag: bool, sender_name: str = "") -> str:
    # Единый формат «как будет выглядеть письмо» для превью в GUI: отправитель,
    # тема, формат и развёрнутое тело. Чистая функция (без Tk) — чтобы и блок тел,
    # и песочница показывали одно и то же и это можно было проверить прогоном.
    fmt = "HTML" if is_html_flag else "Обычный текст"
    sender_line = f"Отправитель: {sender_name}" if sender_name else "Отправитель: (только email)"
    return "\n".join([
        sender_line,
        f"Тема:  {subject}",
        f"Формат:   {fmt}",
        "─" * 55,
        body,
    ])


class ContentManager:

    def __init__(self) -> None:
        self._subjects: list[str] = []
        self._bodies: list[str] = []
        self._link_pools: dict[str, list[str]] = {}
        self._link_files: list[tuple[str, str, int]] = []
        self._sender_names: list[str] = []
        self.consistent_links: bool = False
        self.email_only: bool = False
        self.link_mode: str = "urls"


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
        return render(template, variables, pools, link_cache, is_subject=True,
                      link_mode=self.link_mode)


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
        rendered = render(template, variables, pools, link_cache,
                          link_mode=self.link_mode)
        is_html_body = is_html(rendered)
        return (rendered, is_html_body)


    @property
    def link_pools(self) -> dict[str, list[str]]:
        return dict(self._link_pools)

    @property
    def link_files(self) -> list[tuple[str, str, int]]:
        return list(self._link_files)

    @property
    def link_pool_count(self) -> int:
        return len(self._link_pools)

    @staticmethod
    def _detect_link_mode(lines: list[str]) -> str:
        
        for line in lines:
            if '{' in line and '|' in line:
                return "spintax"
        return "urls"

    def load_links_file(self, filepath: str) -> tuple[str, int, str]:
        
        
        filename = Path(filepath).name
        urls = load_lines(filepath)
        
        detected_mode = self._detect_link_mode(urls)
        self.link_mode = detected_mode
        
        # Номер макроса берётся ИЗ ИМЕНИ ФАЙЛА, а не из порядка загрузки:
        # links.txt → [[LINK]], links1.txt → [[LINK1]], links2.txt → [[LINK2]].
        # Раньше ключ раздавался по очереди загрузки, из-за чего при загрузке вне
        # порядка или подмножеством файлов оферы уезжали не в те макросы.
        key = pool_key_from_filename(filename)
        
        if key in self._link_pools:
            self._link_pools[key].extend(urls)
        else:
            self._link_pools[key] = urls
            
        self._link_files.append((filename, key, len(urls)))
        self._link_files.sort(key=lambda x: int(x[1]) if x[1].isdigit() else 0)
        return key, len(urls), detected_mode

    def clear_links(self) -> None:
        self._link_pools.clear()
        self._link_files.clear()


    @property
    def sender_names(self) -> list[str]:
        return list(self._sender_names)

    @property
    def sender_name_count(self) -> int:
        return len(self._sender_names)

    def load_sender_names(self, filepath: str) -> int:
        lines = load_lines(filepath)
        self._sender_names.extend(lines)
        return len(lines)

    def clear_sender_names(self) -> None:
        self._sender_names.clear()

    def get_random_sender_name(self) -> str:
        if not self._sender_names or self.email_only:
            return ""
        return _rnd.choice(self._sender_names)

    def slice_lines(self, kind: str, offset: int, limit: int) -> list[str]:
        # Окно списка (темы/тела/имена) без копирования всего массива — срез списка
        # в Python это O(размера окна), а не O(всего). Нужно для постраничного показа
        # огромных объёмов (миллионы строк) без лагов интерфейса. Полные данные при
        # этом остаются в менеджере целиком — рассылка работает по всему объёму.
        src = {
            "subjects": self._subjects,
            "senders": self._sender_names,
            "bodies": self._bodies,
        }.get(kind)
        if src is None:
            return []
        if offset < 0:
            offset = 0
        return src[offset:offset + limit]

