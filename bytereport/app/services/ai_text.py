"""
Cleaning and labelling the text the model produces.

Two defences against the same failure: the model emitting something meant for a
machine into prose a person reads.

  * `sanitize` strips formula and placeholder notation. A report shipped with
    "...не менее 60 000 000 UZS $(RO)=$ минимальные переменные затраты..." —
    LaTeX-ish math the model wrote instead of substituting a value.
  * `humanize` turns a controlled-vocabulary token into a label. The same
    report printed "Статус: critical" and "Перспектива: negative", because the
    raw field went straight onto the page.

Both run at ONE boundary — right after the response is parsed — so the PDF and
the web page get the same cleaned object. Sanitising inside the PDF builder
would have left the web report showing the raw text.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Notation that must never reach a reader. Each pattern keeps the words inside
# where they are meaningful and drops the delimiters, because the surrounding
# sentence usually still reads correctly without them.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # \( ... \) and \[ ... \] — LaTeX inline/display math.
    ("latex-delim", re.compile(r"\\[\[(](.*?)\\[\])]", re.S)),
    # $...$ and $$...$$ — TeX math. Requires a non-space start so a plain price
    # like "$5 and $7" is left alone.
    ("tex-math", re.compile(r"\$\$?(?!\d)(\S.*?)\$\$?", re.S)),
    # {VAR} / {{VAR}} — an unsubstituted template placeholder.
    ("placeholder", re.compile(r"\{\{?\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}?\}")),
)

# After the delimiters go, these leftovers are noise rather than words.
_ORPHANS = re.compile(r"\s*(?:=|\\[a-zA-Z]+)\s*(?=\s|$)")

# Two words run together with no space, across scripts. The Uzbek prompt keeps
# borrowed terms in Latin inside Cyrillic prose, so a Cyrillic letter touching a
# Latin one is the signature of a lost boundary — a live report read
# "КечкиUtilities ва software".
#
# Only lower -> UPPER is split, and that restraint is the whole design. Uzbek
# routinely attaches Cyrillic case endings straight onto a Latin term
# ("PDFга", "Excelда"): those are Latin-upper or Latin-lower followed by
# Cyrillic LOWER, and splitting them would break correct text. A lowercase
# letter followed by a capital in the other script is a new word starting, not
# a suffix.
_GLUED = re.compile(r"([a-z])(?=[А-ЯЁЎҚҒҲ])|([а-яёўқғҳ])(?=[A-Z])")


def sanitize(text: str) -> tuple[str, list[str]]:
    """
    Strip formula/placeholder notation. Returns the text and what was found.

    The content between delimiters is kept: "$(RO)=$ минимальные затраты"
    becomes "(RO) минимальные затраты" rather than losing the sentence. A
    partial sentence beats a hole in the middle of one.
    """
    if not text:
        return text, []

    found: list[str] = []
    cleaned = text
    for name, pattern in _PATTERNS:
        if pattern.search(cleaned):
            found.append(name)
            # A space, not "", when the delimiters wrapped nothing. `\(\)` and
            # `{}` have an EMPTY inner group, so substituting the group removed
            # the delimiters and the gap with them, welding the neighbours into
            # one word. That is how this sanitizer could manufacture the very
            # defect it exists to remove. Doubled spaces are collapsed below.
            cleaned = pattern.sub(lambda m: m.group(1) or " ", cleaned)

    if found:
        cleaned = _ORPHANS.sub(" ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    return cleaned, found


# Phrases that assume the report's sections sit in a fixed order. They stop
# being true the moment an accountant hides a chart or drags it to the end,
# which the report now allows. Each pattern is anchored on a section noun or a
# "see"/"as shown" lead-in — "выше нормы" and "ниже 2%" are comparisons, not
# positions, and must survive.
_POSITIONAL: tuple[tuple[re.Pattern[str], str], ...] = (
    # ru: "на графике выше", "в разделе ниже", "в таблице выше"
    (re.compile(r"\b(на|в)\s+(графике|диаграмме|разделе|таблице|блоке)\s+(выше|ниже)\b", re.I), r"\1 \2"),
    # ru: "как видно выше/ниже", "как показано выше/ниже"
    (re.compile(r"\b(как\s+(?:видно|показано|отмечено))\s+(выше|ниже)\b", re.I), r"\1 в отчёте"),
    # ru: "см. выше", "(см. ниже)"
    (re.compile(r"\s*\(?\bсм\.\s*(выше|ниже)\)?", re.I), ""),
    # uz: "юқоридаги/қуйидаги/пастдаги график|жадвал|бўлим"
    (re.compile(r"\b(юқоридаги|қуйидаги|пастдаги)\s+(график|диаграмма|жадвал|бўлим)", re.I), r"\2"),
    # uz: "юқорида кўрсатилганидек" (as shown above)
    (re.compile(r"\b(юқорида|қуйида|пастда)\s+(кўрсатилганидек|айтилганидек|қайд этилганидек)", re.I), r"ҳисоботда \2"),
    # en: "the chart above", "in the section below"
    (re.compile(r"\b(chart|graph|diagram|table|section|block)\s+(above|below)\b", re.I), r"\1"),
    # en: "as shown above", "as seen below"
    (re.compile(r"\b(as\s+(?:shown|seen|noted|illustrated))\s+(above|below)\b", re.I), r"\1 in the report"),
    # en: "(see above)", "see below"
    (re.compile(r"\s*\(?\bsee\s+(above|below)\)?", re.I), ""),
)


_RE_SENTENCE_START = re.compile(r"(^|[.!?]\s+)(\w)")


def strip_positional(text: str) -> tuple[str, list[str]]:
    """
    Remove references to where a section sits relative to another.

    Returns the text and the phrases that were rewritten. The rewrite drops
    only the positional word: "на графике выше" -> "на графике", so the
    sentence still points at the chart, just not at where it is.
    """
    if not text:
        return text, []
    found: list[str] = []
    out = text
    for pattern, repl in _POSITIONAL:
        for m in pattern.finditer(out):
            found.append(m.group(0).strip())
        out = pattern.sub(repl, out)
    if found:
        out = re.sub(r"\s{2,}", " ", out).replace(" ,", ",").replace(" .", ".").strip()
        # Dropping a leading "Юқоридаги" leaves the sentence starting lowercase.
        out = _RE_SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), out)
    return out, found


def split_glued(text: str) -> tuple[str, list[str]]:
    """
    Restore the space between two words welded across scripts.

    Returns the repaired text and the joins that were split, so a caller can log
    them: a run-together is evidence about the generator, and silently patching
    it up would hide how often it happens.
    """
    if not text:
        return text, []
    joins = [
        text[max(0, m.start() - 8):m.start() + 9]
        for m in _GLUED.finditer(text)
    ]
    if not joins:
        return text, []
    return _GLUED.sub(lambda m: (m.group(1) or m.group(2)) + " ", text), joins


# ── Controlled vocabularies ─────────────────────────────────────────────────
#
# The model is asked for prose in `status` and `outlook`, and for one of a fixed
# set in `warning_level` and `confidence`. It does not always comply: a bare
# token in a prose field is exactly what produced "Статус: critical". So every
# one of these fields is passed through the same lookup, and anything that is
# not a known token is left alone as the prose it was meant to be.

_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "critical": "Критический дефицит", "deficit": "Дефицит",
        "negative": "Негативная", "positive": "Позитивная", "neutral": "Нейтральная",
        "stable": "Стабильная", "improving": "Улучшается", "declining": "Ухудшается",
        "healthy": "Устойчивый", "warning": "Тревожный", "surplus": "Профицит",
        "high": "Высокая", "medium": "Средняя", "low": "Низкая",
    },
    "uz": {
        "critical": "Танқисли ҳолат", "deficit": "Танқислик",
        "negative": "Салбий", "positive": "Ижобий", "neutral": "Нейтрал",
        "stable": "Барқарор", "improving": "Яхшиланмоқда", "declining": "Ёмонлашмоқда",
        "healthy": "Мустаҳкам", "warning": "Хавфли", "surplus": "Профицит",
        "high": "Юқори", "medium": "Ўрта", "low": "Паст",
    },
    "en": {
        "critical": "Critical deficit", "deficit": "Deficit",
        "negative": "Negative", "positive": "Positive", "neutral": "Neutral",
        "stable": "Stable", "improving": "Improving", "declining": "Declining",
        "healthy": "Healthy", "warning": "Warning", "surplus": "Surplus",
        "high": "High", "medium": "Medium", "low": "Low",
    },
}


# Russian agrees adjectives with the noun they follow, and these labels sit
# under two different ones: "Уверенность" (feminine) takes ВЫСОКАЯ, "Уровень
# риска" (masculine) takes ВЫСОКИЙ. One table cannot serve both, so the level
# context gets an override rather than the whole product settling for a
# grammatical mismatch on the page. Uzbek and English have no such agreement.
_LEVEL_OVERRIDES: dict[str, dict[str, str]] = {
    "ru": {"high": "Высокий", "medium": "Средний", "low": "Низкий"},
}


def humanize(value: str | None, language: str = "ru", kind: str | None = None) -> str:
    """
    A known token becomes a label; anything else is returned unchanged.

    Multi-word tokens are handled too ("critical deficit", "critical_deficit"),
    because the model reaches for those as readily as the bare word.
    """
    if not value:
        return ""
    table = dict(_LABELS.get(language, _LABELS["ru"]))
    if kind == "level":
        table.update(_LEVEL_OVERRIDES.get(language, {}))
    key = value.strip().lower().replace("_", " ").replace("-", " ")

    if key in table:
        return table[key]

    # "critical deficit" -> the more specific half wins, so the reader gets
    # "Критический дефицит" rather than "Критический" plus a stray word.
    words = key.split()
    if len(words) == 2 and all(w in table for w in words):
        return table["critical"] if "critical" in words and "deficit" in words else (
            f"{table[words[0]]} {table[words[1]].lower()}"
        )

    # Genuine prose. The model was asked for a sentence and gave one.
    return value.strip()


def looks_like_a_bare_token(value: str | None) -> bool:
    """True when a prose field came back as a single lowercase identifier."""
    if not value:
        return False
    v = value.strip()
    return bool(re.fullmatch(r"[a-z][a-z_\- ]{2,30}", v)) and len(v.split()) <= 3


# ── Applying it to a whole parsed report ────────────────────────────────────

M = TypeVar("M", bound=BaseModel)


def scrub_model(model: M, *, where: str = "AI response") -> M:
    """
    Recursively sanitize every string in a parsed model, in place.

    Every hit is logged with its field path: one leak means the prompt is being
    ignored somewhere, and the next one will be in a different field.
    """
    _scrub(model, where, [])
    return model


def _clean_one(value: str, where: str, field: str) -> tuple[str, list[str]]:
    """Both repairs for one string, each logged with the field it came from."""
    cleaned, found = sanitize(value)
    if found:
        logger.warning(
            "%s: stripped %s from %s (was: %r)", where, "+".join(found), field, value[:160]
        )
    cleaned, joins = split_glued(cleaned)
    if joins:
        logger.warning(
            "%s: split %d run-together word(s) in %s: %s",
            where, len(joins), field, "; ".join(repr(j) for j in joins[:3]),
        )
    cleaned, positional = strip_positional(cleaned)
    if positional:
        # Logged, because the prompt forbids these: a hit means the model is
        # ignoring it, and the report can now be rearranged so the reference
        # would have pointed at the wrong place or at nothing.
        logger.warning(
            "%s: removed %d positional reference(s) in %s: %s",
            where, len(positional), field, "; ".join(repr(x) for x in positional[:3]),
        )
    return cleaned, found


def _scrub(obj: Any, where: str, path: list[str]) -> None:
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            value = getattr(obj, name, None)
            if isinstance(value, str):
                cleaned, found = _clean_one(value, where, ".".join([*path, name]))
                if cleaned != value:
                    setattr(obj, name, cleaned)
            else:
                _scrub(value, where, [*path, name])
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                cleaned, _ = _clean_one(item, where, f"{'.'.join(path)}[{i}]")
                if cleaned != item:
                    obj[i] = cleaned
            else:
                _scrub(item, where, [*path, str(i)])
    elif isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                cleaned, _ = _clean_one(v, where, f"{'.'.join(path)}.{k}")
                if cleaned != v:
                    obj[k] = cleaned
            else:
                _scrub(v, where, [*path, str(k)])
