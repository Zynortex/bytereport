"""
Small things that are visible at once: emoji, shadows, a "blue" button that
does not exist, and a demo that switched languages halfway.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "bytereport-frontend"
SRC = WEB / "src"

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def _code_without_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def _ui_files():
    for p in SRC.rglob("*"):
        if p.suffix in (".tsx", ".ts", ".json") and p.is_file():
            yield p


def test_no_emoji_in_the_interface():
    hits = []
    for p in _ui_files():
        text = p.read_text(encoding="utf-8")
        if p.suffix != ".json":
            text = _code_without_comments(text)
        for m in EMOJI.finditer(text):
            hits.append(f"{p.relative_to(SRC)}: U+{ord(m.group()):04X}")
    assert not hits, hits


def test_no_shadows():
    hits = []
    for p in SRC.rglob("*.tsx"):
        text = p.read_text(encoding="utf-8")
        if re.search(r"\bshadow-(sm|md|lg|xl|2xl|card|inner)\b|boxShadow|box-shadow|drop-shadow", text):
            hits.append(p.name)
    assert not hits, hits
    css = (SRC / "index.css").read_text(encoding="utf-8")
    assert not re.search(r"box-shadow\s*:", css)


def test_no_blue_button():
    for lang in ("ru", "uz", "en"):
        text = (SRC / "locales" / f"{lang}.json").read_text(encoding="utf-8").lower()
        for word in ("синюю", "синяя", "кўк тугма", "blue button"):
            assert word not in text, (lang, word)


def test_the_demo_page_has_no_hardcoded_russian():
    code = _code_without_comments((SRC / "pages" / "Demo.tsx").read_text(encoding="utf-8"))
    assert not re.search(r"[А-Яа-яЁё]", code)


def test_demo_labels_exist_in_every_language():
    keys = None
    for lang in ("ru", "uz", "en"):
        block = json.loads((SRC / "locales" / f"{lang}.json").read_text(encoding="utf-8"))["demo"]
        keys = keys or set(block)
        assert set(block) == keys, lang
    en = json.loads((SRC / "locales" / "en.json").read_text(encoding="utf-8"))["demo"]
    assert not any(re.search(r"[А-Яа-яЁё]", v) for v in en.values())


def _bundle_demo() -> dict:
    """Build src/data/demoReport.ts with esbuild and read both variants."""
    node = shutil.which("node")
    esbuild = WEB / "node_modules" / "esbuild"
    if not node or not esbuild.exists():
        pytest.skip("node/esbuild not available")
    script = r"""
const esbuild = require(process.argv[1]);
const out = esbuild.buildSync({ entryPoints: [process.argv[2]], bundle: true, format: "cjs",
  platform: "node", write: false, logLevel: "silent" });
const m = {}; new Function("module", "exports", "require", out.outputFiles[0].text)(m, m.exports = {}, require);
process.stdout.write(JSON.stringify(m.exports.DEMO_VARIANTS));
"""
    res = subprocess.run([node, "-e", script, str(esbuild), str(SRC / "data" / "demoReport.ts")],
                         capture_output=True, text=True, encoding="utf-8", cwd=WEB)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _numbers(obj, path=""):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _numbers(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _numbers(v, f"{path}[{i}]")


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def test_the_english_demo_has_the_same_numbers():
    v = _bundle_demo()
    for part in ("metrics", "report"):
        assert dict(_numbers(v["ru"][part])) == dict(_numbers(v["en"][part])), part


def test_the_english_demo_is_entirely_english():
    v = _bundle_demo()["en"]
    assert v["report"]["language"] == "en"
    russian = [s for s in _strings(v) if re.search(r"[А-Яа-яЁё]", s)]
    assert not russian, russian[:5]


def test_chart_axes_follow_the_interface_language():
    """The monthly chart's axis was fixed to ru-RU: "650 тыс." on an English report."""
    for rel in ("components/report/MonthlyChart.tsx", "components/report/CashForecastCard.tsx"):
        code = (SRC / rel).read_text(encoding="utf-8")
        assert "formatCompact(" in code and "i18n.language" in code, rel
        assert 'Intl.NumberFormat("ru-RU"' not in code, rel
    utils = (SRC / "lib" / "utils.ts").read_text(encoding="utf-8")
    assert '"uz-Cyrl-UZ"' in utils and '"en-US"' in utils
