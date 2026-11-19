"""
Make a NEW git repository for publishing: today's code, one commit, no history.

This repository's history holds old .env files with live keys, so it must stay
private, and its history is not rewritten. Instead this script copies what the
last commit (HEAD) contains into a fresh folder and starts a new repository
there.

    python tools/make_public_repo.py ../bytereport-public --email 12345+you@users.noreply.github.com

What it does:
  1. Refuses if tracked files have uncommitted changes (it publishes HEAD).
  2. Exports HEAD with `git archive`: only files git tracks, so .env, venv,
     node_modules, dist, logs and uploads (all git-ignored) never get in.
  3. Leaves out the paths in EXCLUDE (local tool settings).
  4. Runs tools/secret_scan.py on the result and stops on any finding.
  5. `git init`, one commit. It does not push: that is yours to do.

The author email of a public commit is public. Use GitHub's noreply address
(GitHub → Settings → Emails → "Keep my email addresses private" shows it).
"""

from __future__ import annotations

import argparse
import io
import pathlib
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Tracked today or in the past, never for a public repository.
EXCLUDE = (
    ".claude/",            # local Claude Code settings: permission rules quoted keys
    ".playwright-mcp/",
)


def git(*args: str, cwd: pathlib.Path = ROOT, binary: bool = False):
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="new folder for the public repository (must not exist or be empty)")
    ap.add_argument("--email", help="author email for the commit (GitHub noreply recommended)")
    ap.add_argument("--name", help="author name (default: your git user.name)")
    ap.add_argument("--message", default="ByteReport: initial public version")
    args = ap.parse_args()

    target = pathlib.Path(args.target).resolve()
    if target.exists() and any(target.iterdir()):
        print(f"Stop: {target} exists and is not empty.")
        return 2
    if ROOT in target.parents or target == ROOT:
        print("Stop: the target must be outside this repository.")
        return 2

    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty:
        print("Stop: tracked files have uncommitted changes. The public copy is made from the")
        print("last commit, so commit (or stash) first:\n" + dirty)
        return 2

    name = args.name or git("config", "user.name")
    email = args.email or git("config", "user.email")
    if not args.email and not email.endswith("users.noreply.github.com"):
        print("Stop: a public commit shows its author email. Pass --email with your GitHub")
        print("noreply address (GitHub -> Settings -> Emails), or any address you are happy to publish.")
        return 2

    # 1-3: export HEAD, minus the excluded paths.
    archive = git("archive", "--format=tar", "HEAD", binary=True)
    target.mkdir(parents=True, exist_ok=True)
    kept = skipped = 0
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = []
        for m in tar.getmembers():
            if any(m.name == p.rstrip("/") or m.name.startswith(p) for p in EXCLUDE):
                skipped += 1
                continue
            members.append(m)
            kept += m.isfile()
        tar.extractall(target, members=members, filter="data")
    print(f"Exported {kept} files from HEAD ({git('rev-parse', '--short', 'HEAD')}), left out {skipped}.")

    # 4: scan what is about to be published.
    scan = subprocess.run([sys.executable, str(ROOT / "tools" / "secret_scan.py"), str(target)])
    if scan.returncode != 0:
        print(f"\nStop: the scan found secrets in {target}. Nothing was committed.")
        print("Remove them (and add the path to EXCLUDE in this script), then run again.")
        return 1

    # 5: a new repository with one commit.
    git("init", "-b", "main", cwd=target)
    git("add", "-A", cwd=target)
    git("-c", f"user.name={name}", "-c", f"user.email={email}",
        "commit", "-q", "-m", args.message, cwd=target)
    print(f"\nNew repository: {target}")
    print(f"Commit: {git('log', '--oneline', '-1', cwd=target)}  (author {name} <{email}>)")
    print("\nNext (yours to run):")
    print("  1. GitHub -> New repository, empty (no README, no .gitignore), e.g. bytereport")
    print(f"  2. cd \"{target}\"")
    print("  3. git remote add origin https://github.com/<you>/bytereport.git")
    print("  4. git push -u origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
