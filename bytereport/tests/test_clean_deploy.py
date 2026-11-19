"""
A fresh deploy installs requirements.txt and nothing else.

The bug this pins: `auth.py` imported python-jose, which was installed on the
development machine but absent from requirements.txt. On a clean server the
import failed inside token verification, the failure was reported as
"invalid token", and every signed-in user was refused with a 401 — a broken
environment dressed up as the user's mistake.
"""

import ast
import logging
import pathlib
import re
import sys
from importlib import metadata

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]
client = TestClient(app)


# ── Every import is installable ─────────────────────────────────────────────

def _requirement_names() -> set[str]:
    names = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[\[<>=!~ ;]", line, maxsplit=1)[0]
        names.add(_norm(name))
    return names


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _closure(roots: set[str]) -> set[str]:
    """Everything pip would install for `roots`, read from installed metadata."""
    seen: set[str] = set()
    todo = list(roots)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            reqs = metadata.requires(name) or []
        except metadata.PackageNotFoundError:
            continue
        for req in reqs:
            if "extra ==" in req:
                # Extras are only pulled in when asked for; requirements.txt
                # names the extras it wants explicitly (e.g. python-jose[cryptography]).
                continue
            todo.append(_norm(re.split(r"[\[<>=!~ ;(]", req, maxsplit=1)[0]))
    return seen


def _third_party_imports() -> dict[str, set[str]]:
    """Top-level module -> files, including imports inside functions."""
    found: dict[str, set[str]] = {}
    files = [ROOT / "main.py", *(ROOT / "app").rglob("*.py")]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for mod in mods:
                top = mod.split(".")[0]
                if top in ("app", "main") or top in sys.stdlib_module_names:
                    continue
                found.setdefault(top, set()).add(path.name)
    return found


def test_jose_is_a_declared_dependency():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^python-jose\[cryptography\]==", text, re.M), (
        "auth.py verifies every token with python-jose; without it a clean "
        "deploy refuses every signed-in user"
    )


def test_every_import_is_covered_by_requirements():
    """
    Lazy imports inside functions are the ones `import main` never reaches —
    jose was one — so the source is scanned rather than the app imported.
    """
    installable = _closure(_requirement_names())
    by_module = metadata.packages_distributions()
    missing = []
    for module, where in sorted(_third_party_imports().items()):
        dists = {_norm(d) for d in by_module.get(module, [])}
        if not dists:
            missing.append(f"{module} (not installed here at all) <- {sorted(where)}")
        elif not dists & installable:
            missing.append(f"{module} from {sorted(dists)} <- {sorted(where)}")
    assert not missing, "imported but not installed by requirements.txt:\n" + "\n".join(missing)


# ── A broken environment is a server fault, not a bad token ─────────────────

def _bearer() -> dict:
    return {"Authorization": "Bearer aaa.bbb.ccc"}


def test_a_missing_jose_is_a_500_with_a_traceback(monkeypatch, caplog):
    # `None` in sys.modules makes `import jose` raise ImportError, which is
    # exactly what a deploy without the package does.
    monkeypatch.setitem(sys.modules, "jose", None)
    monkeypatch.setitem(sys.modules, "jose.jwt", None)
    monkeypatch.setitem(sys.modules, "jose.exceptions", None)
    with caplog.at_level(logging.ERROR, logger="app.core.auth"):
        resp = client.post("/voice/parse", json={"text": "x"}, headers=_bearer())
    assert resp.status_code == 500, resp.text
    assert "токен" not in resp.json()["detail"].lower(), "must not blame the token"
    crash = [r for r in caplog.records if r.name == "app.core.auth" and r.levelno >= logging.ERROR]
    assert crash and crash[0].exc_info, "the traceback must reach the log"
    assert issubclass(crash[0].exc_info[0], ImportError)


def test_any_non_jose_failure_is_a_500(monkeypatch):
    import app.core.auth as auth_mod

    def boom(_token):
        raise AttributeError("a bug, not a bad token")

    monkeypatch.setattr(auth_mod, "_decode", boom)
    resp = client.post("/voice/parse", json={"text": "x"}, headers=_bearer())
    assert resp.status_code == 500


def test_a_genuinely_bad_token_is_still_a_401(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "test-only-secret")
    resp = client.post("/voice/parse", json={"text": "x"}, headers=_bearer())
    assert resp.status_code == 401


@pytest.mark.parametrize("exc_name", ["ExpiredSignatureError", "JWTClaimsError", "JWTError", "JWKError"])
def test_every_jose_rejection_is_a_401(monkeypatch, exc_name):
    import jose.exceptions as jx

    import app.core.auth as auth_mod

    def reject(_token):
        raise getattr(jx, exc_name)("rejected")

    monkeypatch.setattr(auth_mod, "_decode", reject)
    resp = client.post("/voice/parse", json={"text": "x"}, headers=_bearer())
    assert resp.status_code == 401


# ── Secrets stay out of git; every setting is named ─────────────────────────

def test_env_example_names_every_setting():
    from app.core.config import Settings

    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    named = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, re.M))
    missing = {f.upper() for f in Settings.model_fields} - named
    assert not missing, f".env.example does not mention: {sorted(missing)}"


def test_env_example_carries_no_values():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    filled = [ln for ln in text.splitlines() if re.match(r"^#?\s*[A-Z][A-Z0-9_]+=\S", ln)]
    assert not filled, filled


def test_env_files_are_not_tracked():
    import shutil
    import subprocess

    if not shutil.which("git"):
        pytest.skip("git not available")
    out = subprocess.run(["git", "ls-files"], cwd=ROOT.parent, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    tracked = [p for p in out.stdout.splitlines()
               if re.search(r"(^|/)\.env$", p) or "__pycache__" in p]
    assert not tracked, tracked
