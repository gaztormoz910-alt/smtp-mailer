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
    t = _STYLE_BLOCK_RE.sub("", template)
    t = _MACRO_RE.sub("", t)
    t = _LINK_RE.sub("", t)
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
    out: list[dict] = []
    for i, tpl in enumerate(items):
        probs = validate_template(tpl, is_subject)
        if probs:
            out.append({"n": i + 1, "why": ", ".join(probs)})
    return out


_LINK_TOKEN = "\x01"
_VAR_TOKEN = "\x02"


def _split_top_alternatives(inner: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in inner:
        if ch == "{":
            depth += 1; cur.append(ch)
        elif ch == "}":
            depth -= 1; cur.append(ch)
        elif ch == "|" and depth == 0:
            parts.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _run_link_factor(run: str, link_factor: dict[str, int]) -> int:
    factor = 1
    i = 0
    while True:
        a = run.find(_LINK_TOKEN, i)
        if a < 0:
            break
        b = run.find(_LINK_TOKEN, a + 1)
        if b < 0:
            break
        key = run[a + 1:b]
        factor *= link_factor.get(key, 1)
        i = b + 1
    return factor


def _count_expansions(s: str, link_factor: dict[str, int]) -> int:
    total = 1
    n = len(s)
    i = 0
    run_start = 0
    while i < n:
        if s[i] == "{":
            total *= _run_link_factor(s[run_start:i], link_factor)
            depth = 1
            j = i + 1
            while j < n and depth:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                j += 1
            if depth:
                total *= _run_link_factor(s[i:], link_factor)
                return total
            inner = s[i + 1:j - 1]
            group = sum(_count_expansions(alt, link_factor)
                        for alt in _split_top_alternatives(inner))
            total *= group
            i = j
            run_start = j
        else:
            i += 1
    total *= _run_link_factor(s[run_start:], link_factor)
    return total


def count_combinations(
    template: str,
    link_pools: dict[str, list[str]] | None = None,
    link_mode: str = "urls",
    consistent_links: bool = False,
) -> int:
    if not template:
        return 1
    link_factor: dict[str, int] = {}
    if link_pools:
        for key, pool in link_pools.items():
            if not pool:
                link_factor[key] = 1
            elif link_mode == "spintax":
                link_factor[key] = sum(count_combinations(u) for u in pool) or 1
            else:
                link_factor[key] = len(pool)
    t = _MACRO_RE.sub(_VAR_TOKEN, template)
    marked = _LINK_RE.sub(lambda m: f"{_LINK_TOKEN}{m.group(1)}{_LINK_TOKEN}", t)

    if consistent_links and link_factor:
        spin_only = _count_expansions(marked, {})
        link_mult = 1
        for key in set(_LINK_RE.findall(template)):
            link_mult *= link_factor.get(key, 1)
        return spin_only * link_mult

    return _count_expansions(marked, link_factor)


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


_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s<)]+)\)')
_A_TAG_SPLIT_RE = re.compile(r'(<a\s[^>]+>.*?</a>)', re.IGNORECASE)
_RAW_URL_RE = re.compile(r'(https?://[^\s<]+)')


def plain_to_html(body: str) -> str:
    h = html.escape(body).replace("\n", "<br>\n")
    h = _MD_LINK_RE.sub(r'<a href="\2">\1</a>', h)
    parts = _A_TAG_SPLIT_RE.split(h)
    for i in range(0, len(parts), 2):
        parts[i] = _RAW_URL_RE.sub(r'<a href="\1">\1</a>', parts[i])
    return "".join(parts)


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
    parts = _TAG_SPLIT_RE.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = _tidy_text_run(parts[i])
    return "".join(parts)


_DOCTYPE_RE = re.compile(r"<!doctype", re.I)

_META_CHARSET_RE = re.compile(r"<meta[^>]+charset", re.I)
_VIEWPORT_RE = re.compile(r'<meta[^>]+name\s*=\s*["\']?viewport', re.I)
_HEAD_OPEN_RE = re.compile(r"<head[^>]*>", re.I)
_DOCTYPE_LINE_RE = re.compile(r"^﻿?\s*<!DOCTYPE[^>]*>[ \t]*\r?\n?", re.I)


def _ensure_meta_tags(html: str) -> str:
    metas = []
    if not _META_CHARSET_RE.search(html):
        metas.append('<meta charset="utf-8">')
    if not _VIEWPORT_RE.search(html):
        metas.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    if not metas:
        return html
    block = "".join(metas)
    m = _HEAD_OPEN_RE.search(html)
    if m:
        i = m.end()
        return html[:i] + block + html[i:]
    d = _DOCTYPE_LINE_RE.match(html)
    if d:
        i = d.end()
        return html[:i] + block + "\n" + html[i:]
    return block + "\n" + html


_FONT_STACKS = [
    "Arial, Helvetica, sans-serif",
    "'Helvetica Neue', Helvetica, Arial, sans-serif",
    "Georgia, 'Times New Roman', serif",
    "'Trebuchet MS', Verdana, sans-serif",
    "Verdana, Geneva, sans-serif",
    "Tahoma, 'Segoe UI', sans-serif",
    "'Segoe UI', Roboto, Arial, sans-serif",
    "Georgia, serif",
]
_FONT_FAMILY_RE = re.compile(r"font-family\s*:", re.I)
_FONT_SIZE_RE   = re.compile(r"font-size\s*:", re.I)
_LINE_H_RE      = re.compile(r"line-height\s*:", re.I)
_FIRST_STYLE_RE = re.compile(r'style="([^"]*)"', re.I)


def _diversify_typography(html: str) -> str:
    add = []
    if not _FONT_FAMILY_RE.search(html):
        add.append(f"font-family:{_rnd.choice(_FONT_STACKS)}")
    if not _FONT_SIZE_RE.search(html):
        add.append(f"font-size:{_rnd.choice([15, 16, 16, 17, 18])}px")
    if not _LINE_H_RE.search(html):
        add.append(f"line-height:{_rnd.choice(['1.4', '1.5', '1.55', '1.6'])}")
    if not add:
        return html
    props = ";".join(add)

    def _inject(m: re.Match) -> str:
        inner = m.group(1)
        if inner and not inner.rstrip().endswith(';'):
            inner += ';'
        return f'style="{inner}{props}"'

    return _FIRST_STYLE_RE.sub(_inject, html, count=1)


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

    result = _tidy_spaces(result, original_is_html)

    if is_subject:
        return result

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
            if tag.startswith('</') or tag.startswith('<!'):
                return tag
            if _rnd.random() < 0.15 and not tag.endswith('/>') and ' ' in tag:
                tag = tag[:-1] + ' >'
            return tag
        result = re.sub(r'<[^>]+>', _randomize_whitespace, result)

        result = _diversify_typography(result)

        if not _DOCTYPE_RE.search(result):
            result = "<!DOCTYPE html>\n" + result.lstrip("﻿ \t\r\n")

        result = _ensure_meta_tags(result)

    return result


_POOL_KEY_RE = re.compile(r"(\d+)$")


def pool_key_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    m = _POOL_KEY_RE.search(stem)
    return m.group(1) if m else ""


def subjects_preview_text(subjects: list[str], limit: int = 5) -> str:
    if not subjects:
        return "(пусто)"
    shown = subjects[:limit]
    text = "\n".join(shown)
    extra = len(subjects) - len(shown)
    if extra > 0:
        text += f"\n… ещё {extra}"
    return text


def format_email_preview(subject: str, body: str, is_html_flag: bool, sender_name: str = "") -> str:
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

