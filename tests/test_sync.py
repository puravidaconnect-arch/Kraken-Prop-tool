"""sync against a throwaway bare remote. Never touches the real repo."""
import os
import subprocess
from pathlib import Path

import pytest

from src import sync


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.delenv("STUDIO_NO_SYNC", raising=False)
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(remote), str(work))
    git(work, "checkout", "-q", "-b", "main")
    (work / "state").mkdir(); (work / "journal").mkdir(); (work / "src").mkdir()
    (work / "state" / "account_state.json").write_text("{}")
    (work / "src" / "code.py").write_text("x = 1\n")
    git(work, "add", "-A"); git(work, "commit", "-q", "-m", "init"); git(work, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    return work, other, remote


def test_disabled_without_git_or_env(tmp_path, monkeypatch):
    monkeypatch.delenv("STUDIO_NO_SYNC", raising=False)
    assert sync.pull(tmp_path) == "sync off" and sync.push("m", tmp_path) == "sync off"
    monkeypatch.setenv("STUDIO_NO_SYNC", "1")
    assert not sync.enabled(Path(__file__).resolve().parent.parent)


def test_push_record_lands_on_main_and_pull_brings_it_back(repos):
    work, other, _ = repos
    (work / "journal" / "2026-09-14_BTC_long.json").write_text('{"id": "x"}')
    assert sync.push("plan x", work) == "pushed to origin/main"
    assert git(work, "status", "--porcelain").strip() == ""
    assert "nothing new" in sync.push("again", work)
    assert sync.pull(other).startswith("pulled")
    assert (other / "journal" / "2026-09-14_BTC_long.json").read_text() == '{"id": "x"}'


def test_push_from_session_branch_with_only_record_changes_goes_to_main(repos):
    work, other, _ = repos
    git(work, "checkout", "-q", "-b", "claude/session-1")
    (work / "state" / "last_wrap.json").write_text('{"date": "2026-09-14"}')
    assert sync.push("wrap", work) == "pushed to origin/main"
    sync.pull(other)
    assert (other / "state" / "last_wrap.json").exists()


def test_push_with_code_changes_stays_on_branch(repos):
    work, other, _ = repos
    git(work, "checkout", "-q", "-b", "claude/session-2")
    (work / "src" / "code.py").write_text("x = 2\n")
    git(work, "commit", "-q", "-am", "code work")
    (work / "state" / "last_wrap.json").write_text('{"date": "2026-09-15"}')
    msg = sync.push("wrap", work)
    assert msg.startswith("pushed to origin/claude/session-2") and "NOT on main" in msg and "src/code.py" in msg
    sync.pull(other)
    assert not (other / "state" / "last_wrap.json").exists()  # main untouched


def test_push_merges_remote_first(repos):
    work, other, _ = repos
    (other / "state" / "events.json").write_text("{}")
    git(other, "add", "-A"); git(other, "commit", "-q", "-m", "elsewhere"); git(other, "push", "-q", "origin", "main")
    (work / "state" / "last_wrap.json").write_text('{"date": "2026-09-14"}')
    assert sync.push("wrap", work) == "pushed to origin/main"
    assert (work / "state" / "events.json").exists()


def test_pull_refuses_with_dirty_record(repos):
    work, _, _ = repos
    (work / "state" / "account_state.json").write_text('{"dirty": true}')
    with pytest.raises(sync.SyncError, match="uncommitted"):
        sync.pull(work)


def test_cli(repos, monkeypatch, capsys):
    work, _, _ = repos
    monkeypatch.setattr(sync, "ROOT", work)
    monkeypatch.chdir(work)
    (work / "state" / "last_wrap.json").write_text('{"date": "2026-09-14"}')
    assert sync.main(["push", "--message", "m"]) == 0
    assert "pushed" in capsys.readouterr().out
    assert sync.main(["pull"]) == 0
