"""
The web app on free hosting: a demo that never waits for the backend, a wake
screen instead of a frozen button, and the copy fixes that went with it.
"""

import functools
import json
import pathlib
import re

from tests.test_a5_polish import _bundle_demo, _numbers, _strings

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "bytereport-frontend"
SRC = WEB / "src"
LANGS = ("ru", "uz", "en")


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _locale(lang: str) -> dict:
    return json.loads((SRC / "locales" / f"{lang}.json").read_text(encoding="utf-8"))


def _code(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


# ── /demo needs nothing from the backend ────────────────────────────────────

def test_the_demo_makes_no_request_when_it_opens():
    demo = _code(_read("pages/Demo.tsx"))
    # The one backend call on the page is the PDF download, behind a click.
    assert demo.count("api.") == 1 and "api.downloadPDF" in demo
    assert "warmUp()" not in demo
    # The server is woken only when the visitor reaches for the real product.
    assert demo.count("{...warmOnIntent}") == 3


def test_the_landing_and_sign_in_pages_wake_the_server():
    assert "warmUp" in _code(_read("pages/Landing.tsx"))
    assert "warmUp()" in _code(_read("pages/Auth.tsx"))


def test_a_direct_link_to_the_demo_works_on_vercel():
    cfg = json.loads((WEB / "vercel.json").read_text(encoding="utf-8"))
    rewrites = cfg["rewrites"]
    assert rewrites[0] == {"source": "/demo", "destination": "/demo.html"}
    assert rewrites[-1] == {"source": "/(.*)", "destination": "/index.html"}
    # The build writes that file (vite.config.ts, socialMeta).
    assert 'path.join(dist, "demo.html")' in (WEB / "vite.config.ts").read_text(encoding="utf-8")


# ── Wake screen ─────────────────────────────────────────────────────────────

def test_every_api_request_waits_for_a_sleeping_server_first():
    client = _code(_read("api/client.ts"))
    request = client[client.index("interceptors.request.use"):]
    assert request.index("ensureServerAwake") < request.index("getSession")
    assert "markAwake()" in client and "markUnknown()" in client


def test_the_wake_screen_timings_match_the_brief():
    wake = _read("api/serverWake.ts")
    assert "SHOW_AFTER_MS = 3_000" in wake
    assert "GIVE_UP_AFTER_MS = 90_000" in wake


def test_the_wake_screen_is_mounted_once_for_the_whole_app():
    app = _read("App.tsx")
    assert app.count("<ServerWakeOverlay />") == 1


def test_the_wake_screen_speaks_three_languages():
    keys = None
    for lang in LANGS:
        block = _locale(lang)["server_wake"]
        assert all(v.strip() for v in block.values()), lang
        keys = keys or set(block)
        assert set(block) == keys, lang
    assert {"title", "text", "failed_title", "retry", "close", "gave_up"} <= keys
    assert _locale("ru")["server_wake"]["title"] == "Сервер запускается, это займёт до минуты"
    assert _locale("ru")["server_wake"]["retry"] == "Повторить"


def test_the_base_url_comes_from_vite_api_url():
    assert "import.meta.env.VITE_API_URL" in _read("api/baseUrl.ts")
    for rel in ("api/client.ts", "api/serverWake.ts"):
        assert "localhost:8000" not in _read(rel), rel


# ── Copy ────────────────────────────────────────────────────────────────────

def test_the_free_reports_line_counts_from_pricing():
    for lang in LANGS:
        loc = _locale(lang)
        for sec, key in (("auth", "free_reports"), ("landing", "cta_sub")):
            forms = {k: v for k, v in loc[sec].items() if k.startswith(key + "_")}
            assert forms and all("{{count}}" in v for v in forms.values()), (lang, sec)
        assert "first_free" not in loc["auth"] and "first_free" not in loc["dashboard"]
    ru = _locale("ru")
    assert ru["landing"]["cta_sub_few"].startswith("{{count}} анализа бесплатно")
    for rel, key in (("pages/Auth.tsx", "auth.free_reports"), ("pages/Landing.tsx", "landing.cta_sub")):
        assert f'"{key}", {{ count: FREE_REPORTS_ON_SIGNUP }}' in _read(rel), rel


def test_no_page_promises_thirty_seconds():
    for lang in LANGS:
        loc = _locale(lang)
        for sec, key in (("landing", "hero_sub"), ("landing", "checks_title"),
                         ("auth", "tagline"), ("welcome", "p2")):
            assert not re.search(r"\b30\b", loc[sec][key]), (lang, sec, key)
    assert "примерно за минуту" in _locale("ru")["landing"]["hero_sub"]


def test_report_headings_are_translated():
    for lang in ("ru", "uz"):
        rep = _locale(lang)["report"]
        for key in ("executive_summary", "cash_flow"):
            assert not re.search(r"[A-Za-z]", rep[key]), (lang, key, rep[key])
    assert _locale("uz")["report"]["cash_flow"] == "Пул оқими"


# ── Uzbek demo ──────────────────────────────────────────────────────────────

def test_the_uzbek_demo_has_the_same_numbers():
    v = _bundle_demo()
    for part in ("metrics", "report"):
        assert dict(_numbers(v["ru"][part])) == dict(_numbers(v["uz"][part])), part


def test_the_uzbek_demo_is_uzbek():
    v = _bundle_demo()["uz"]
    assert v["report"]["language"] == "uz"
    texts = list(_strings(v))
    codes = ("RUB", "uz", "medium", "high", "low", "spike", "drop", "MEDIUM")
    # "I чорак" — a Roman numeral for the quarter, written the same in Uzbek.
    latin = [s for s in texts
             if s not in codes and re.search(r"[A-Za-z]", re.sub(r"\b[IV]{1,3}\b", "", s))]
    assert not latin, latin[:5]
    # Uzbek Cyrillic has no ы; Russian left untranslated would.
    assert not [s for s in texts if "ы" in s.lower()]
    assert re.search(r"[ўғқҳ]", v["report"]["executive_summary"])


def test_the_demo_follows_the_interface_language():
    demo = _read("data/demoReport.ts")
    assert 'if (lang === "uz") return UZ;' in demo
    assert "DEMO_VARIANTS = { ru: RU, uz: UZ, en: EN }" in demo


def test_no_standing_cold_start_banner_on_the_upload_page():
    """The wake screen handles a sleeping server; a permanent "may take up to
    60 seconds, server is waking up" banner warned about it on every visit."""
    assert "cold_start" not in _read("pages/Upload.tsx")
    for lang in LANGS:
        assert not [k for k in _locale(lang)["upload"] if k.startswith("cold_start")], lang


# ── When the wake screen may appear ─────────────────────────────────────────
# serverWake.ts is bundled with esbuild and run in Node with a fake fetch, on
# real timers: each scenario gets its own copy of the module and its own fetch.

WAKE_HARNESS = r"""
const esbuild = require(process.argv[1]);
const build = (dev) => esbuild.buildSync({
  entryPoints: [process.argv[2]], bundle: true, format: "cjs", platform: "node", write: false,
  logLevel: "silent",
  define: { "import.meta.env.DEV": String(dev), "import.meta.env.VITE_API_URL": '"http://api.test"' },
}).outputFiles[0].text;
const PROD = build(false), DEV = build(true);

function load(code, fetchImpl) {
  const m = { exports: {} };
  new Function("module", "exports", "require", "fetch", code)(m, m.exports, require, fetchImpl);
  return m.exports;
}
const ok = () => ({ ok: true, status: 200, json: async () => ({ status: "ok" }) });
const abortable = (init, settle) => new Promise((resolve, reject) => {
  init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  settle(resolve, reject);
});

async function scenario(code, fetchImpl, { markAwakeFirst = false, watchMs = 0 } = {}) {
  const calls = [];
  const wrapped = (url, init = {}) => { calls.push(init.mode || "cors"); return fetchImpl(url, init); };
  const mod = load(code, wrapped);
  const phases = new Set([mod.useServerWake.getState().phase]);
  mod.useServerWake.subscribe((s) => phases.add(s.phase));
  if (markAwakeFirst) mod.markAwake();
  const t0 = Date.now();
  let resolvedAt = null;
  mod.ensureServerAwake(() => "gave up").then(() => { resolvedAt = Date.now() - t0; }, () => {});
  await new Promise((r) => setTimeout(r, watchMs || 200));
  return { phases: [...phases], resolvedAt, calls };
}

(async () => {
  const out = {};
  const started = Date.now();
  const runs = {
    // A live server answers /health at once: no screen.
    alive: scenario(PROD, (u, init) => abortable(init, (res) => setTimeout(() => res(ok()), 50)), { watchMs: 3600 }),
    // /health is blocked by CORS but the server answers it: alive, no screen.
    cors_blocked: scenario(PROD, (u, init) => abortable(init, (res, rej) =>
      init.mode === "no-cors" ? setTimeout(() => res({ ok: false, status: 0, type: "opaque" }), 30)
                              : setTimeout(() => rej(new TypeError("Failed to fetch")), 30)), { watchMs: 3600 }),
    // Known awake (a request answered recently): nothing is probed, however
    // long the next request then takes.
    known_awake: scenario(PROD, () => { throw new Error("probed"); }, { markAwakeFirst: true, watchMs: 300 }),
    // Asleep: the host holds /health for 3.6 s, then answers. Screen, then gone.
    asleep: scenario(PROD, (u, init) => abortable(init, (res) => setTimeout(() => res(ok()), 3600 - (Date.now() - started))), { watchMs: 4200 }),
    // Nothing listens at all: the screen after 3 s.
    refused: scenario(PROD, (u, init) => abortable(init, (res, rej) => setTimeout(() => rej(new TypeError("Failed to fetch")), 10)), { watchMs: 3400 }),
    // npm run dev: never probed, never shown, even with nothing listening.
    dev: scenario(DEV, (u, init) => abortable(init, (res, rej) => rej(new TypeError("Failed to fetch"))), { watchMs: 3400 }),
  };
  for (const [k, p] of Object.entries(runs)) out[k] = await p;
  const devMod = load(DEV, () => { throw new Error("warm-up fetched in dev"); });
  devMod.warmUp();
  out.dev_warmup = "no fetch";
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
"""


@functools.lru_cache(maxsize=1)
def _wake_scenarios() -> dict:
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    esbuild = WEB / "node_modules" / "esbuild"
    if not node or not esbuild.exists():
        pytest.skip("node/esbuild not available")
    res = subprocess.run([node, "-e", WAKE_HARNESS, str(esbuild), str(SRC / "api" / "serverWake.ts")],
                         capture_output=True, text=True, encoding="utf-8", cwd=WEB, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_the_wake_screen_depends_on_health_alone():
    s = _wake_scenarios()
    # A live server: answered, no screen.
    assert s["alive"]["phases"] == ["idle"] and s["alive"]["resolvedAt"] is not None
    # Alive behind a CORS mistake: no "server is starting" screen.
    assert s["cors_blocked"]["phases"] == ["idle"] and s["cors_blocked"]["calls"][:2] == ["cors", "no-cors"]
    # Known awake: no probe at all, so a slow request can never raise the screen.
    assert s["known_awake"]["calls"] == [] and s["known_awake"]["resolvedAt"] is not None
    # Asleep: shown while /health is silent, gone once it answers.
    assert "waking" in s["asleep"]["phases"] and s["asleep"]["resolvedAt"] >= 3000
    # Nothing answers: shown after 3 s, request still held.
    assert "waking" in s["refused"]["phases"] and s["refused"]["resolvedAt"] is None


def test_no_wake_screen_and_no_warm_up_under_npm_run_dev():
    s = _wake_scenarios()
    assert s["dev"]["phases"] == ["idle"] and s["dev"]["calls"] == []
    assert s["dev"]["resolvedAt"] is not None
    assert s["dev_warmup"] == "no fetch"


def test_the_upload_hint_states_the_pdf_page_limit():
    import sys

    sys.path.insert(0, str(ROOT / "bytereport"))
    from app.services.pdf_statement import MAX_PAGES

    for lang in LANGS:
        assert str(MAX_PAGES) in _locale(lang)["upload"]["file_support"], lang
