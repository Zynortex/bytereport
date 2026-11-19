"""
Look for keys, tokens and private data before code goes public.

    python tools/secret_scan.py                 # files git tracks in this repo
    python tools/secret_scan.py <directory>     # every file under a directory

Exit code 1 when anything at "secret" level is found, so a script can stop on
it. Values are never printed in full: a finding shows the first characters
and the length, enough to recognise which key it is and no more.

Levels:
  secret  a credential: an API key, a JWT, a private key, a filled-in .env line
  review  not a credential, but identifies a person or a project (an email
          address, a Supabase project URL): decide before publishing
  note    the word appears (e.g. "service_role" in a comment that explains why
          the service key never reaches the browser): listed, harmless
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

SKIP_DIRS = {".git", "node_modules", "dist", "venv", ".venv", "__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".ttf", ".woff",
                 ".woff2", ".zip", ".xlsx", ".xls", ".pyc", ".lock"}

RULES: list[tuple[str, str, re.Pattern]] = [
    ("secret", "OpenAI key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("secret", "Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("secret", "JWT (Supabase anon/service key or a token)",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("secret", "Supabase secret key", re.compile(r"\bsb_secret_[A-Za-z0-9_\-]{10,}")),
    ("secret", "private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secret", "AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("secret", "GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("secret", "filled-in secret variable",
     # [ \t]*, not \s*: an empty `KEY=` must not swallow the next line as its value.
     re.compile(r"^[ \t]*(?:export[ \t]+)?(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|SUPABASE_SERVICE_KEY|"
                r"SUPABASE_ANON_KEY|SUPABASE_JWT_SECRET|VITE_SUPABASE_ANON_KEY)[ \t]*=[ \t]*['\"]?"
                r"(?!your|<|\$\{|qa-|test)[A-Za-z0-9_\-.]{12,}", re.M)),
    ("review", "Supabase project URL", re.compile(r"\bhttps://[a-z0-9]{20}\.supabase\.co\b")),
    ("review", "email address", re.compile(r"\b[\w.+\-]+@[\w\-]+\.[A-Za-z]{2,}\b")),
    ("note", "word service_role / SUPABASE_SERVICE_KEY", re.compile(r"service_role|SUPABASE_SERVICE_KEY")),
]

# Addresses that are placeholders or public by design.
SAFE_EMAILS = re.compile(r"@(example\.(com|org)|biznes\.uz|test\.local|anthropic\.com)$|^noreply@", re.I)


def tracked_files(root: pathlib.Path) -> list[pathlib.Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [root / p for p in out.stdout.decode("utf-8").split("\0") if p]


def all_files(root: pathlib.Path) -> list[pathlib.Path]:
    return [p for p in root.rglob("*")
            if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS)]


def redact(value: str) -> str:
    return f"{value[:6]}... ({len(value)} chars)"


def scan(root: pathlib.Path, files: list[pathlib.Path]) -> list[tuple[str, str, str, str]]:
    findings = []
    for path in files:
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        for level, name, rx in RULES:
            for m in rx.finditer(text):
                value = m.group(0)
                if name == "email address" and SAFE_EMAILS.search(value):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                shown = value if level == "note" else redact(value)
                findings.append((level, f"{rel}:{line}", name, shown))
    return findings


def main() -> int:
    target = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if target:
        root, files = target, all_files(target)
    else:
        root = pathlib.Path(__file__).resolve().parents[1]
        files = tracked_files(root)

    findings = scan(root, files)
    print(f"Scanned {len(files)} files under {root}")
    for level in ("secret", "review", "note"):
        rows = [f for f in findings if f[0] == level]
        print(f"\n{level.upper()}: {len(rows)}")
        for _, where, name, shown in rows[:200]:
            print(f"  {where:60s} {name:45s} {shown}")
    return 1 if any(f[0] == "secret" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
