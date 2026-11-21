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


# ── tools/sync_public_repo.py ───────────────────────────────────────────────

def _load_sync():
    import importlib.util

    tools = ROOT / "tools"
    sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location("sync_public_repo", tools / "sync_public_repo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _repo(path, files: dict):
    path.mkdir(parents=True, exist_ok=True)
    git = lambda *a: subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)  # noqa: E731
    git("init", "-q", "-b", "main")
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(text, encoding="utf-8")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")
    return git


def test_sync_mirrors_head_excludes_private_paths_and_commits_as_the_noreply_author(tmp_path):
    sync = _load_sync()
    _repo(tmp_path / "private", {
        "README.md": "new readme\n", "app/main.py": "print('v2')\n",
        "app/new.py": "x = 1\n", ".claude/settings.local.json": "{}\n",
    })
    pub_git = _repo(tmp_path / "public", {
        "README.md": "old readme\n", "app/main.py": "print('v1')\n", "app/gone.py": "old\n",
    })
    s = sync.sync(tmp_path / "private", tmp_path / "public", sync.DEFAULT_AUTHOR, message="Sync")
    assert s["added"] == ["app/new.py"]
    assert sorted(s["changed"]) == ["README.md", "app/main.py"]
    assert s["removed"] == ["app/gone.py"]
    assert not (tmp_path / "public" / ".claude").exists()
    log = pub_git("log", "-1", "--format=%an <%ae>|%cn <%ce>|%s").stdout.decode()
    assert log.strip() == ("Azizbek <264824882+Zynortex@users.noreply.github.com>|"
                           "Azizbek <264824882+Zynortex@users.noreply.github.com>|Sync")
    assert pub_git("rev-list", "--count", "HEAD").stdout.decode().strip() == "2"


def test_sync_stops_on_a_secret_and_touches_nothing(tmp_path):
    sync = _load_sync()
    key = "sk-proj-" + "Zz9" * 12
    _repo(tmp_path / "private", {"config.py": f'KEY = "{key}"\n'})
    pub_git = _repo(tmp_path / "public", {"config.py": "KEY = ''\n"})
    import pytest as _pytest

    with _pytest.raises(sync.SyncError) as exc:
        sync.sync(tmp_path / "private", tmp_path / "public", sync.DEFAULT_AUTHOR)
    assert key not in str(exc.value)
    assert (tmp_path / "public" / "config.py").read_text(encoding="utf-8") == "KEY = ''\n"
    assert pub_git("rev-list", "--count", "HEAD").stdout.decode().strip() == "1"


def test_sync_will_not_overwrite_uncommitted_public_edits(tmp_path):
    sync = _load_sync()
    _repo(tmp_path / "private", {"a.txt": "private\n"})
    _repo(tmp_path / "public", {"a.txt": "public\n"})
    (tmp_path / "public" / "a.txt").write_text("edited by hand\n", encoding="utf-8")
    import pytest as _pytest

    with _pytest.raises(sync.SyncError):
        sync.sync(tmp_path / "private", tmp_path / "public", sync.DEFAULT_AUTHOR)
    assert (tmp_path / "public" / "a.txt").read_text(encoding="utf-8") == "edited by hand\n"


def test_sync_dry_run_writes_nothing(tmp_path):
    sync = _load_sync()
    _repo(tmp_path / "private", {"a.txt": "new\n"})
    _repo(tmp_path / "public", {"a.txt": "old\n"})
    s = sync.sync(tmp_path / "private", tmp_path / "public", sync.DEFAULT_AUTHOR, dry_run=True)
    assert s["changed"] == ["a.txt"] and s["commit"] is None
    assert (tmp_path / "public" / "a.txt").read_text(encoding="utf-8") == "old\n"


def test_sync_shares_the_exclusions_and_never_pushes():
    src = _read("tools/sync_public_repo.py")
    assert "from make_public_repo import EXCLUDE" in src
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith(("print(", "#")))
    assert '"push"' not in code and "'push'" not in code


def test_render_region_matches_the_public_repository():
    assert "region: singapore" in _read("render.yaml")
