"""
Bring the public repository up to date with this private one: one new commit.

This repository's history holds old .env files with live keys, so it stays
private. The public repository (the one Vercel and Render deploy from) has its
own, clean history. This script copies what this repository's last commit
(HEAD) contains into the public working tree, with the same exclusions as
make_public_repo.py, scans the result for secrets, and makes one commit there.
It never pushes: that is yours to do.

    python tools/sync_public_repo.py                      # E:\\bytereport-public
    python tools/sync_public_repo.py --dry-run            # show what would change
    python tools/sync_public_repo.py --public ../other --message "..."

It refuses to run when:
  * tracked files here have uncommitted changes (only HEAD is published);
  * tracked files in the public repository have uncommitted changes (they would
    be overwritten);
  * the scan finds a secret in what would be published.

A file deleted here is deleted there too: the public tree mirrors HEAD.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from make_public_repo import EXCLUDE  # noqa: E402  (one list of exclusions for both)
from secret_scan import all_files, scan  # noqa: E402

PRIVATE_ROOT = TOOLS.parent
DEFAULT_PUBLIC = pathlib.Path(r"E:\bytereport-public")
DEFAULT_AUTHOR = ("Azizbek", "264824882+Zynortex@users.noreply.github.com")


class SyncError(Exception):
    """A reason to stop before anything in the public repository is touched."""


def _git(cwd: pathlib.Path, *args: str, stdin: bytes | None = None, binary: bool = False):
    out = subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8").strip()


def _excluded(path: str) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p) for p in EXCLUDE)


def _text(data: bytes) -> bytes:
    """Bytes with CRLF folded to LF: git checks text out with CRLF on Windows."""
    return data.replace(b"\r\n", b"\n")


def export_head(private: pathlib.Path, into: pathlib.Path) -> list[str]:
    """HEAD's tracked files, minus EXCLUDE, written under `into`. Returns their paths."""
    archive = _git(private, "archive", "--format=tar", "HEAD", binary=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = [m for m in tar.getmembers() if not _excluded(m.name)]
        tar.extractall(into, members=members, filter="data")
        return sorted(m.name for m in members if m.isfile())


def sync(private: pathlib.Path, public: pathlib.Path, author: tuple[str, str],
         message: str | None = None, dry_run: bool = False) -> dict:
    """Mirror private HEAD into the public working tree and commit it there."""
    if not (public / ".git").exists():
        raise SyncError(f"{public} is not a git repository.")
    if _git(private, "status", "--porcelain", "--untracked-files=no"):
        raise SyncError("Tracked files in the private repository have uncommitted changes. "
                        "Only the last commit is published: commit (or stash) first.")
    if _git(public, "status", "--porcelain", "--untracked-files=no"):
        raise SyncError(f"Tracked files in {public} have uncommitted changes; "
                        "they would be overwritten. Commit or discard them there first.")

    with tempfile.TemporaryDirectory() as tmp:
        staging = pathlib.Path(tmp)
        exported = export_head(private, staging)

        secrets = [f for f in scan(staging, all_files(staging)) if f[0] == "secret"]
        if secrets:
            lines = "\n".join(f"  {where}  {name}  {shown}" for _, where, name, shown in secrets)
            raise SyncError("The secret scan found keys in what would be published. "
                            f"Nothing was copied.\n{lines}")

        tracked = set(filter(None, _git(public, "ls-files").splitlines()))
        added, changed = [], []
        for rel in exported:
            target = public / rel
            new = (staging / rel).read_bytes()
            if not target.exists():
                added.append(rel)
            # Line endings aside: git checks text out with CRLF on Windows, and
            # that is not a change git would commit.
            elif _text(target.read_bytes()) != _text(new):
                changed.append(rel)
        removed = sorted(tracked - set(exported))
        summary = {"added": added, "changed": changed, "removed": removed, "commit": None}

        if dry_run or not (added or changed or removed):
            return summary

        for rel in added + changed:
            (public / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staging / rel, public / rel)

    if removed:
        _git(public, "rm", "-q", "--pathspec-from-file=-", stdin="\n".join(removed).encode("utf-8"))
    if added or changed:
        _git(public, "add", "--pathspec-from-file=-", stdin="\n".join(added + changed).encode("utf-8"))
    try:
        _git(public, "diff", "--cached", "--quiet")
        return summary            # content differed only in line endings: nothing to commit
    except subprocess.CalledProcessError:
        pass

    name, email = author
    subject = message or _git(private, "log", "-1", "--format=%s")
    # Author AND committer: the committer would otherwise be this machine's git
    # identity, and a public commit shows both.
    _git(public, "-c", f"user.name={name}", "-c", f"user.email={email}",
         "commit", "-q", "--author", f"{name} <{email}>", "-m", subject)
    summary["commit"] = _git(public, "log", "-1", "--format=%h %an <%ae> | %s")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public", type=pathlib.Path, default=DEFAULT_PUBLIC,
                    help=f"the public repository's folder (default {DEFAULT_PUBLIC})")
    ap.add_argument("--message", help="commit message (default: the subject of the private HEAD)")
    ap.add_argument("--dry-run", action="store_true", help="list the changes, touch nothing")
    ap.add_argument("--author-name", default=DEFAULT_AUTHOR[0])
    ap.add_argument("--author-email", default=DEFAULT_AUTHOR[1])
    args = ap.parse_args()

    public = args.public.resolve()
    try:
        s = sync(PRIVATE_ROOT, public, (args.author_name, args.author_email), args.message, args.dry_run)
    except SyncError as exc:
        print(f"Stop: {exc}")
        return 1

    print(f"Added {len(s['added'])}, changed {len(s['changed'])}, removed {len(s['removed'])} file(s).")
    for label, key in (("+", "added"), ("~", "changed"), ("-", "removed")):
        for rel in s[key][:200]:
            print(f"  {label} {rel}")
    if args.dry_run:
        print("Dry run: nothing was written.")
    elif s["commit"]:
        print(f"\nCommitted in {public}:\n  {s['commit']}")
        print("\nNext (yours to run):")
        print(f'  cd "{public}"')
        print("  git push")
    else:
        print("Nothing to sync: the public repository already matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
