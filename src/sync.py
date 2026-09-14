"""Keep the journal and state on GitHub so a cloud session can be thrown away.

The studio's record is the set of files below. `pull()` brings the latest
copy from `origin/main` before a session reads them; `push()` commits them
and pushes to `main` after a session writes them. Both are no-ops when the
root is not a git checkout (tests, a plain folder), and can be turned off
with STUDIO_NO_SYNC=1 or `--no-sync` on the scripts.

  python -m src.sync pull
  python -m src.sync push --message "wrap 2026-09-14"
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from src.state import ROOT

STATE_PATHS = ["state", "journal", "daily_log", "lessons.md", "evals/labels.json", "evals/charts"]
REMOTE, BRANCH = "origin", "main"
IDENTITY = ["-c", "user.name=Trading Studio", "-c", "user.email=studio@localhost"]


class SyncError(RuntimeError):
    """The record could not be pulled or pushed. The caller must stop."""


def enabled(root: Path | None = None) -> bool:
    root = root or ROOT
    return not os.environ.get("STUDIO_NO_SYNC") and (root / ".git").exists()


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["git", *IDENTITY, *args]
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SyncError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r


def _has_remote(root: Path) -> bool:
    return _git(root, "remote", check=False).stdout.split().count(REMOTE) == 1


def pull(root: Path | None = None) -> str:
    """Bring origin/main's record into the working tree. Returns a one-line status."""
    root = root or ROOT
    if not enabled(root):
        return "sync off"
    if not _has_remote(root):
        return "sync skipped: no origin remote"
    _git(root, "fetch", REMOTE, BRANCH)
    dirty = _git(root, "status", "--porcelain", "--", *STATE_PATHS).stdout.strip()
    if dirty:
        raise SyncError("uncommitted changes in the record; run `python -m src.sync push` first")
    ff = _git(root, "merge", "--ff-only", f"{REMOTE}/{BRANCH}", check=False)
    if ff.returncode == 0:
        return "pulled (fast-forward)"
    merge = _git(root, "merge", "--no-edit", f"{REMOTE}/{BRANCH}", check=False)
    if merge.returncode != 0:
        _git(root, "merge", "--abort", check=False)
        raise SyncError("origin/main conflicts with this checkout; resolve by hand before trading")
    return "pulled (merged origin/main)"


def _current_branch(root: Path) -> str:
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _code_changed(root: Path) -> list[str]:
    """Paths that differ between origin/main and HEAD outside the record."""
    names = _git(root, "diff", "--name-only", f"{REMOTE}/{BRANCH}", "HEAD").stdout.split()
    return [n for n in names if not any(n == p or n.startswith(p.rstrip("/") + "/") for p in STATE_PATHS)]


def push(message: str, root: Path | None = None) -> str:
    """Commit the record and push it. Lands on origin/main when the checkout
    carries only record changes; a checkout with code changes pushes to its
    own branch instead, so a trading session never ships half-done code."""
    root = root or ROOT
    if not enabled(root):
        return "sync off"
    if not _has_remote(root):
        return "sync skipped: no origin remote"
    _git(root, "add", "-A", "--", *[p for p in STATE_PATHS if (root / p).exists()])
    staged = _git(root, "diff", "--cached", "--quiet", check=False).returncode != 0
    if staged:
        _git(root, "commit", "-q", "-m", message)
    suffix = "" if staged else " (nothing new to commit)"

    _git(root, "fetch", REMOTE, BRANCH)
    if _git(root, "merge-base", "--is-ancestor", f"{REMOTE}/{BRANCH}", "HEAD", check=False).returncode != 0:
        m = _git(root, "merge", "--no-edit", f"{REMOTE}/{BRANCH}", check=False)
        if m.returncode != 0:
            _git(root, "merge", "--abort", check=False)
            raise SyncError("origin/main conflicts with this checkout; resolve by hand, then python -m src.sync push")
    branch = _current_branch(root)
    code = _code_changed(root)
    if code and branch != BRANCH:
        r = _git(root, "push", REMOTE, f"HEAD:{branch}", check=False)
        if r.returncode != 0:
            raise SyncError(f"push failed: {(r.stderr or r.stdout).strip()}")
        return (f"pushed to {REMOTE}/{branch}{suffix}; NOT on main because this checkout also changes code "
                f"({', '.join(code[:3])}{'…' if len(code) > 3 else ''}). Merge that branch to main to keep the record shared.")
    r = _git(root, "push", REMOTE, f"HEAD:{BRANCH}", check=False)
    if r.returncode != 0:
        raise SyncError(f"push failed: {(r.stderr or r.stdout).strip()}")
    return f"pushed to {REMOTE}/{BRANCH}{suffix}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull/push the studio's record (state, journal, logs, lessons).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull")
    p = sub.add_parser("push"); p.add_argument("--message", default="studio: update record")
    args = ap.parse_args(argv)
    try:
        print(pull() if args.cmd == "pull" else push(args.message))
    except SyncError as exc:
        print(f"SYNC FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
