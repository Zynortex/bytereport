"""
What goes public, and how: the Render blueprint, the secret scanner, the
script that builds a fresh repository, and the README it ships with.
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── render.yaml ─────────────────────────────────────────────────────────────

def test_render_starts_the_api_the_way_the_brief_says():
    y = _read("render.yaml")
    assert "startCommand: cd bytereport && uvicorn main:app --host 0.0.0.0 --port $PORT" in y
    assert "healthCheckPath: /health" in y
    assert "plan: free" in y
    assert re.search(r"key: PYTHON_VERSION\s+value: 3\.11\.\d+", y)


def test_render_never_carries_a_secret_value():
    y = _read("render.yaml")
    for key in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
                "ALLOWED_ORIGINS", "UNLIMITED_REPORT_EMAILS"):
        assert re.search(rf"key: {key}\s+sync: false", y), key
    assert "AI_MOCK" not in y, "production must call the real model"


def test_the_old_hosts_configs_are_gone():
    for name in ("Procfile", "koyeb.yaml", "railway.json", "nixpacks.toml", "runtime.txt"):
        assert not (ROOT / "bytereport" / name).exists(), name


# ── Secret scanner ──────────────────────────────────────────────────────────

def _scan(path: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "tools" / "secret_scan.py"), str(path)],
                          capture_output=True, text=True, encoding="utf-8")


def test_the_scanner_stops_on_a_key_without_printing_it(tmp_path):
    key = "sk-proj-" + "A1b2C3d4" * 6
    (tmp_path / "config.py").write_text(f'OPENAI = "{key}"\n', encoding="utf-8")
    (tmp_path / ".env").write_text("SUPABASE_SERVICE_KEY=abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    out = _scan(tmp_path)
    assert out.returncode == 1
    assert "OpenAI key" in out.stdout and "filled-in secret variable" in out.stdout
    assert key not in out.stdout and "abcdefghijklmnop" not in out.stdout


def test_the_scanner_passes_a_clean_tree(tmp_path):
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\nSUPABASE_SERVICE_KEY=\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    assert _scan(tmp_path).returncode == 0


def test_local_tool_settings_are_neither_tracked_nor_published():
    assert ".claude/settings.local.json" in _read(".gitignore")
    tracked = subprocess.run(["git", "ls-files", ".claude"], cwd=ROOT, capture_output=True, text=True).stdout
    assert "settings.local.json" not in tracked
    assert '".claude/"' in _read("tools/make_public_repo.py")


def test_the_public_repo_script_never_pushes():
    src = _read("tools/make_public_repo.py")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith(("print(", "#")))
    assert '"push"' not in code and "'push'" not in code
    assert "noreply" in src, "a public commit must not expose a private email by default"


# ── README ──────────────────────────────────────────────────────────────────

def test_every_readme_screenshot_exists():
    readme = _read("README.md")
    shots = re.findall(r"docs/screenshots/[\w.-]+\.png", readme)
    assert len(set(shots)) >= 3
    for rel in shots:
        assert (ROOT / rel).is_file(), rel


def test_the_readme_test_count_is_current():
    """The README states a number of tests; it must be the real one."""
    stated = int(re.search(r"\*\*(\d+) automated tests\*\*", _read("README.md")).group(1))
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT / "bytereport", capture_output=True, text=True, encoding="utf-8")
    collected = int(re.search(r"(\d+) tests? collected", out.stdout).group(1))
    assert stated == collected, f"README says {stated}, pytest collects {collected}"
